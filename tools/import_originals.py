#!/usr/bin/env python3
"""Package original CSPUD resources, deduplicating by content SHA-256.
Existing revival assets are reused when byte-identical. No transcript conversion.
"""
import argparse,hashlib,json,lzma,struct,re,sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from codkiwi.library import truncated_ids

def kind(b):
    if b.startswith(b'kiwi'):return '.kiw'
    if b.startswith(b'\x89PNG'):return '.png'
    if b.startswith(b'\xff\xd8\xff'):return '.jpg'
    if b.startswith(b'GIF8'):return '.gif'
    if b.startswith(b'ID3') or b[:1]==b'\xff' and len(b)>1 and b[1]&224==224:return '.mp3'
    if b.startswith(b'RIFF') and b[8:12]==b'WAVE':return '.wav'
    return '.bin'

def unpack(b):
    u16=lambda o:struct.unpack_from('>H',b,o)[0]
    u32=lambda o:struct.unpack_from('>I',b,o)[0]
    if b[:5]!=b'CSPUD':raise ValueError('Not CSPUD')
    for i in range(u32(5)):
        rid=u16(9+i*6);off=u32(11+i*6);compressed,raw=u32(off),u32(off+4);p=b[off+12:off+12+compressed]
        if compressed==raw:data=p
        else:
            props=p[0];lc=props%9;lp=props//9%5;pb=props//45
            decoder=lzma.LZMADecompressor(format=lzma.FORMAT_RAW,filters=[dict(id=lzma.FILTER_LZMA1,dict_size=int.from_bytes(p[1:5],'little'),lc=lc,lp=lp,pb=pb)])
            data=decoder.decompress(p[13:],max_length=raw)
        if len(data)!=raw:raise ValueError('Resource size mismatch')
        yield rid,data

## The base application carries one story inside itself. res_generated/12 is a
## CSPUD container holding eight programs whose chapter cards read Washed Up, The
## Masks We Wear, Bad Medicine, Buried Secrets, Unmasked and The Devil's Island -
## Volume 1, which shipped built in rather than as a purchasable .exp. Its art and
## audio are the base resources around it, so the episode needs only the programs.
##
## Note for anyone packing it later: Volume 1 is the one container where the gate
## is NOT rid - entry. 25004 onwards are off by one (gate 4 at rid 25004, and
## nothing carries gate 3), so a chapter entered with chapter - entry would halt.
## Playing it from its entry script, which is what the library does, is unaffected.
BUILT_IN_EPISODES = {'12': 'Volume_1'}


def built_in(bundled_dir, put):
    """Episodes that live inside the base application's own resource folder."""
    episodes = []
    for f in sorted(bundled_dir.iterdir(), key=lambda p: p.name):
        if not (f.is_file() and f.name.isdecimal()): continue
        if f.read_bytes()[:5] != b'CSPUD': continue
        ident = BUILT_IN_EPISODES.get(f.name, 'builtin_%s' % f.name)
        resources = {str(rid): put(data) for rid, data in unpack(f.read_bytes())}
        episodes.append(dict(id=ident, title=ident.replace('_', ' '), resources=resources,
                             entry=25001 if '25001' in resources else None))
    return episodes


def main():
    p=argparse.ArgumentParser();p.add_argument('episodes',type=Path);p.add_argument('bundled',type=Path);p.add_argument('--game',type=Path,default=Path(__file__).resolve().parents[1]/'game');a=p.parse_args()
    objects=a.game/'kiwi_assets/objects';objects.mkdir(parents=True,exist_ok=True)
    hashes={};reused=set()
    for folder in ['images','audio']:
        for f in (a.game/folder).rglob('*'):
            if f.is_file():hashes.setdefault(hashlib.sha256(f.read_bytes()).hexdigest(),f.relative_to(a.game).as_posix())
    def put(data):
        digest=hashlib.sha256(data).hexdigest()
        if digest in hashes:reused.add(hashes[digest]);return hashes[digest]
        f=objects/(digest+kind(data))
        if not f.exists():f.write_bytes(data)
        return f.relative_to(a.game).as_posix()
    bundled={str(int(f.name)):put(f.read_bytes())for f in a.bundled.iterdir()if f.is_file() and f.name.isdecimal()}
    episodes=built_in(a.bundled,put)
    for f in sorted(a.episodes.glob('*.exp'),key=lambda p:[int(s)if s.isdigit()else s.lower()for s in re.split(r'(\d+)',p.name)]):
        resources={str(rid):put(data)for rid,data in unpack(f.read_bytes())}
        episodes.append(dict(id=f.stem,title=f.stem.replace('_',' '),resources=resources,entry=25001 if '25001'in resources else None))
    ## The source folder holds a second extraction pass whose filenames lost their
    ## leading characters - gic_School.exp beside 1_1_Magic_School.exp, es.exp
    ## beside MTX_Character_Files.exp. Importing both listed every such story
    ## twice. truncated_ids keeps a pair only when the short id is a suffix of the
    ## long one AND the two hold identical resources, so a genuinely different
    ## episode that happens to share a suffix survives.
    dropped=truncated_ids(episodes)
    episodes=[e for e in episodes if e['id'] not in dropped]
    catalog=dict(schema=1,bundled=bundled,episodes=episodes)
    (a.game/'kiwi_assets/catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
    print(json.dumps(dict(episodes=len(episodes),droppedTruncatedDuplicates=sorted(dropped),bundled=len(bundled),uniqueObjects=len(list(objects.iterdir())),reusedRevivalFiles=len(reused)),indent=2))
if __name__=='__main__':main()
