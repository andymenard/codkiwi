// Migration oracle: existing JS reconstruction, not original-device validation.
const [reference,corpus,limitArg]=Deno.args,limit=Number(limitArg??80);
const source=(await Promise.all(['kiwi-format.js','kiwi-vm.js','native-effects.js','story-runtime.js'].map(f=>Deno.readTextFile(reference+'/'+f)))).join('\n');
const {parseKiwi,StoryRuntime}=new Function(source+';return {parseKiwi,StoryRuntime};')();
function canonical(v){if(Array.isArray(v))return v.map(canonical);if(v&&typeof v==='object')return ['__object__',Object.keys(v).sort().map(k=>[k,canonical(v[k])])];return v;}
async function digest(v){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(canonical(v)))))].map(v=>v.toString(16).padStart(2,'0')).join('');}
function state(r){const v=r.vm;return {script:r.script,ip:v.ip,sp:v.sp,bp:v.bp,pri:v.pri,alt:v.alt,sys:v.sys,state:v.state,stack:v.stack,cells:v.program.cells,pending:v.pendingSyscall,strings:v.stringSlots??[],ui:r.ui,properties:r.properties,arrays:r.arrays,names:r.names,replacements:r.replacements,queue:r.queue,effects:r.effects.save(),events:r.effects.events,results:r.resultSlots,eventText:r.eventText,randomCursor:r.randomCursor};}
const rows=[];
for await(const d of Deno.readDir(corpus)){
 if(!d.isDirectory)continue;const programs=new Map();for await(const f of Deno.readDir(corpus+'/'+d.name))if(f.name.endsWith('.kiw'))programs.set(parseInt(f.name.slice(6),16),parseKiwi(await Deno.readFile(corpus+'/'+d.name+'/'+f.name)));
 let seed=12345;const tape=Array.from({length:32768},()=>seed=(Math.imul(seed,1664525)+1013904223)>>>0);
 const r=new StoryRuntime(programs),row={episode:d.name,frames:[]};rows.push(row);
 try{
 r.reset();r.randomTape=tape;r.load(25001);r.run();
 for(let n=0;n<limit;n++){
  const frame={hash:await digest(state(r)),script:r.script,ip:r.vm.ip,kind:r.ui.kind};row.frames.push(frame);
  if(r.vm.state==='halted')break;
  const c=r.ui.choices.filter(c=>c.enabled);
  const action=r.ui.kind==='action'?{tick:r.ui.remaining+1}:r.ui.kind==='input'?{text:r.ui.input||'Alex'}:{value:c.length?c[(n*17+13)%c.length].value:0};frame.action=action;
  r.effects.events=[];r.calls=[];
  if('tick'in action)r.tick(action.tick);else r.respond(action.text??action.value);
 }
 }catch(e){row.error=e.message;}
}
console.log(JSON.stringify({schema:1,limit,seed:12345,tapeLength:32768,rows}));
