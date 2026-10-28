// Browser API/DOM simulation; no npm dependency or real microphone/network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(id) { this.id=id; this.value=''; this.textContent=''; this.hidden=false; this.disabled=false; this.checked=false; this.listeners={}; }
  addEventListener(name, cb) { (this.listeners[name] ||= []).push(cb); }
  setAttribute(name, value) { this[name]=value; }
  focus() { this.focused=true; }
  async click() { if (!this.disabled) for (const cb of this.listeners.click || []) await cb({target:this}); }
}
const ids=['voice-widget','voice-panel','voice-close','voice-open','voice-mic','voice-stop','voice-new','voice-status','voice-text','voice-history','voice-auto-speak','voice-send','voice-read','voice-silence','voice-reply','voice-confirm','voice-action-title','voice-action-name','voice-duration-field','voice-action-duration','voice-action-apply','voice-action-cancel','voice-plan-confirm','voice-plan-apply','voice-plan-cancel','voice-today','voice-preview','logout-btn'];
const els=Object.fromEntries(ids.map(id=>[id,new Element(id)]));
els['voice-panel'].hidden=true; els['voice-confirm'].hidden=true; els['voice-plan-confirm'].hidden=true; els['voice-stop'].disabled=true; els['voice-read'].disabled=true;
const memory = new Map();
const storage={getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,String(v)),removeItem:k=>memory.delete(k)};
const calls=[]; let failWrite=false, spoken=[], currentRec=null, navigated=null, validPlan=true, stalePlan=false;
const mockPlan={date:'2026-10-28',blocks:[{start:'09:00',end:'09:30',title:'کار پروژه'}],validation:{valid:true,violations:[]},warnings:['هشدار نمونه'],deferred:[{title:'کار دوم',message:'زمان کافی نیست'}],conflicts:[]};
class Recognition {
  constructor(){ currentRec=this; }
  start(){ this.started=true; }
  stop(){ this.stopped=true; }
  abort(){ this.aborted=true; }
}
const win={SpeechRecognition:Recognition, SpeechSynthesisUtterance:class {constructor(text){this.text=text;}},
 speechSynthesis:{cancel(){}, getVoices(){return [{lang:'fa-IR'}]}, speak(u){spoken.push(u.text)}},
 location:{assign(p){navigated=p}}, addEventListener(){}, dispatchEvent(){}};
const document={getElementById:id=>els[id],querySelector:()=>({content:'csrf-test'}),body:{dataset:{}}};
const fetch=async(url,opts)=>{calls.push([url,opts]); if(failWrite && opts.method==='POST' && url.includes('/planner/tasks')) throw new Error('network');
 let data={ok:true}; if(url.endsWith('/chat/send')) data={ok:true,conversation_id:42,answer:'پاسخ مدل'};
 if(url.endsWith('/planner/tasks') && !opts.method) data={ok:true,items:[{title:'کار اول',status:'open'}]};
 if(url.endsWith('/planner/today')) data={ok:true,date:'2026-10-28',plan:mockPlan};
 if(url.endsWith('/planner/preview')) data={ok:true,token:validPlan?'signed-token':null,inputs:{open_tasks:2,fixed_events:1,profile_completed:false},plan:{...mockPlan,validation:{valid:validPlan,violations:validPlan?[]:['overlap']}}};
 if(url.endsWith('/planner/preview/confirm')) {
   if(stalePlan) return {ok:false,status:409,json:async()=>({ok:false,error:{message:'اطلاعات تغییر کرده است'}})};
   data={ok:true,plan:mockPlan,plan_db_id:12};
 }
 return {ok:true,status:200,json:async()=>data};};
vm.runInNewContext(fs.readFileSync('app/web/static/js/voice.js','utf8'),{window:win,document,sessionStorage:storage,fetch,console,CustomEvent:class {constructor(type){this.type=type}}});
(async()=>{
 assert.equal(currentRec,null); // No microphone on page load or opening.
 await els['voice-open'].click(); assert.equal(currentRec,null);
 await els['voice-mic'].click(); assert.equal(currentRec.started,true); assert.equal(currentRec.lang,'fa-IR');
 currentRec.onresult({resultIndex:0,results:[Object.assign([{transcript:'سلام'}],{isFinal:true})]});
 assert.equal(els['voice-text'].value,'سلام'); assert.equal(calls.length,0); // no auto-send
 await els['voice-send'].click(); assert.equal(calls.length,0); // while mic is active
 currentRec.onend(); await els['voice-send'].click();
 let body=JSON.parse(calls[0][1].body); assert.equal(body.text,'سلام'); assert.equal(body.allow_remember,false); assert.equal(body.include_history,false); assert.equal(calls[0][1].headers['X-CSRF-Token'],'csrf-test');
 assert.match(els['voice-reply'].textContent,/اقدامی اجرا نشده است/); assert.match(els['voice-reply'].textContent,/پاسخ مدل/); assert.equal(spoken.length,0);
 await els['voice-read'].click(); assert.equal(spoken.length,1); assert.match(spoken[0],/اقدامی اجرا نشده است/);
 els['voice-history'].checked=true; els['voice-text'].value='ادامه'; await els['voice-send'].click(); body=JSON.parse(calls.at(-1)[1].body); assert.equal(body.conversation_id,42); assert.equal(body.include_history,true);
 els['voice-text'].value='ثبت وظیفه خرید شیر'; let before=calls.length; await els['voice-send'].click(); assert.equal(calls.length,before); assert.equal(els['voice-confirm'].hidden,false);
 els['voice-action-duration'].value='0'; await els['voice-action-apply'].click(); assert.equal(calls.length,before);
 els['voice-action-duration'].value='30'; await els['voice-action-apply'].click(); assert.equal(calls.at(-1)[0],'/api/v1/planner/tasks'); body=JSON.parse(calls.at(-1)[1].body); assert.equal(body.title,'خرید شیر'); assert.equal(body.duration_min,30);
 els['voice-text'].value='ثبت پروژه خانه'; before=calls.length; await els['voice-send'].click(); await els['voice-action-cancel'].click(); await els['voice-action-apply'].click(); assert.equal(calls.length,before);
 els['voice-text'].value='ثبت پروژه خانه'; await els['voice-send'].click(); await els['voice-action-apply'].click(); assert.equal(calls.at(-1)[0],'/api/v1/data/projects'); assert.equal(JSON.parse(calls.at(-1)[1].body).name,'خانه');
 els['voice-text'].value='وظایف من'; await els['voice-send'].click(); assert.match(els['voice-reply'].textContent,/کار اول/);
 els['voice-text'].value='برنامه امروز'; await els['voice-send'].click(); assert.equal(calls.at(-1)[0],'/api/v1/planner/today'); assert.match(els['voice-reply'].textContent,/کار پروژه/); assert.match(els['voice-reply'].textContent,/کار دوم/);
 els['voice-text'].value='پیش نمایش برنامه امروز'; before=calls.length; await els['voice-send'].click(); assert.equal(calls.length,before+1); assert.equal(calls.at(-1)[0],'/api/v1/planner/preview'); assert.equal(els['voice-plan-confirm'].hidden,false); assert.match(els['voice-reply'].textContent,/هشدار نمونه/); assert.match(els['voice-reply'].textContent,/کار دوم/);
 await els['voice-plan-cancel'].click(); before=calls.length; await els['voice-plan-apply'].click(); assert.equal(calls.length,before);
 els['voice-text'].value='برنامه امروز را بساز'; await els['voice-send'].click(); await els['voice-plan-apply'].click(); assert.equal(calls.at(-1)[0],'/api/v1/planner/preview/confirm'); assert.equal(JSON.parse(calls.at(-1)[1].body).token,'signed-token'); assert.match(els['voice-status'].textContent,/فعال شد/);
 validPlan=false; els['voice-text'].value='پیش نمایش برنامه امروز'; await els['voice-send'].click(); assert.equal(els['voice-plan-confirm'].hidden,true); assert.match(els['voice-reply'].textContent,/overlap/);
 validPlan=true; stalePlan=true; els['voice-text'].value='پیش نمایش برنامه امروز'; await els['voice-send'].click(); await els['voice-plan-apply'].click(); assert.match(els['voice-status'].textContent,/تغییر کرده/); assert.equal(els['voice-plan-confirm'].hidden,true);
 // Natural variants must reach the local planner, never chat or automatic activation.
 const views=['برنامه امروز من چیه؟','رومکا لطفاً برنامه امروزم رو بهم بگو','امروز چه برنامه ای دارم؟','میشه برای امروز برنامه من رو نشون بده','نمایش برنامه امروز'];
 for(const phrase of views){els['voice-text'].value=phrase; before=calls.length; await els['voice-send'].click(); assert.equal(calls.length,before+1,phrase);assert.equal(calls.at(-1)[0],'/api/v1/planner/today',phrase);}
 const builds=['برام برنامه امروز رو بساز','رومکا برای امروز برنامه ریزی کن','میتونی برنامه امروز منو بچینی؟','لطفا یه برنامه برای امروزم بچین','برنامه امروز را آماده کن','پیش‌نمایش برنامه امروز'];
 for(const phrase of builds){els['voice-text'].value=phrase; before=calls.length; await els['voice-send'].click(); assert.equal(calls.length,before+1,phrase); assert.equal(calls.at(-1)[0],'/api/v1/planner/preview',phrase); assert.match(els['voice-reply'].textContent,/وظایف باز: 2/);assert.match(els['voice-reply'].textContent,/ممکن است پیش‌فرض باشند/); await els['voice-plan-cancel'].click();}
 const ambiguous=['برنامه فردا رو بساز','برنامه امروز رو نساز','برنامه امروز رو حذف کن','برای امروز برنامه بساز ساعت ۶ جلسه دارم','برنامه امروز رو با ورزش تنظیم کن','برنامه من رو نشون بده'];
 for(const phrase of ambiguous){els['voice-text'].value=phrase; before=calls.length; await els['voice-send'].click(); assert.equal(calls.length,before,phrase);assert.equal(els['voice-text'].value,phrase);assert.match(els['voice-reply'].textContent,/هیچ تغییری انجام نشده/);}
 els['voice-text'].value='ثبت وظیفه برنامه امروز'; before=calls.length; await els['voice-send'].click(); assert.equal(calls.length,before); assert.equal(els['voice-confirm'].hidden,false); assert.equal(els['voice-action-name'].value,'برنامه امروز'); await els['voice-action-cancel'].click();
 els['voice-text'].value='پیش نویس خودم'; before=calls.length; await els['voice-today'].click(); assert.equal(calls.at(-1)[0],'/api/v1/planner/today');assert.equal(els['voice-text'].value,'پیش نویس خودم');
 await els['voice-preview'].click(); assert.equal(calls.at(-1)[0],'/api/v1/planner/preview');assert.equal(els['voice-text'].value,'پیش نویس خودم'); before=calls.length; await els['voice-today'].click();assert.equal(calls.length,before);assert.match(els['voice-status'].textContent,/تأیید یا لغو/); await els['voice-plan-cancel'].click();
 els['voice-text'].value='برو به حافظه'; before=calls.length; await els['voice-send'].click(); assert.equal(navigated,'/memory'); assert.equal(calls.length,before);
 els['voice-text'].value='ثبت وظیفه تست'; await els['voice-send'].click(); els['voice-action-duration'].value='60'; failWrite=true; await els['voice-action-apply'].click(); assert.match(els['voice-status'].textContent,/نامشخص/); before=calls.length; await els['voice-action-apply'].click(); assert.equal(calls.length,before);
 await els['voice-mic'].click(); const old=currentRec; await els['voice-close'].click(); assert.equal(old.aborted,true); old.onresult({resultIndex:0,results:[Object.assign([{transcript:'نباید ذخیره شود'}],{isFinal:true})]}); assert.notEqual(els['voice-text'].value,'نباید ذخیره شود');
 console.log('voice widget mocked browser tests passed');
})().catch(err=>{console.error(err);process.exitCode=1});
