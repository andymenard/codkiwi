#!/usr/bin/env python3
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from codkiwi import parse_kiwi,StoryRuntime

def state(r):
 v=r.vm
 return dict(script=r.script,ip=v.ip,sp=v.sp,bp=v.bp,pri=v.pri,alt=v.alt,sys=v.sys,state=v.state,stack=v.stack,cells=v.program['cells'],pending=v.pendingSyscall,strings=v.stringSlots,ui=r.ui,properties=r.properties,arrays=r.arrays,names=r.names,replacements=r.replacements,queue=r.queue,effects=r.effects.snapshot(),events=r.effects.events,results=r.resultSlots,eventText=r.eventText,randomCursor=r.randomCursor)

def canonical(v):
 if isinstance(v,list):return [canonical(x)for x in v]
 if isinstance(v,dict):return ['__object__',[[k,canonical(v[k])]for k in sorted(v)]]
 return v

def digest(v):return hashlib.sha256(json.dumps(canonical(v),sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def main():
 fixture=json.loads(Path(sys.argv[1]).read_text());root=Path(sys.argv[2]);errors=[];frames=0
 for row in fixture['rows']:
  p={int(f.stem[6:],16):parse_kiwi(f.read_bytes())for f in (root/row['episode']).glob('*.kiw')}
  r=StoryRuntime(p);seed=fixture['seed'];tape=[]
  for _ in range(fixture['tapeLength']):seed=(seed*1664525+1013904223)&0xffffffff;tape.append(seed)
  try:
   r.reset();r.randomTape=tape;r.load(25001);r.run()
   for i,frame in enumerate(row['frames']):
    if digest(state(r))!=frame['hash']:
     errors.append(dict(episode=row['episode'],frame=i,expected=frame,actual=dict(script=r.script,ip=r.vm.ip,kind=r.ui['kind'])));break
    frames+=1
    if 'action' not in frame:break
    action=frame['action'];r.effects.events=[];r.calls=[]
    if 'tick'in action:r.tick(action['tick'])
    else:r.respond(action.get('text',action.get('value',0)))
  except Exception as e:errors.append(dict(episode=row['episode'],exception=str(e)))
 print(json.dumps(dict(episodes=len(fixture['rows']),matchingFrames=frames,errors=errors),indent=2))
 return bool(errors)
if __name__=='__main__':sys.exit(main())
