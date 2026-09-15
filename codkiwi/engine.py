"""Engine-call adapter producing serializable UI and ordered media events."""
import copy
import hashlib
import json
import re
import secrets
from .vm import KiwiVM, signed


class Effects:
    def __init__(self, resources=()):
        self.resourceIds = set(resources); self.events = []
        self.background = -1; self.location = [-1, -1]
        self.portraits = {}; self.expressions = {}
        self.speaker = self.primary = self.event = -1
        self.pendingSound = -1; self.pendingMusic = self.music = None
        self.panEnabled = True; self.alignment = 2
        self.queuedFade = 0

    def emit(self, kind, **data): self.events.append(dict(type=kind, **data))
    def resource(self, ident): return dict(id=ident, scope='expansion' if ident >= 26000 else 'bundled')
    def set_portrait(self, entity, base):
        ids = [base+i if base > 0 and base+i in self.resourceIds else base for i in range(5)]
        self.portraits[str(entity)] = ids
        self.emit('portrait-map', entity=entity, ids=ids)
    def set_speaker(self, entity, expression=0):
        self.speaker = entity; slot = max(0, expression) % 5
        ident = self.portraits.get(str(entity), [-1]*5)[slot]
        self.currentPortrait = ident
        self.emit('speaker', entity=entity, expression=slot, portrait=self.resource(ident), narration=entity == self.event)
    def set_location(self, base, variant):
        if base != -2: self.location[0] = base
        if variant != -2: self.location[1] = variant
        base, variant = self.location
        if base < 0: return
        candidate = base + (variant if variant in (1,2) else 0)
        if candidate not in self.resourceIds: candidate = base
        if candidate != self.background:
            self.background = candidate
            self.emit('background', **self.resource(candidate), base=base, variant=variant)
    def flush(self):
        n = self.pendingSound
        if n >= 26000 or 8001 <= n <= 8006: self.emit('sound', **self.resource(n), stopPrevious=True)
        self.pendingSound = -1
        m = self.pendingMusic
        if m and (m['id'] >= 26000 or 8201 <= m['id'] <= 8209):
            self.music = m
            self.emit('music', **self.resource(m['id']), loop=m['loop'])
        self.pendingMusic = None
    def stop_music(self, duration):
        self.emit('stop-music', fadeMs=1000 if duration == -1 else duration)
        self.music = self.pendingMusic = None
    def snapshot(self): return copy.deepcopy({k:v for k,v in self.__dict__.items() if k not in ('resourceIds','events')})


def fold(text):
    """Case as the original compared a typed answer.

    Every guess the scripts store is written in sentence case - first letter up,
    the rest down - the multi-word ones included: 'Hedge hog', 'Wheel chair',
    'Denture cream', where title case is how a player would actually type it.
    114 of the 126 distinct answers across the 103-container corpus are exactly
    that, and all twelve that are not sit beside one that is, as a redundant extra
    spelling - 'IPCONFIG' and 'IPConfig' next to 'Ipconfig', 'hyde' next to 'Hyde'.
    Authors would not write answers that way, nor bother with those spellings,
    unless the typed answer were folded before the comparison. Comparing raw is
    what made 'grandmaster' fail where 'Grandmaster' passed.

    Folding both sides of the comparison rather than the answer where it is typed
    leaves the player's own text untouched for display. No comparison anywhere in
    the corpus is between two fixed strings, so the two are indistinguishable in
    practice, and this one cannot reach a name.
    """
    return text.lower()


def idle(): return dict(title='', text='', speaker='', choices=[], kind='idle')


class StoryRuntime:
    DEFAULT_CALLS = {12,14,18,19,20,21,23,31,39,41,42,48,62,67,68,69,77,92,93,94,96}
    def __init__(self, programs, resource_ids=(), random_fn=None, volume_id=None, host_call=None):
        self.programs = programs; self.resource_ids = list(resource_ids)
        self.random_fn = random_fn or (lambda: secrets.randbits(32))
        self.host_call = host_call
        if volume_id is None:
            h = 2166136261
            for ident, p in sorted(programs.items()):
                values = [ident] + p['cells'] + [v for ins in p['instructions'] for v in (ins['raw'],ins['operand'] or 0)]
                for value in values:
                    h = ((h ^ (value & 255)) * 16777619) & 0xffffffff
                    h = ((h ^ (value >> 8)) * 16777619) & 0xffffffff
            volume_id = format(h, 'x')
        self.volumeId = volume_id
        self.reset()
    def reset(self):
        self.randomTape=[]; self.randomCursor=0; self.resultSlots=[0]*10; self.eventText=''
        self.arrays={}; self.effects=Effects(self.resource_ids); self.dialog=None; self.ended=False
        self.properties={}; self.names={}; self.replacements={}; self.portraits={}
        self.queue=[]; self.calls=[]; self.ui=idle(); self.primarySpeaker=None; self.eventSpeaker=None
        self.menu=None; self.vm=None; self.script=None; self.lastResult=0
    def load(self, ident, skip=False):
        if ident not in self.programs: raise RuntimeError('Missing script resource %s' % ident)
        self.script=ident; self.vm=KiwiVM(self.programs[ident], self.syscall)
        self.dialog=None if skip else idle(); self.ui=self.dialog if self.dialog is not None else idle()
    def start(self, ident=25001): self.reset(); self.load(ident); return self.run()
    def run(self):
        for _ in range(100):
            state=self.vm.execute()
            if self.ended:
                self.effects.flush(); self.vm.state='halted'; self.ui['kind']='ended'; return 'halted'
            if state != 'halted': self.effects.flush(); return state
            if not self.queue:
                self.effects.flush(); self.ui['kind']='ended'; return state
            n=self.queue.pop(); self.load(n['id'],n['skipDialog'])
        raise RuntimeError('Script transition budget exceeded')
    def respond(self, value=0):
        kind=self.ui['kind']
        if kind in ('choice','portrait') and not any(c['enabled'] and c['value']==value for c in self.ui['choices']):
            raise RuntimeError('Invalid menu selection')
        if kind == 'action':
            choices=[c for c in self.ui['choices'] if c['value']==value]
            if not choices: raise RuntimeError('Invalid action choice')
            self.ui['score']=max(0,self.ui['score']+choices[0]['delta']); self.action_round(); return 'waiting'
        if kind == 'input':
            self.eventText=str(value)[:20]; value=self.vm.slot(0,self.eventText)
        if kind in ('choice','portrait'): self.lastResult=value; self.resultSlots[0]=value
        self.finish_ui()
        self.ui=self.dialog if self.dialog is not None else idle()
        self.ui['choices']=[]; self.ui['kind']='idle'
        self.vm.resume(value); return self.run()
    def finish_ui(self):
        # SHSUIElement::finishUI -> GameModel::setupQueuedFade. Call 16 queues
        # a transition AFTER the current UI is dismissed, not before its text.
        style = self.effects.queuedFade
        self.effects.queuedFade = 0
        if style:
            self.effects.emit('queued-fade', style=style)
    def tick(self, delta):
        if delta < 0: raise RuntimeError('Negative timer tick')
        if self.vm.state != 'waiting' or not self.ui.get('timed'): return
        self.ui['remaining']-=delta
        if self.ui['remaining'] < 0:
            value=self.ui['score'] if self.ui['kind']=='action' else self.ui['defaultValue']
            self.effects.emit('menu-timeout',value=value); self.resultSlots[0]=value; self.lastResult=value
            self.finish_ui()
            self.ui=self.dialog if self.dialog is not None else idle()
            self.vm.resume(value); self.run()
    def random32(self):
        if self.randomCursor >= len(self.randomTape): self.randomTape.extend(self.random_fn() & 0xffffffff for _ in range(1024))
        value=self.randomTape[self.randomCursor]; self.randomCursor+=1; return value
    def random_below(self, n):
        if n <= 0: return 0
        x=self.random32(); x=x-0x100000000 if x & 0x80000000 else x
        return abs(x) % n
    def action_round(self):
        good,bad=self.ui['good'],self.ui['bad']
        if len(good)<2 or len(bad)<3: raise RuntimeError('Action pools too small')
        def draw(n, excluded=()):
            # Fail rather than hang forever on a malformed deterministic tape.
            for _ in range(100000):
                v=self.random32()%n
                if v not in excluded:return v
            raise RuntimeError('Distinct RNG draw budget exceeded')
        g=draw(len(good)); b=draw(len(bad)); b2=draw(len(bad),(b,))
        choices=[dict(text=good[g],delta=1),dict(text=bad[b],delta=-1),dict(text=bad[b2],delta=-1)]
        choices.append(dict(text=good[draw(len(good),(g,))],delta=1) if self.random32()&1==0 else dict(text=bad[draw(len(bad),(b,b2))],delta=-1))
        for _ in range(20):
            a,b=self.random32()&3,self.random32()&3; choices[a],choices[b]=choices[b],choices[a]
        self.ui['choices']=[dict(c,value=i,enabled=True)for i,c in enumerate(choices)]
    def string(self, pointer, replace=False):
        value=(self.vm.stringSlots[pointer-0x7ff5] if pointer-0x7ff5<len(self.vm.stringSlots) else '') if 0x7ff5<=pointer<0x8000 else self.vm.read_string(pointer)
        return self.replace(value or "") if replace else (value or "")
    def replace(self, value):
        for _ in range(100):
            result=value
            for key,replacement in self.replacements.items():
                if key:result=result.replace(key,replacement)
            if result==value:return value
            value=result
        raise RuntimeError('Cyclic name replacement')
    def speaker(self, entity):
        self.ui['speaker']='' if entity==self.eventSpeaker else self.replace(self.names.get(str(entity),'')); self.ui['title']=''
    def syscall(self, ident, a, vm):
        self.calls.append(dict(script=self.script,ip=vm.ip-1,id=ident,args=list(a)))
        s=lambda i, rep=False:self.string(a[i],rep)
        wait={'wait':True}
        def line(text):
            self.ui.update(text=self.replace(text),kind='dialogue',choices=[]); return wait
        def key():return '%s:%s'%(a[0],a[1])
        if ident in self.DEFAULT_CALLS or ident>99:return 0
        if ident in (0,22):
            offset=1 if ident==0 and signed(a[0])<0 else 0
            slot=1-signed(a[0]) if offset else 0
            index=(offset+1) if ident==0 else 2
            fmt=s(offset if ident==0 else 1)
            def sub(m):
                nonlocal index
                index+=1; token=m.group(0)
                return s(index-1) if token=='%s' else chr(a[index-1]&255) if token=='%c' else str(signed(a[index-1]))
            text=re.sub(r'%[cds]' if ident==0 else r'%[ds]',sub,fmt)
            if ident==0:return vm.slot(slot,text)
            if fmt:vm.write_string(a[0],text)
            return 0
        if ident==1:
            self.ui=dict(timed=signed(a[3])>0,remaining=signed(a[3]),defaultValue=signed(a[4]),title=s(0,True),text=s(2,True) if signed(a[2])>=0 else '',speaker='',kind='choice',choices=[dict(text=t,value=i,enabled=True)for i,t in enumerate(s(1,True).split('|'))]);return wait
        if ident==2:
            self.menu=dict(timed=signed(a[2])>0,remaining=signed(a[2]),defaultIndex=signed(a[3]),title=s(0,True),text=s(1,True),speaker='',choices=[],kind='choice');return 0
        if ident==3:
            if self.menu is None:raise RuntimeError('Menu item without menu')
            self.menu['choices'].append(dict(text=s(0,True),value=len(self.menu['choices']) if a[1]==0xfc19 else a[1],enabled=a[2]!=0));return 0
        if ident==4:
            if self.menu is None:raise RuntimeError('Run without menu')
            choices=self.menu['choices']
            if a[0]:
                for i in range(len(choices)):
                    j=self.random_below(len(choices));choices[i],choices[j]=choices[j],choices[i]
            self.ui=self.menu;index=self.menu['defaultIndex'];self.ui['defaultValue']=choices[index]['value'] if 0<=index<len(choices) else index;self.menu=None;return wait
        if ident==5:self.effects.expressions[str(a[0])]=(a[1]&255)-(256 if a[1]&128 else 0);return 0
        if ident in (6,61):
            name=self.names.get(str(a[0]),'')
            if ident==6 and signed(a[1])<0:return vm.slot(~signed(a[1]),name)
            vm.write_string(a[1],name);return a[1] if ident==6 else 0
        if ident in (7,63):self.queue=[];self.properties={};self.arrays={};self.ended=True;return 0
        if ident==8:
            self.ui=dict(title=s(0,True) if signed(a[0])>=0 else '',text=s(1,True),speaker='',choices=[],kind='chapter',imageId=signed(a[2]),parameter=signed(a[3]))
            self.effects.emit('chapter-card',title=self.ui['title'],text=self.ui['text'],image=self.effects.resource(self.ui['imageId']),parameter=self.ui['parameter']);return wait
        if ident==10:self.queue.append(dict(id=a[0],skipDialog=bool(a[1])));return 0
        if ident==11:self.effects.set_location(signed(a[1]),signed(a[0]));return 0
        if ident==13:
            if self.dialog is None:return 0
            offset=int(signed(a[0])<0);entity=a[offset+1];self.speaker(entity)
            expression=signed(a[offset+2]) if len(a)>offset+2 and signed(a[offset+2])!=-1 else self.effects.expressions.get(str(entity),0)
            self.effects.set_speaker(entity,expression)
            text=s(offset);text='('+text+')' if signed(a[0])==-2 else '`'+text+'`' if signed(a[0])==-3 else text
            return line(text)
        if ident in (15,76):self.ui.update(title=s(0,True),speaker='');return line(s(1,True))
        if ident in (17,40):self.ui=dict(title=s(0,True),text=s(1,True),input=s(2,True),speaker='',choices=[],kind='input',maxLength=20);return wait
        if ident==24:return int(fold(s(0))==fold(s(1)))
        if ident==25:vm.write_string(a[0],s(0)+s(1));return 0
        if ident==26:return 0
        if ident==27:return self.random_below(signed(a[0]))
        if ident==28:vm.write_string(a[0],self.eventText);return 0
        if ident==29:
            if a[0]>=10:raise RuntimeError('Invalid result slot')
            return self.resultSlots[a[0]]
        if ident==33:self.ui=dict(title=s(0),text=s(1),speaker='',choices=[],kind='form',parameter=signed(a[2]));return wait
        if ident==34:
            if self.dialog is None:self.dialog=idle();self.ui=self.dialog;self.effects.set_location(signed(a[1]),signed(a[0]))
            return 0
        if ident==35:self.effects.set_speaker(signed(a[0]),signed(a[3]));self.speaker(a[0]);self.effects.set_location(signed(a[2]),signed(a[1]));return 0
        if ident==36:self.ui['title']=s(0);return 0
        if ident==37:return line(s(0))
        if ident==43:self.replacements['$USR']=s(0);return 0
        if ident in (44,54):self.properties['0:%s'%a[0]]=signed(a[1]);return 0
        if ident in (45,55):return self.properties.get('0:%s'%a[0],0)
        if ident==46:self.replacements[s(0)]=s(1);return 0
        if ident==47:
            k=s(0);v=self.replacements.get(k) or s(1);self.replacements[k]=v;return vm.slot(~signed(a[2]),v)
        if ident in (49,64):
            name=s(1)
            if ident==49 and a[2] and not name.startswith('$'):name=' '.join(w[:1].upper()+w[1:].lower() for w in name.split(' '))
            self.names[str(a[0])]=name;return 0
        if ident in (50,51):
            bit=a[2]&255;mask=1<<bit if bit<32 else 0;current=self.properties.get(key(),0)
            if ident==51:return int(bool(current&mask))
            value=current|mask if a[3]==1 else current&~mask
            self.properties[key()]=(value&0xffffffff)-(0x100000000 if value&0x80000000 else 0);return 0
        if ident==52:self.properties[key()]=signed(a[2]);return 0
        if ident==53:return self.properties.get(key(),0)
        if ident==56:self.arrays.setdefault(key(),[]).append(signed(a[2]));return 0
        if ident in (57,59):
            array=self.arrays.get(key(),[])
            if a[2]>=len(array):raise RuntimeError('Invalid native array access')
            if ident==57:return array[a[2]]
            array.pop(a[2]);return 0
        if ident==58:return len(self.arrays.get(key(),[]))
        if ident==60:return next((i for i in range(200) if self.names.get(str(i),'')==s(0)),-1)
        if ident==65:
            if self.dialog is None:return 0
            self.effects.set_speaker(signed(a[0]),signed(a[2]));self.speaker(a[0]);return line(s(1))
        if ident==66:
            weights=list(map(signed,a));total=sum(weights)
            if total<=0 or any(w<0 for w in weights):raise RuntimeError('Invalid weighted random input')
            r=self.random_below(total)
            for i,w in enumerate(weights):
                r-=w
                if r<0:return i
            return len(weights)-1
        if ident==70:return vm.slot(0,'1.3.4') if a[0]==6 else {2:2,3:6,9:1,10:1}.get(a[0],0)
        if ident==71:
            self.ui=dict(title=s(0),text=s(1),speaker='',kind='action',good=s(2).split('|'),bad=s(3).split('|'),timed=signed(a[4])>0,remaining=signed(a[4]),score=0,roundTime=signed(a[7]),choices=[]);self.action_round();return wait
        if ident==72:self.effects.set_portrait(a[0],signed(a[1]));self.portraits[str(a[0])]=a[1];return 0
        if ident==73:return self.portraits.get(str(a[0]),0)
        if ident==74:self.effects.primary=a[0];self.primarySpeaker=a[0];return 0
        if ident==75:self.effects.event=a[0];self.eventSpeaker=a[0];return 0
        if ident==78:self.ui=dict(title=s(0,True),text='',speaker='',kind='portrait',choices=[dict(text='Portrait %s'%(i+1),portraitId=vm.read(a[2]+i),value=i,enabled=True)for i in range(a[1])]);return wait
        if ident==79:
            if 8201<=a[0]<=8209:self.effects.pendingMusic=dict(id=a[0],loop=False)
            else:self.effects.pendingSound=signed(a[0])
            return 0
        if ident==80:self.effects.pendingMusic=dict(id=signed(a[0]),loop=bool(a[1]));return 0
        if ident==81:self.effects.stop_music(signed(a[0]));return 0
        if ident in (82,83,84):self.effects.emit({82:'vibrate',83:'pause-music',84:'resume-music'}[ident]);return 0
        if ident==85:return 0
        if ident==86:self.effects.set_location(signed(a[0]),signed(a[1]));return 0
        if ident==88:self.effects.emit('dialog-aux-text',text=s(0,True));return 0
        if ident==89:self.effects.emit('model-flag-0x400',value=True);return 0
        if ident==90:self.effects.emit('schedule-caption',id=signed(a[0]),text='' if signed(a[1])==-1 else s(1,True));return 0
        if ident==91:
            self.effects.emit('show-loading')
            if a[0]:self.ui=dict(title='Loading',text='Native asynchronous operation: complete explicitly.',kind='loading',choices=[]);return wait
            return 0
        if ident==97:
            self.effects.panEnabled=bool(a[0]);self.effects.alignment=signed(a[1]);self.effects.emit('align-location',enabled=bool(a[0]),alignment=signed(a[1]));return 0
        if ident==98:self.effects.emit('hide-loading');return 0
        if ident==99:self.effects.emit('full-page-ad',flag=bool(a[0]));return 0
        if ident in (16,38):
            if ident == 16:self.effects.queuedFade = signed(a[0])
            self.ui.setdefault('presentation',{})[str(ident)]=list(a);self.effects.emit('presentation-call',id=ident,args=list(a));return 0
        if ident in (9,30,32,87,95) and self.host_call:return self.host_call(ident,a,vm,self)
        raise NotImplementedError('Native platform syscall %s requires explicit host adapter' % ident)

    def snapshot(self):
        fields=('randomTape','randomCursor','resultSlots','eventText','arrays','ended','properties','names','replacements','portraits','queue','ui','primarySpeaker','eventSpeaker','menu','script','lastResult','dialog')
        state={k:copy.deepcopy(getattr(self,k))for k in fields}
        # The data segment starts as a copy of the script's own cells and only
        # self-modifying code writes to it, so record the differences rather than
        # all 18k of them: cells were 88% of the snapshot and most scripts change
        # none. Version 1 snapshots carried the whole segment and still load.
        base=self.programs[self.script]['cells'];live=self.vm.program['cells']
        state.update(version=2,volumeId=self.volumeId,vm=self.vm.snapshot(),effects=self.effects.snapshot(),
                     cellDelta={str(i):b for i,(a,b) in enumerate(zip(base,live)) if a!=b})
        return state
    def restore(self,state):
        if state['version'] not in (1,2) or state['volumeId']!=self.volumeId:raise RuntimeError('Incompatible VM snapshot')
        self.load(state['script'])
        for k,v in state.items():
            if k not in ('version','volumeId','vm','cells','cellDelta','effects'):setattr(self,k,copy.deepcopy(v))
        self.vm.__dict__.update(copy.deepcopy(state['vm']))
        if 'cells' in state:self.vm.program['cells']=list(state['cells'])
        else:
            cells=self.vm.program['cells']
            for i,v in state['cellDelta'].items():cells[int(i)]=v
        self.effects.__dict__.update(copy.deepcopy(state['effects']));self.effects.events=[];self.calls=[]
        if self.ui['kind']=='dialogue' and self.dialog is not None:self.ui=self.dialog
