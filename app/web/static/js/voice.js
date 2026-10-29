/* Optional, push-to-talk assistant. No background microphone or model tool execution. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  if (!$('voice-widget')) return;
  const API = '/api/v1', CONV_KEY = 'romka.voice.conversation.v1';
  const session = () => { try { return JSON.parse(sessionStorage.getItem('romka.session.v1') || 'null'); } catch (_) { return null; } };
  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || document.body.dataset.csrf || session()?.csrf || '';
  const getConversation = () => { try { const n = Number(sessionStorage.getItem(CONV_KEY)); return Number.isSafeInteger(n) && n > 0 ? n : null; } catch (_) { return null; } };
  const setConversation = id => { try { if (id) sessionStorage.setItem(CONV_KEY, String(id)); else sessionStorage.removeItem(CONV_KEY); } catch (_) {} };
  async function api(path, body) {
    const headers = {'Content-Type':'application/json'};
    const token = session()?.token; if (token) headers.Authorization = 'Bearer ' + token;
    const opts = {credentials:'include', headers};
    if (body !== undefined) { opts.method = 'POST'; headers['X-CSRF-Token'] = csrf(); opts.body = JSON.stringify(body); }
    let res;
    try { res = await fetch(API + path, opts); } catch (_) { throw new Error('ارتباط با سرور برقرار نشد.'); }
    let data; try { data = await res.json(); } catch (_) { throw new Error('پاسخ سرور نامعتبر است.'); }
    if (!res.ok || data.ok === false) {
      if (res.status === 404 && path === '/chat/send') setConversation(null);
      const error = new Error(data?.error?.message || `خطای ${res.status}`); error.status = res.status; throw error;
    }
    return data;
  }
  const status = message => { $('voice-status').textContent = message; };
  let recognition = null, captureAllowed = false, lastReply = '', busy = false, pending = null, pendingPlan = null;
  window.RomkaVoiceListening = () => recognition !== null;
  const setBusy = value => {
    busy = value; $('voice-send').disabled = value; $('voice-action-apply').disabled = value;
    $('voice-mic').disabled = value || !!recognition || !!wakeRecognition; $('voice-new').disabled = value; $('voice-action-cancel').disabled = value;
    $('voice-plan-apply').disabled = value; $('voice-plan-cancel').disabled = value;
    $('voice-today').disabled = value; $('voice-preview').disabled = value;
  };
  const stopSpeaking = () => { if ('speechSynthesis' in window) window.speechSynthesis.cancel(); };
  function readReply() {
    if (!lastReply) return;
    if (recognition) { status('برای جلوگیری از ضبط پاسخ، ابتدا ضبط را متوقف کنید.'); return; }
    if (!('speechSynthesis' in window) || !window.SpeechSynthesisUtterance) { status('خواندن صوتی در این مرورگر پشتیبانی نمی‌شود.'); return; }
    stopSpeaking();
    const utterance = new window.SpeechSynthesisUtterance(lastReply);
    utterance.lang = 'fa-IR';
    const voice = window.speechSynthesis.getVoices().find(v => /^fa(?:-|$)/i.test(v.lang));
    if (voice) utterance.voice = voice;
    utterance.onerror = () => status('پخش صدا ناموفق بود؛ متن پاسخ در دسترس است.');
    window.speechSynthesis.speak(utterance);
    status(voice ? 'در حال خواندن پاسخ.' : 'صدای فارسی دستگاه پیدا نشد؛ کیفیت یا امکان پخش به دستگاه بستگی دارد.');
  }
  function reply(text) {
    lastReply = String(text || '');
    $('voice-reply').textContent = lastReply;
    $('voice-read').disabled = !lastReply;
  }
  function stopCapture(abort) {
    captureAllowed = !abort;
    if (recognition) { try { abort ? recognition.abort() : recognition.stop(); } catch (_) {} }
    if (abort) { recognition = null; $('voice-mic').disabled = false; $('voice-stop').disabled = true; }
  }
  $('voice-open').addEventListener('click', () => {
    $('voice-panel').hidden = false; $('voice-open').setAttribute('aria-expanded','true'); $('voice-text').focus();
  });
  $('voice-close').addEventListener('click', () => {
    stopCapture(true); stopSpeaking();
    if (wakeOn) status('فعال‌سازی صوتی روشن باقی می‌ماند؛ برای خاموش کردن آن را در همین پنل غیرفعال کنید.');
    $('voice-panel').hidden = true; $('voice-open').setAttribute('aria-expanded','false'); $('voice-open').focus();
  });
  window.addEventListener('pagehide', () => { stopCapture(true); stopSpeaking(); });
  $('logout-btn')?.addEventListener('click', () => { stopCapture(true); stopSpeaking(); setConversation(null); });
  function startCapture() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) { status('تشخیص گفتار در این مرورگر در دسترس نیست؛ می‌توانید متن بنویسید.'); return; }
    if (recognition) return;
    stopSpeaking();
    let rec;
    try { rec = new SpeechRecognition(); } catch (_) { status('تشخیص گفتار در دسترس نیست؛ می‌توانید متن بنویسید.'); return; }
    recognition = rec; captureAllowed = true;
    let recognitionError = false;
    rec.lang = 'fa-IR'; rec.continuous = false; rec.interimResults = false; rec.maxAlternatives = 1;
    rec.onstart = () => { if (recognition === rec) status('میکروفون روشن است؛ صحبت کنید.'); };
    rec.onresult = e => {
      if (!captureAllowed || recognition !== rec) return;
      const pieces = [];
      for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) pieces.push(e.results[i][0].transcript);
      if (pieces.length) {
        const current = $('voice-text').value.trim();
        $('voice-text').value = [current, ...pieces].filter(Boolean).join(' ').slice(0,8000);
        status('متن شناسایی شد؛ آن را بررسی و سپس ارسال کنید.');
      }
    };
    rec.onerror = e => { if (recognition === rec) { recognitionError = true; status(e.error === 'not-allowed' || e.error === 'service-not-allowed' ? 'اجازهٔ میکروفون یا سرویس گفتار داده نشد.' : 'تشخیص گفتار ناموفق بود؛ دوباره تلاش کنید یا متن بنویسید.'); } };
    rec.onend = () => { if (recognition === rec) { recognition = null; captureAllowed = false; $('voice-mic').disabled = busy; $('voice-stop').disabled = true; if (!recognitionError) status('ضبط پایان یافت؛ متن را بررسی کنید.'); if (wakeArmed) setTimeout(wakeRearm, 250); } };
    try { rec.start(); $('voice-mic').disabled = true; $('voice-stop').disabled = false; status('در انتظار شروع ضبط و اجازهٔ مرورگر…'); }
    catch (_) { recognition = null; captureAllowed = false; $('voice-mic').disabled = false; $('voice-stop').disabled = true; status('میکروفون شروع نشد؛ مجوز مرورگر را بررسی کنید.'); }
  }
  $('voice-mic').addEventListener('click', startCapture);
  $('voice-stop').addEventListener('click', () => { stopCapture(false); status('در حال پایان ضبط…'); });

  /* ── optional wake word ("رومکا") ───────────────────────────────────────────
     Off by default. The browser's own SpeechRecognition does the listening, so
     audio leaves the device to that service and the tab must stay visible; this
     is NOT an on-device, low-power detector like Siri. It is bounded: one
     session, a hard time limit, and it stops the moment the tab is hidden. */
  const WAKE_KEY = 'romka.voice.wake.v1', WAKE_MAX_MS = 10 * 60 * 1000, WAKE_WORDS_KEY = 'romka.voice.wakewords.v1';
  const DEFAULT_WAKE_WORDS = 'رومکا, romka, hey romka, سلام رومکا';
  let wakeRecognition = null, wakeOn = false, wakeArmed = false, wakeDeadline = 0, wakeTimer = null, wakeFailures = 0, wakeStopping = false;
  const wakeWords = () => ($('wake-words')?.value || DEFAULT_WAKE_WORDS).split(/[,،]/)
    .map(w => normalize(w)).filter(Boolean);
  const wakeStatus = message => { const el = $('wake-status'); if (el) el.textContent = message; };
  const wakeMatches = text => {
    const clean = normalize(text);
    if (!clean) return false;
    return wakeWords().some(word => word.length >= 2 && clean.includes(word));
  };
  const chime = () => {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext; if (!Ctx) return;
      const ctx = new Ctx(); const now = ctx.currentTime;
      [[660, 0], [880, .12]].forEach(([hz, at]) => {
        const osc = ctx.createOscillator(), gain = ctx.createGain();
        osc.frequency.value = hz; osc.type = 'sine';
        gain.gain.setValueAtTime(.0001, now + at);
        gain.gain.exponentialRampToValueAtTime(.09, now + at + .02);
        gain.gain.exponentialRampToValueAtTime(.0001, now + at + .18);
        osc.connect(gain); gain.connect(ctx.destination); osc.start(now + at); osc.stop(now + at + .2);
      });
      setTimeout(() => { try { ctx.close(); } catch (_) {} }, 600);
    } catch (_) {}
  };
  const wakeLabel = on => { const b = $('voice-open'); if (b) b.textContent = on ? 'دستیار صوتی · گوش می‌دهم' : 'دستیار صوتی';
    const box = $('wake-box'); if (box) box.dataset.on = String(on); };
  function wakeStop(message) {
    wakeStopping = true; wakeOn = false;
    if (wakeTimer) { clearInterval(wakeTimer); wakeTimer = null; }
    if (wakeRecognition) { const rec = wakeRecognition; wakeRecognition = null; try { rec.abort(); } catch (_) {} }
    wakeDeadline = 0; wakeArmed = false;
    const box = $('wake-start'), stop = $('wake-stop'), toggle = $('wake-enabled');
    if (box) box.disabled = false; if (stop) stop.disabled = true;
    if (!busy && !recognition) $('voice-mic').disabled = false;
    if (toggle) toggle.checked = false;
    try { localStorage.removeItem(WAKE_KEY); } catch (_) {}
    if ($('wake-words-field')) $('wake-words-field').hidden = true;
    if ($('wake-controls')) $('wake-controls').hidden = true;
    wakeLabel(false);
    if (message) wakeStatus(message);
    const wakeBoxEl = $('wake-box'); if (wakeBoxEl) wakeBoxEl.dataset.on = 'false';
    wakeStopping = false;
  }
  function wakeStart() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) { wakeStatus('تشخیص گفتار در این مرورگر در دسترس نیست؛ فعال‌سازی صوتی کار نمی‌کند.'); return false; }
    if (wakeRecognition) return true;
    if (recognition) { stopCapture(false); }
    stopSpeaking();
    let rec;
    try { rec = new SpeechRecognition(); } catch (_) { wakeStatus('تشخیص گفتار در دسترس نیست.'); return false; }
    wakeRecognition = rec; wakeOn = true; wakeFailures = 0;
    wakeDeadline = Date.now() + WAKE_MAX_MS;
    let buffer = '';
    rec.lang = 'fa-IR'; rec.continuous = true; rec.interimResults = true; rec.maxAlternatives = 1;
    rec.onstart = () => { if (wakeRecognition === rec) wakeStatus('در انتظار گفتن «رومکا»…'); };
    rec.onresult = e => {
      if (wakeRecognition !== rec) return;
      for (let i = e.resultIndex; i < e.results.length; i++) {
        buffer = (buffer + ' ' + (e.results[i][0].transcript || '')).slice(-240);
      }
      if (!wakeMatches(buffer)) return;
      buffer = '';
      wakeStatus('رومکا فعال شد؛ دستور را بگویید.');
      status('رومکا فعال شد؛ دستور را بگویید.');
      chime();
      wakeRecognition = null; wakeOn = false;
      if (wakeTimer) { clearInterval(wakeTimer); wakeTimer = null; }
      try { rec.stop(); } catch (_) {}
      if ($('wake-stop')) $('wake-stop').disabled = true;
      $('voice-panel').hidden = false; $('voice-open').setAttribute('aria-expanded', 'true');
      wakeLabel(false);
      setTimeout(() => { try { startCapture(); } catch (_) {} }, 120);
    };
    rec.onerror = e => {
      if (wakeRecognition !== rec) return;
      const kind = e.error;
      if (kind === 'not-allowed' || kind === 'service-not-allowed') {
        wakeStop('اجازهٔ میکروفون یا سرویس گفتار داده نشد؛ فعال‌سازی صوتی خاموش شد.');
      } else if (kind === 'network' || kind === 'audio-capture') {
        wakeFailures += 1;
        if (wakeFailures >= 3) wakeStop('سرویس گفتار پاسخ نداد؛ فعال‌سازی صوتی خاموش شد. دکمهٔ ضبط دستی همچنان کار می‌کند.');
      }
    };
    rec.onend = () => {
      if (wakeRecognition !== rec || wakeStopping) return;
      wakeRecognition = null;
      if (wakeOn) setTimeout(() => { if (wakeOn && !wakeRecognition) wakeStart(); }, 350);
    };
    try { rec.start(); } catch (_) { wakeRecognition = null; wakeOn = false; wakeStatus('میکروفون شروع نشد؛ مجوز مرورگر را بررسی کنید.'); return false; }
    $('voice-mic').disabled = true;   // one microphone, one listener
    return true;
  }
  function wakeRearm() {
    if (!wakeArmed || wakeRecognition || recognition) return;
    if (Date.now() > wakeDeadline) { wakeStop('به محدودیت ۱۰ دقیقهٔ گوش دادن رسید؛ برای ادامه دوباره روشن کنید.'); return; }
    wakeStart();
  }
  const wakeControls = () => {
    const toggle = $('wake-enabled'); if (!toggle) return;
    const box = $('wake-start'), stop = $('wake-stop');
    try {
      const words = $('wake-words')?.value?.trim();
      if (words) localStorage.setItem(WAKE_WORDS_KEY, words); else localStorage.setItem(WAKE_WORDS_KEY, DEFAULT_WAKE_WORDS);
    } catch (_) {}
    if (toggle.checked) {
      if ($('wake-words-field')) $('wake-words-field').hidden = false;
      if ($('wake-controls')) $('wake-controls').hidden = false;
      const ok = wakeStart();
      if (!ok) { toggle.checked = false; wakeArmed = false; return; }
      wakeArmed = true; wakeDeadline = Date.now() + WAKE_MAX_MS;
      try { localStorage.setItem(WAKE_KEY, 'on'); } catch (_) {}
      if (box) box.disabled = true; if (stop) stop.disabled = false;
      wakeLabel(true);
      wakeStatus('فعال‌سازی صوتی روشن است؛ «رومکا» بگویید.');
      if (wakeTimer) clearInterval(wakeTimer);
      wakeTimer = setInterval(() => {
        if (!wakeOn) return;
        if (Date.now() > wakeDeadline) { wakeStop('به محدودیت ۱۰ دقیقهٔ گوش دادن رسید؛ برای ادامه دوباره روشن کنید.'); return; }
        const left = Math.ceil((wakeDeadline - Date.now()) / 1000);
        wakeStatus(`در انتظار گفتن «رومکا»… (${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')} تا توقف خودکار)`);
      }, 1000);
    } else {
      wakeArmed = false;
      wakeStop('فعال‌سازی صوتی خاموش شد.');
    }
  };
  $('wake-enabled')?.addEventListener('change', wakeControls);
  $('wake-start')?.addEventListener('click', () => { if (!$('wake-enabled')?.checked) { $('wake-enabled').checked = true; } wakeControls(); });
  $('wake-stop')?.addEventListener('click', () => wakeStop('گوش دادن متوقف شد.'));
  // Restore the opt-in and the wake words from this browser only.
  (() => {
    try {
      const words = localStorage.getItem(WAKE_WORDS_KEY);
      if (words && $('wake-words')) $('wake-words').value = words;
      if (localStorage.getItem(WAKE_KEY) === 'on' && $('wake-enabled')) {
        $('wake-enabled').checked = true; wakeControls();
      }
    } catch (_) {}
  })();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && wakeOn) wakeStop('تب پنهان شد؛ گوش دادن در پس‌زمینه متوقف شد.');
  });
  window.addEventListener('pagehide', () => { if (wakeOn) wakeStop(); });
  $('logout-btn')?.addEventListener('click', () => { if (wakeOn) wakeStop(); });
  window.RomkaVoiceWake = () => ({enabled: wakeArmed, listening: wakeRecognition !== null,
    remainingMs: wakeArmed ? Math.max(0, wakeDeadline - Date.now()) : 0});
  $('voice-read').addEventListener('click', readReply);
  $('voice-silence').addEventListener('click', () => { stopSpeaking(); status('پخش صدا متوقف شد.'); });
  $('voice-new').addEventListener('click', () => { stopSpeaking(); setConversation(null); pending = null; pendingPlan = null; $('voice-confirm').hidden = true; $('voice-plan-confirm').hidden = true; reply(''); status('گفت‌وگوی جدید آماده است.'); });
  $('voice-action-cancel').addEventListener('click', () => { pending = null; $('voice-confirm').hidden = true; status('اقدام لغو شد؛ چیزی ثبت نشد.'); });

  $('voice-plan-cancel').addEventListener('click', () => { pendingPlan = null; $('voice-plan-confirm').hidden = true; status('پیش‌نمایش لغو شد؛ برنامه‌ای تغییر نکرد.'); });

  // Fixed, local grammar and destinations: model responses never choose a URL or action.
  const destinations = {'داشبورد':'/', 'گفتگو':'/chat', 'گفت و گو':'/chat', 'چت':'/chat',
    'برنامه ریز':'/planner', 'برنامه ریزی':'/planner', 'متخصص ها':'/agents', 'متخصصان':'/agents',
    'پروژه ها':'/business', 'پروژه':'/business', 'سلامت':'/health', 'حافظه':'/memory', 'تنظیمات':'/settings'};
  const normalize = text => text.replace(/[يى]/g,'ی').replace(/ك/g,'ک').replace(/‌/g,' ').replace(/\s+/g,' ').trim();
  // Recognize only a constrained vocabulary; extra dates or constraints are
  // not silently discarded or turned into executable model output.
  function classifyPlan(text) {
    const clean = text.replace(/[ًٌٍَُِّْـ]/g,'').replace(/[،,؛;؟?!.:：]/g,' ')
      .replace(/\s+/g,' ').trim();
    const words = clean.split(' ');
    const planWords = new Set(['برنامه','برنامهام','برنامم','برنامه‌ام','برناممو','برنامهامو']);
    const hasPlan = words.some(word => planWords.has(word));
    const hasToday = words.some(word => ['امروز','امروزم','امروزمو'].includes(word));
    if (!hasPlan) return null;
    const vocabulary = new Set(['سلام','رومکا','عزیز','لطفا','لطفاً','خواهش','میکنم','می','کنم','میشه','شه','میتونی','تونی','میتونه',
      'ممنون','بهم','برام','واسه','برای','یه','یک','من','منو','م','ام','مو','ای','امروز','امروزم','امروزمو','برنامه','برنامهام',
      'برنامم','برناممو','برنامهامو','ریزی','چه','چی','چیه','چیست','چطور','دارم','رو','را','امروزمان',
      'نشون','نشان','نمایش','بده','بگو','بگی','ببینم','میخوام','میخوامش','ببین','ببینم','ببینمش','بخون','بخونی',
      'بساز','بسازی','بچین','بچینی','بذار','بزار','بسازش','تنظیم','تهیه','آماده','کن','کنید','کنی','کنه','بکن','بدهی','پیش','پیشنمایش']);
    const safeVocabulary = words.every(word => vocabulary.has(word));
    if (hasToday && safeVocabulary) {
      if (words.some(word => ['بساز','بسازی','بسازش','بچین','بچینی','بذار','بزار','تنظیم','تهیه','آماده','پیش','پیشنمایش','ریزی'].includes(word))) return 'plan-preview';
      return 'today';
    }
    // Ambiguous planner requests stay local and require an explicit choice.
    if (hasToday || words.some(word => ['فردا','دیروز','هفته','بساز','بسازی','بچین','بچینی','بذار','بزار','تنظیم','تهیه','نشون','نشان','نمایش','بگو','بگی','بده','دارم'].includes(word))) return 'plan-help';
    return null;
  }
  function parse(text) {
    const normalized = normalize(text).replace(/[.!؟?]+$/,'').trim();
    const nav = normalized.match(/^(?:برو به|باز کن|صفحه)\s+(?:بخش\s+)?(.+?)(?:\s+(?:را|رو))?$/);
    if (nav && Object.hasOwn(destinations, nav[1])) return {type:'navigate', path:destinations[nav[1]]};
    if (/^(?:وظایف من|کارهای من|لیست وظایف|فهرست وظایف)$/.test(normalized)) return {type:'tasks'};
    // Explicit task/project creation wins even if the title mentions a plan.
    // Preserve the original title; normalized text is only for matching commands.
    const action = text.trim().match(/^(?:ثبت|ایجاد|افزودن)(?:\s+(?:یک|یه))?\s+(وظیفه|پروژه)(?:\s*[:：]\s*|\s+)?([\s\S]*)$/);
    if (action) return {type:action[1] === 'وظیفه' ? 'task' : 'project', name:action[2].trim()};
    const planCommand = classifyPlan(normalized);
    if (planCommand) return {type:planCommand};
    return {type:'chat'};
  }
  function formatPlan(plan, iso, preview) {
    const date = window.RomkaDate?.display(iso) || iso || '—';
    if (!plan) return `برای تاریخ ${date} برنامهٔ فعالی ثبت نشده است. برای محاسبه از دکمهٔ پیش‌نمایش استفاده کنید.`;
    const lines = [preview ? `پیش‌نمایش ذخیره‌نشده برای ${date}` : `برنامهٔ فعال ${date}`,
      plan.validation?.valid ? 'اعتبار محاسبه: معتبر' : 'هشدار: برنامه معتبر نیست و قابل فعال‌سازی از این پنل نیست.'];
    const blocks = Array.isArray(plan.blocks) ? plan.blocks : [];
    if (!blocks.length) lines.push('بازه‌ای در برنامه وجود ندارد.');
    for (const block of blocks) lines.push(`${block.start || '—'} تا ${block.end || '—'}: ${block.title || 'بدون عنوان'}`);
    for (const warning of plan.warnings || []) lines.push(`هشدار: ${warning}`);
    for (const conflict of plan.conflicts || []) lines.push(`تعارض: ${conflict.message || 'تعارض زمان‌بندی'}`);
    for (const violation of plan.validation?.violations || []) lines.push(`خطای اعتبار: ${violation}`);
    for (const item of plan.deferred || []) lines.push(`به‌تعویق‌افتاده: ${item.title || 'بدون عنوان'} — ${item.message || 'دلیل ثبت نشده'}`);
    if (plan.calibration?.note) lines.push(`کالیبراسیون: ${plan.calibration.note}`);
    return lines.join('\n');
  }
  async function showPreview(body) {
    const data = await api('/planner/preview', body);
    let explanation = 'منبع برنامه‌ریز: وظایف، تعهدات و پروفایل ثبت‌شده؛ متن گفتگو یا حافظه به‌طور خودکار وظیفه نمی‌شود.';
    if (data.inputs) {
      explanation += `\nوظایف باز: ${data.inputs.open_tasks}؛ تعهدات ثابت این روز: ${data.inputs.fixed_events}.`;
      if (!data.inputs.profile_completed) explanation += '\nپروفایل اولیه تکمیل نشده است.';
      if (!data.inputs.open_tasks && !data.inputs.fixed_events) explanation += '\nبرای این محاسبه وظیفه یا تعهد ثابتی ثبت نشده است.';
    }
    explanation += '\nبرخی زمان‌ها یا ظرفیت‌ها ممکن است پیش‌فرض باشند؛ آنها را در پروفایل بررسی کنید.';
    reply(explanation + '\n\n' + formatPlan(data.plan, data.plan?.date, true));
    pendingPlan = data.token || null;
    $('voice-plan-confirm').hidden = !pendingPlan;
    return pendingPlan ? 'پیش‌نمایش آماده است؛ هنوز چیزی ثبت نشده است.' : 'این پیش‌نمایش معتبر نیست؛ تعارض‌ها را در پاسخ بررسی کنید.';
  }
  async function submitText(text, preserveDraft=false) {
    if (busy) return;
    if (recognition) { status('ابتدا ضبط را متوقف کنید و متن را بررسی کنید.'); return; }
    if (!text) { status('متن پیام خالی است.'); return; }
    if (preserveDraft && (pending || pendingPlan)) { status('ابتدا پیش‌نمایش قبلی را تأیید یا لغو کنید.'); return; }
    pending = null; pendingPlan = null; $('voice-confirm').hidden = true; $('voice-plan-confirm').hidden = true;
    const command = parse(text);
    if (command.type === 'navigate') { window.location.assign(command.path); return; }
    if (command.type === 'plan-help') {
      reply('منظور از درخواست برنامه مشخص نیست یا شامل جزئیات دیگری است. هیچ تغییری انجام نشده است. برای نمایش یا پیش‌نمایش امروز از دکمه‌های بالا استفاده کنید؛ برای تاریخ یا محدودیت دیگر به برنامه‌ریز بروید.');
      status('درخواست به مدل فرستاده نشد؛ متن شما حفظ شده است.');
      if ($('voice-auto-speak').checked && !$('voice-panel').hidden) readReply();
      return;
    }
    if (command.type === 'task' || command.type === 'project') {
      if (!command.name) { status('عنوان را بعد از دستور بگویید یا بنویسید.'); return; }
      pending = command.type;
      $('voice-action-title').textContent = pending === 'task' ? 'پیش‌نمایش وظیفه' : 'پیش‌نمایش پروژه';
      $('voice-action-name').value = command.name;
      $('voice-action-name').maxLength = pending === 'task' ? 400 : 200;
      $('voice-duration-field').hidden = pending !== 'task';
      $('voice-action-duration').value = '60';
      $('voice-confirm').hidden = false;
      status('پیش‌نمایش را بررسی کنید؛ هنوز چیزی ثبت نشده است.');
      $('voice-action-name').focus(); return;
    }
    setBusy(true); status('در حال دریافت پاسخ…');
    let finalStatus = 'فهرست آماده است.';
    try {
      if (command.type === 'tasks') {
        const data = await api('/planner/tasks');
        const items = data.items.filter(x => x.status !== 'done');
        reply(items.length ? `وظایف باز (${items.length}):\n` + items.slice(0,10).map((x,i)=>`${i+1}. ${x.title}`).join('\n') + (items.length > 10 ? '\nبرای بقیه به برنامه‌ریز بروید.' : '') : 'وظیفهٔ بازی وجود ندارد.');
      } else if (command.type === 'today') {
        const data = await api('/planner/today');
        reply(formatPlan(data.plan, data.date, false));
        finalStatus = 'برنامهٔ فعال دریافت شد؛ چیزی تغییر نکرد.';
      } else if (command.type === 'plan-preview') {
        finalStatus = await showPreview({energy_mode:'normal'});
      } else {
        const data = await api('/chat/send', {text, conversation_id:getConversation(), include_history:$('voice-history').checked, allow_remember:false});
        if (Number.isSafeInteger(data.conversation_id) && data.conversation_id > 0) setConversation(data.conversation_id);
        reply('پاسخ گفت‌وگو؛ اقدامی اجرا نشده است.\n\n' + (data.answer || 'پاسخی دریافت نشد.'));
        const cost = Number(data.provider?.cost_usd);
        finalStatus = 'پاسخ آماده است.' + (Number.isFinite(cost) ? ` هزینهٔ گزارش‌شده: ${cost} دلار.` : '');
      }
      if (!preserveDraft && $('voice-text').value.trim() === text) $('voice-text').value = '';
      status(finalStatus);
      if (lastReply && $('voice-auto-speak').checked && !$('voice-panel').hidden) readReply();
    } catch (e) { status(e.message); }
    finally { setBusy(false); }
  }
  window.addEventListener('romka:plan-preview', async event => {
    if (busy || recognition || pending || pendingPlan) { status('ابتدا ضبط یا پیش‌نمایش قبلی را تمام کنید.'); return; }
    setBusy(true); status('در حال محاسبه پیش‌نمایش…');
    try { status(await showPreview({date:event.detail.date, energy_mode:event.detail.mode})); }
    catch (e) { status(e.message); }
    finally { setBusy(false); }
  });
  $('voice-send').addEventListener('click', () => submitText($('voice-text').value.trim()));
  $('voice-today').addEventListener('click', () => submitText('برنامه امروز', true));
  $('voice-preview').addEventListener('click', () => submitText('پیش نمایش برنامه امروز', true));
  $('voice-plan-apply').addEventListener('click', async () => {
    if (busy || !pendingPlan) return;
    const token = pendingPlan; setBusy(true); status('در حال فعال‌سازی برنامه…');
    try {
      const data = await api('/planner/preview/confirm', {token});
      pendingPlan = null; $('voice-plan-confirm').hidden = true;
      reply(formatPlan(data.plan, data.plan?.date, false));
      status('برنامه فعال شد؛ برای به‌روزرسانی صفحهٔ فعلی آن را بازخوانی کنید.');
      window.dispatchEvent(new CustomEvent('romka:plan-activated'));
      if (lastReply && $('voice-auto-speak').checked && !$('voice-panel').hidden) readReply();
    } catch (e) {
      pendingPlan = null; $('voice-plan-confirm').hidden = true;
      status(e.status >= 400 && e.status < 500 ? e.message : 'نتیجهٔ فعال‌سازی نامشخص است؛ ابتدا برنامهٔ فعال را بررسی کنید.');
    } finally { setBusy(false); }
  });
  $('voice-action-apply').addEventListener('click', async () => {
    if (busy || !pending) return;
    const name = $('voice-action-name').value.trim();
    const duration = Number($('voice-action-duration').value);
    if (!name || name.length > (pending === 'task' ? 400 : 200)) { status('عنوان معتبر لازم است.'); return; }
    if (pending === 'task' && (!Number.isInteger(duration) || duration < 5 || duration > 720)) { status('مدت تخمینی باید بین ۵ تا ۷۲۰ دقیقه باشد.'); return; }
    const kind = pending; setBusy(true); status('در حال ثبت…');
    try {
      await api(kind === 'task' ? '/planner/tasks' : '/data/projects', kind === 'task' ? {title:name, duration_min:duration} : {name});
      pending = null; $('voice-confirm').hidden = true; $('voice-text').value = '';
      reply(kind === 'task' ? 'وظیفه ثبت شد. برای دیدن آن به برنامه‌ریز بروید.' : 'پروژه ثبت شد. برای دیدن آن به بخش پروژه‌ها بروید.');
      status('ثبت انجام شد؛ برای به‌روزرسانی صفحهٔ فعلی، آن را بازخوانی کنید.');
      if (lastReply && $('voice-auto-speak').checked && !$('voice-panel').hidden) readReply();
    } catch (e) {
      // A lost response can follow a successful commit. Do not retry blindly.
      pending = null; $('voice-confirm').hidden = true;
      status('نتیجهٔ ثبت نامشخص است. ابتدا فهرست مربوط را بررسی کنید؛ سپس در صورت نیاز دوباره اقدام کنید.');
    }
    finally { setBusy(false); }
  });
})();
