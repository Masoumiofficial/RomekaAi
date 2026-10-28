// Dependency-free DOM simulation; no microphone or network is used.
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
class Node {
  constructor(tag='div') { this.tagName=tag; this.children=[]; this.listeners={}; this.value=''; this.textContent=''; this.hidden=false; this.disabled=false; this.checked=false; }
  append(...xs) { this.children.push(...xs); }
  replaceChildren(...xs) { this.children=xs; }
  addEventListener(n,fn) { (this.listeners[n] ||= []).push(fn); }
  async click() { if (!this.disabled) for (const fn of this.listeners.click || []) await fn({target:this}); }
  focus() {}
  async change() { for (const fn of this.listeners.change || []) await fn({target:this}); }
}
const ids=['day-draft','day-draft-fields','day-draft-items','day-draft-date','day-draft-message','day-draft-parse','day-draft-commit','day-draft-cancel','voice-text','voice-status'];
const E=Object.fromEntries(ids.map(x=>[x,new Node()])); E['day-draft'].hidden=true;
const listeners={}; let listening=false, shouldFail=false, failStatus=null, calls=[];
const window={crypto:{randomUUID:()=> '4a9599e3-9285-4a39-95e4-148c0b8ab832'}, RomkaVoiceListening:()=>listening,
  addEventListener:(n,f)=>(listeners[n] ||= []).push(f), dispatchEvent(e){for(const f of listeners[e.type]||[]) f(e)}, confirm:()=>true};
const document={getElementById:id=>E[id],createElement:tag=>new Node(tag),createTextNode:text=>({textContent:text}),querySelector:()=>({content:'csrf'})};
const RomkaDate=require('../app/web/static/js/persian-date.js');
const fetch=async (url, options) => {
  calls.push({url, options});
  if (url.endsWith('/commit') && shouldFail) throw new Error('network');
  if (url.endsWith('/commit') && failStatus) return {ok:false,status:failStatus,json:async()=>({error:{message:'fail'}})};
  if (url.endsWith('/commit')) return {ok:true,json:async()=>({task_ids:[1],event_ids:[]})};
  return {ok:true,json:async()=>({date_uncertain:true,suggested_date:null,items:[
    {title:'<img src=x onerror=alert(1)>',kind:'task',duration_min:null,start_min:null,end_min:null},
    {title:'جلسه ساعت ۹ صبح',kind:'event',duration_min:null,start_min:540,end_min:null}]})};
};
class CustomEvent {constructor(type, options={}) {this.type=type;this.detail=options.detail;}}
vm.runInNewContext(fs.readFileSync('app/web/static/js/day-draft.js','utf8'),{document,window,fetch,RomkaDate,CustomEvent,Uint8Array,sessionStorage:{getItem:()=>null}});
(async()=>{
 E['voice-text'].value='فردا کارها'; listening=true; await E['day-draft-parse'].click(); assert.equal(calls.length,0);
 listening=false; await E['day-draft-parse'].click(); assert.equal(calls.length,1); assert.match(calls[0].url,/\/parse$/);
 assert.equal(E['day-draft'].hidden,false); assert.equal(E['day-draft-date'].value,'');
 const [a,b]=E['day-draft-items'].children; const [head,source,title,kind,task]=a.children;
 assert.equal(head.children[0].checked,false); assert.equal(source.textContent,'متن منبع: <img src=x onerror=alert(1)>'); assert.equal(source.children.length,0);
 assert.equal(b.children[0].children[0].checked,false); assert.equal(b.children[5].children[1].children[1].value,'');
 E['day-draft-date'].value='۱۴۰۵/۰۸/۰۶'; await E['day-draft-commit'].click(); assert.equal(calls.length,1); // nothing checked
 head.children[0].checked=true; await E['day-draft-commit'].click(); assert.equal(calls.length,1); // no duration
 task.children[0].children[1].value='۴۵'; shouldFail=true; await E['day-draft-commit'].click(); assert.equal(calls.length,2);
 let first=calls[1].options.body; let payload=JSON.parse(first); assert.equal(payload.date,'2026-10-28'); assert.equal(payload.tasks[0].duration_min,45); assert.equal(payload.events.length,0);
 assert.equal(E['day-draft-fields'].disabled,true); assert.match(E['day-draft-message'].textContent,/نامشخص/);
 shouldFail=false; failStatus=401; await E['day-draft-commit'].click(); assert.equal(E['day-draft-fields'].disabled,true); assert.equal(calls[2].options.body,first);
 failStatus=null; await E['day-draft-commit'].click(); assert.equal(calls[3].options.body,first); assert.equal(E['day-draft'].hidden,true);
 assert.match(E['voice-status'].textContent,/برنامه فعال تغییر نکرد/);
 await E['day-draft-parse'].click(); const before=calls.length; await E['day-draft-cancel'].click(); await E['day-draft-commit'].click(); assert.equal(calls.length,before);
 console.log('day draft UI mock passed');
})().catch(e=>{console.error(e);process.exitCode=1});
