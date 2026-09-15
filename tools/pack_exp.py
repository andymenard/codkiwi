#!/usr/bin/env python3
"""Package a Cause of Death .exp as a self-contained chapter pack.

    python3 tools/pack_exp.py <file.exp> [--out packs] [--name volume_6]

Produces <out>/<name>/ containing:

    resources/<sha256>.<ext>   every resource in the container, content-addressed
    pack.json                  manifest: episode id, entry, chapter table, rid -> path

The manifest is the deliverable. It names the entry script, lists each chapter
with the gate value that reaches it and the title from its chapter card, and
maps every resource id to a file on disk. A host reads that and plays the
chapters through the interpreter; the pack itself is host-neutral.

Chapters are located the way the engine locates them. Every script program opens
with a gate that reads global property 1001 and halts unless it equals
`rid - entry`:

    push <prop> ; syscall 45 get_global_int ; ... ; raw92 <gate | offset<<8>

That prologue holds for 317 of 317 gated programs across the 103-container
corpus, always on property 1001, with `gate == rid - entry` every time - so it is
read out of each program here rather than assumed.
"""
import argparse, hashlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from codkiwi.vm import parse_kiwi                    # noqa: E402
from codkiwi.exp import unpack                       # noqa: E402

EXT = {b'\x89PNG': '.png', b'\xff\xd8\xff': '.jpg', b'GIF8': '.gif',
       b'RIFF': '.wav', b'ID3': '.mp3', b'kiwi': '.kiw'}
WORDS = ['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight',
         'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen']


def extension(data):
    for magic, ext in EXT.items():
        if data.startswith(magic):
            return ext
    if data[:2] == b'\xff\xfb' or data[:2] == b'\xff\xf3':
        return '.mp3'
    return '.bin'


def strings_of(prog):
    raw = bytearray()
    for cell in prog['cells']:
        raw.append((cell >> 8) & 255)
        raw.append(cell & 255)
    text = ''.join(chr(v) if 32 <= v < 127 else '\x00' for v in raw)
    return [s for s in text.split('\x00') if s]


def gate_of(instructions):
    """(property, gate) from the chapter prologue, or None if it has no gate."""
    if len(instructions) < 6:
        return None
    first = instructions[0]
    if first['raw'] != 26 or first['operand'] is None:
        return None
    second = instructions[1]
    call = (second['operand'] if second['raw'] == 30 else
            (second['operand'] >> 8 if second['raw'] == 31 else None))
    if call != 45:
        return None
    for ins in instructions[2:8]:
        if ins['raw'] == 92 and ins['operand'] is not None:
            return first['operand'], ins['operand'] & 255
    return None


def chapter_meta(strings):
    """(number, title) from the chapter card text, or None if there is no card."""
    for i, s in enumerate(strings):
        m = re.match(r'^Chapter\s+([A-Za-z]+)\s*$', s)
        if not m:
            continue
        word = m.group(1).capitalize()
        number = WORDS.index(word) if word in WORDS else None
        title = ''
        for nxt in strings[i + 1:i + 4]:
            if 2 <= len(nxt) <= 40 and not re.search(r'[.!?;:]', nxt) and nxt[:1].isupper():
                title = nxt.strip()
                break
        return number, title
    return None


def slugify(value):
    return re.sub(r'_+', '_', re.sub(r'[^a-z0-9]+', '_', value.lower())).strip('_')


def shared_resources(catalog_path):
    """The base-application assets an .exp relies on but does not contain.

    An .exp is an expansion container: it carries its own scenes but not the
    common portraits, sounds and music. Bundling these makes a pack work in a
    project that has no kiwi_assets store of its own.
    """
    if not catalog_path or not os.path.exists(catalog_path):
        return {}
    root = os.path.dirname(os.path.dirname(os.path.abspath(catalog_path)))
    out = {}
    with open(catalog_path) as handle:
        bundled = json.load(handle).get('bundled', {})
    for rid, rel in bundled.items():
        full = os.path.join(root, rel)
        if os.path.exists(full):
            out[int(rid)] = open(full, 'rb').read()
    return out


def build(exp_path, out_root, name=None, catalog_path=None):
    data = open(exp_path, 'rb').read()
    resources = dict(shared_resources(catalog_path))
    resources.update(unpack(data))        # the container's own ids win on collision
    episode = os.path.splitext(os.path.basename(exp_path))[0]
    slug = slugify(name or episode)
    pack_dir = os.path.join(out_root, slug)
    res_dir = os.path.join(pack_dir, 'resources')
    os.makedirs(res_dir, exist_ok=True)

    entry = 25001
    table = {}
    for rid, payload in sorted(resources.items()):
        digest = hashlib.sha256(payload).hexdigest()
        rel = 'resources/%s%s' % (digest, extension(payload))
        target = os.path.join(pack_dir, rel)
        if not os.path.exists(target):
            with open(target, 'wb') as handle:
                handle.write(payload)
        table[str(rid)] = rel

    own = unpack(data)
    chapters = []
    for rid, payload in sorted(own.items()):
        if not payload.startswith(b'kiwi'):
            continue
        program = parse_kiwi(payload)
        gate = gate_of(program['instructions'])
        if gate is None:
            continue
        meta = chapter_meta(strings_of(program))
        if meta is None:
            continue                      # gated, but no chapter card: a continuation script
        number, title = meta
        chapters.append({'rid': rid, 'gate': gate[1], 'property': gate[0],
                         'number': number, 'title': title,
                         'label': '%s_chapter_%s' % (slug, number if number is not None else rid)})

    manifest = {'id': episode, 'title': episode.replace('_', ' '), 'entry': entry,
                'resources': table, 'chapters': chapters, 'root': 'packs/%s' % slug}
    with open(os.path.join(pack_dir, 'pack.json'), 'w') as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)

    return pack_dir, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('exp')
    parser.add_argument('--out', default='packs')
    parser.add_argument('--name', default=None)
    parser.add_argument('--catalog', default=None,
                        help='base-application catalog whose shared assets get bundled in; '
                             'omit to build a pack of the container alone')
    args = parser.parse_args()
    pack_dir, manifest = build(args.exp, args.out, args.name, args.catalog or None)
    print('pack written to %s' % os.path.normpath(pack_dir))
    print('  resources : %d' % len(manifest['resources']))
    print('  chapters  : %d' % len(manifest['chapters']))
    for chapter in manifest['chapters']:
        print('    %-32s rid %-6s gate %-3s %s'
              % (chapter['label'], chapter['rid'], chapter['gate'], chapter['title']))


if __name__ == '__main__':
    main()
