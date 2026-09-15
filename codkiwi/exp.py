"""Original CSPUD containers exposed as virtual RenPy files, without conversion."""
import hashlib
import io
import json
import lzma
import os
import struct
from pathlib import Path

MAX_CONTAINER = 128 * 1024 * 1024
MAX_RESOURCE = 64 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024


def extension(data):
    if data.startswith(b'kiwi'): return '.kiw'
    if data.startswith(b'\x89PNG'): return '.png'
    if data.startswith(b'\xff\xd8\xff'): return '.jpg'
    if data.startswith(b'GIF8'): return '.gif'
    if data.startswith(b'RIFF') and data[8:12] == b'WAVE': return '.wav'
    if data.startswith(b'ID3') or len(data) > 1 and data[0] == 255 and data[1] & 224 == 224: return '.mp3'
    return '.bin'


def unpack(data):
    if len(data) > MAX_CONTAINER or len(data) < 9 or data[:5] != b'CSPUD':
        raise ValueError('This is not a supported CSPUD .EXP file.')
    count = struct.unpack_from('>I', data, 5)[0]
    end = 9 + count * 6
    if end > len(data): raise ValueError('Truncated resource table.')
    resources = {}
    total = 0
    for index in range(count):
        rid, offset = struct.unpack_from('>HI', data, 9 + index * 6)
        if rid in resources: raise ValueError('Duplicate resource ID: %s' % rid)
        if offset < end or offset + 12 > len(data): raise ValueError('Invalid resource offset.')
        packed, raw = struct.unpack_from('>II', data, offset)
        total += raw
        if raw > MAX_RESOURCE or total > MAX_TOTAL: raise ValueError('Resource size limit exceeded.')
        if offset + 12 + packed > len(data): raise ValueError('Truncated resource payload.')
        payload = data[offset + 12:offset + 12 + packed]
        if packed != raw:
            if len(payload) < 13: raise ValueError('Truncated LZMA header.')
            props = payload[0]
            dictionary = int.from_bytes(payload[1:5], 'little')
            if props >= 225 or dictionary > MAX_RESOURCE: raise ValueError('Unsupported LZMA parameters.')
            decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[dict(
                id=lzma.FILTER_LZMA1, dict_size=max(4096, dictionary),
                lc=props % 9, lp=props // 9 % 5, pb=props // 45)])
            payload = decoder.decompress(payload[13:], max_length=raw)
        if len(payload) != raw: raise ValueError('Resource size mismatch.')
        resources[rid] = payload
    if not resources.get(25001, b'').startswith(b'kiwi'):
        raise ValueError('This .EXP has no supported entry script (25001).')
    return resources


class Library:
    def __init__(self, renpy):
        self.renpy = renpy
        self.root = Path(renpy.config.savedir) / 'kiwi-exp-library'
        self.files = {}
        self.episodes = {}

    def register(self, data, title):
        digest = hashlib.sha256(data).hexdigest()
        ident = 'exp-' + digest
        if ident in self.episodes: return ident
        resources = unpack(data)
        # Validate every script before making the episode available.
        from .vm import parse_kiwi
        for content in resources.values():
            if content.startswith(b'kiwi'): parse_kiwi(content)
        paths = {}
        for rid, content in resources.items():
            path = 'kiwi_exp/%s/%s%s' % (digest, rid, extension(content))
            paths[str(rid)] = path
            self.files[path] = content
        self.episodes[ident] = dict(id=ident, title=title, resources=paths, entry=25001)
        return ident

    def import_file(self, path):
        source = Path(path).expanduser()
        if source.suffix.lower() != '.exp': raise ValueError('Select an .EXP file.')
        with source.open('rb') as stream: data = stream.read(MAX_CONTAINER + 1)
        ident = self.register(data, source.stem.replace('_', ' '))
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / (ident + '.exp')
        # Keep the exact source bytes for reopening saves after a restart.
        temporary = target.with_suffix('.tmp')
        temporary.write_bytes(data)
        os.replace(temporary, target)
        target.with_suffix('.json').write_text(json.dumps({'title': self.episodes[ident]['title']}))
        return ident

    def scan(self):
        errors = []
        sources = list(self.root.glob('*.exp')) if self.root.exists() else []
        for path in sources:
            try:
                title = path.stem
                if path.with_suffix('.json').exists(): title = json.loads(path.with_suffix('.json').read_text())['title']
                with path.open('rb') as stream: self.register(stream.read(MAX_CONTAINER + 1), title)
            except Exception as exc: errors.append('%s: %s' % (path.name, exc))
        for path in self.renpy.list_files():
            if path.startswith('episodes/') and path.lower().endswith('.exp'):
                try:
                    with self.renpy.file(path) as stream:
                        self.register(stream.read(MAX_CONTAINER + 1), Path(path).stem.replace('_', ' '))
                except Exception as exc: errors.append('%s: %s' % (path, exc))
        return errors

    def open(self, name):
        content = self.files.get(name)
        return io.BytesIO(content) if content is not None else None


def places(gamedir=None):
    """Somewhere to start looking, on whatever this is running on.

    The picker used to offer two roots: the game folder, and the home directory -
    which on Android is the application's own private directory, where the player
    has nothing. Everything they actually have is on shared storage, which is
    somewhere else entirely, so the shared roots and any removable volume are
    offered too. Each one is checked for existence and readability first, so a
    path that does not apply to this device is simply not shown rather than
    leading to an error.
    """
    found = []

    def add(label, path):
        if not path: return
        try:
            candidate = Path(path).expanduser()
            if not candidate.is_dir() or not os.access(str(candidate), os.R_OK): return
            resolved = str(candidate.resolve())
        except OSError:
            return
        if any(resolved == seen or label == name for name, seen in found): return
        found.append((label, resolved))

    home = Path.home()
    add('Home', home)
    for name in ('Downloads', 'Download', 'Documents', 'Desktop'):
        add('Downloads' if name == 'Download' else name, home / name)

    ## Android: /sdcard and /storage/emulated/0 are the same shared volume under
    ## two names, which the resolve-and-dedupe above collapses.
    for root in ('/sdcard', '/storage/emulated/0', os.environ.get('EXTERNAL_STORAGE')):
        add('Device storage', root)
        if root:
            add('Downloads', Path(root) / 'Download')
            add('Documents', Path(root) / 'Documents')

    ## Removable volumes: SD cards on Android, mounted disks on macOS and Linux.
    ## Not /mnt - on both Android and Linux it is where the system puts its own
    ## mounts, and listing those is noise in a file picker.
    for parent in ('/storage', '/Volumes', '/media'):
        try:
            children = sorted(Path(parent).iterdir())
        except OSError:
            continue
        for child in children:
            if child.name in ('self', 'emulated'): continue
            add(child.name, child)

    add('Game folder', gamedir)
    return found


def browse(path):
    """Directory entries for the in-game picker. No OS dialog dependency."""
    directory = Path(path).expanduser().resolve()
    rows = [('..', str(directory.parent), True)]
    try:
        children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        rows.extend((p.name, str(p), p.is_dir()) for p in children
                    if not p.name.startswith('.') and (p.is_dir() or p.suffix.lower() == '.exp'))
        return rows, None
    except OSError as exc: return rows, str(exc)
