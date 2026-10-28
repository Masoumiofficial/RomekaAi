/* Local, review-first extraction. No chat/model call and no writes until commit. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  if (!$('day-draft')) return;
  const panel = $('day-draft'), fields = $('day-draft-fields'), list = $('day-draft-items');
  let active = false, busy = false, pending = null, rows = [];
  const status = text => { $('voice-status').textContent = text; };
  const message = text => { $('day-draft-message').textContent = text; };
  const el = (tag, text, cls) => {
    const e = document.createElement(tag);
    if (text != null) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  };
  function labelled(parent, label, input) {
    const wrap = el('label', null, 'field small');
    wrap.append(el('span', label), input); parent.append(wrap);
  }
  function input(value, placeholder) {
    const e = el('input'); e.type = 'text'; e.className = 'input';
    e.value = value ?? ''; e.placeholder = placeholder || ''; return e;
  }
  function clock(n) {
    return n == null ? '' : `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`;
  }
  function normalize(s) {
    return String(s).replace(/[۰-۹٠-٩]/g, c => String(c.charCodeAt(0) - (c.charCodeAt(0) >= 0x6f0 ? 0x6f0 : 0x660))).trim();
  }
  function minutes(s) {
    const m = normalize(s).match(/^(\d{1,2}):(\d{2})$/);
    if (!m || +m[1] > 24 || +m[2] > 59 || (+m[1] === 24 && +m[2] !== 0)) return null;
    return +m[1] * 60 + +m[2];
  }
  function render(item, index) {
    const box = el('div', null, 'card flat');
    const check = el('input'); check.type = 'checkbox'; check.checked = false;
    const heading = el('label', null, 'small'); heading.append(check, document.createTextNode(` انتخاب مورد ${index + 1}`));
    box.append(heading, el('p', `متن منبع: ${item.title}`, 'xs faint'));
    const title = input(item.title); title.maxLength = 200;
    labelled(box, 'عنوان', title);
    const kind = el('select'); kind.className = 'input';
    for (const [value, name] of [['task','وظیفه'],['event','تعهد ثابت']]) {
      const opt = el('option', name); opt.value = value; kind.append(opt);
    }
    kind.value = item.kind === 'event' ? 'event' : 'task'; labelled(box, 'نوع', kind);
    const task = el('div'); const duration = input(item.duration_min, 'مثلاً ۴۵'); duration.inputMode = 'numeric';
    labelled(task, 'مدت وظیفه به دقیقه (الزامی)', duration);
    const event = el('div'); const start = input(clock(item.start_min), 'مثلاً ۰۹:۳۰');
    const end = input(clock(item.end_min), 'مثلاً ۱۰:۳۰'); start.inputMode = end.inputMode = 'numeric';
    labelled(event, 'شروع (ساعت:دقیقه، ۲۴ ساعته)', start); labelled(event, 'پایان (ساعت:دقیقه، ۲۴ ساعته)', end);
    const category = el('select'); category.className = 'input';
    for (const [value, name] of [['personal','شخصی'],['meeting','جلسه'],['workout','تمرین'],['meal','غذا'],['commute','رفت‌وآمد']]) {
      const opt = el('option', name); opt.value = value; category.append(opt);
    }
    category.value = item.kind === 'event' ? 'meeting' : 'personal'; labelled(event, 'دسته تعهد', category);
    box.append(task, event); const switchKind = () => { task.hidden = kind.value !== 'task'; event.hidden = kind.value !== 'event'; };
    kind.addEventListener('change', switchKind); switchKind(); list.append(box);
    return {check, title, kind, duration, start, end, category};
  }
  async function post(path, body) {
    let session = null;
    try { session = JSON.parse(sessionStorage.getItem('romka.session.v1') || 'null'); } catch (_) {}
    const headers = {'Content-Type':'application/json', 'X-CSRF-Token':document.querySelector('meta[name="csrf-token"]')?.content || session?.csrf || ''};
    if (session?.token) headers.Authorization = 'Bearer ' + session.token;
    const response = await fetch('/api/v1/planner/day-draft/' + path, {
      method: 'POST', credentials: 'same-origin', headers, body: JSON.stringify(body)
    });
    let data = {}; try { data = await response.json(); } catch (_) { /* error page */ }
    if (!response.ok) { const error = new Error(data?.error?.message || `خطای ${response.status}`); error.status = response.status; throw error; }
    return data;
  }
  function setBusy(value) {
    busy = value; $('day-draft-parse').disabled = value; $('day-draft-commit').disabled = value;
    $('day-draft-cancel').disabled = value; fields.disabled = value || !!pending;
  }
  async function parse(text, preferredDate) {
    if (busy) return;
    if (active) { status('ابتدا پیش‌نویس باز را ثبت یا لغو کنید؛ متن فعلی دست‌نخورده مانده است.'); return; }
    if (window.RomkaVoiceListening?.()) { status('ابتدا ضبط را متوقف و متن را بررسی کنید.'); return; }
    text = String(text || '').trim();
    if (!text) { status('ابتدا متن روز را بنویسید یا ضبط کنید.'); return; }
    setBusy(true); status('در حال استخراج محلی پیشنهادها؛ هیچ موردی ثبت نمی‌شود…');
    try {
      const result = await post('parse', {text});
      list.replaceChildren(); rows = result.items.map(render);
      $('day-draft-date').value = result.date_uncertain ? '' : RomkaDate.display(preferredDate || result.suggested_date);
      active = true; panel.hidden = false;
      message(result.date_uncertain ? 'تاریخ مبهم یا متفاوت تشخیص داده شد؛ تاریخ موارد انتخابی را مشخص کنید و روزهای متفاوت را جداگانه بررسی کنید.' : 'تاریخ مشترک را بررسی کنید. زمان و مدت نامشخص باید توسط شما وارد شود.');
      status('پیشنهادها آماده‌اند؛ هیچ موردی هنوز ثبت نشده است.');
      $('day-draft-date').focus();
    } catch (e) { status('استخراج انجام نشد: ' + e.message); }
    finally { setBusy(false); }
  }
  function uuid() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    if (!window.crypto?.getRandomValues) throw new Error('مرورگر امکان ایجاد شناسه امن ندارد.');
    const b = new Uint8Array(16); window.crypto.getRandomValues(b); b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
    const h = Array.from(b, n => n.toString(16).padStart(2, '0')).join('');
    return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;
  }
  function payload() {
    const date = RomkaDate.toISO($('day-draft-date').value);
    if (!date) throw new Error('تاریخ شمسی مشترک معتبر وارد کنید.');
    const selected = rows.filter(r => r.check.checked);
    if (!selected.length) throw new Error('دست‌کم یک مورد را انتخاب کنید.');
    const tasks = [], events = [];
    for (const r of selected) {
      const title = r.title.value.trim();
      if (!title) throw new Error('عنوان تمام موارد انتخاب‌شده را وارد کنید.');
      if (r.kind.value === 'task') {
        const d = normalize(r.duration.value);
        if (!/^\d+$/.test(d) || +d < 5 || +d > 720) throw new Error('مدت هر وظیفه باید بین ۵ تا ۷۲۰ دقیقه باشد.');
        tasks.push({title, duration_min: +d});
      } else {
        const start = minutes(r.start.value), end = minutes(r.end.value);
        if (start == null || end == null || start >= end || start >= 1440) throw new Error('شروع و پایان معتبر و مرتب برای هر تعهد وارد کنید؛ مثال ۰۹:۳۰.');
        events.push({title, start_min:start, end_min:end, category:r.category.value});
      }
    }
    return {request_id:uuid(), date, tasks, events};
  }
  window.addEventListener('beforeunload', e => { if (pending) { e.preventDefault(); e.returnValue = ''; } });
  $('day-draft-parse').addEventListener('click', () => parse($('voice-text').value));
  window.addEventListener('romka:day-draft', e => parse(e.detail?.text, e.detail?.date));
  $('day-draft-commit').addEventListener('click', async () => {
    if (busy || !active) return;
    const retrying = !!pending;
    if (!pending) { try { pending = payload(); } catch (e) { message(e.message); return; } }
    setBusy(true); message('در حال ثبت موارد انتخاب‌شده…');
    try {
      const r = await post('commit', pending);
      if (!Array.isArray(r.task_ids) || !Array.isArray(r.event_ids)) throw new Error('پاسخ ثبت نامعتبر است.');
      pending = null; active = false; panel.hidden = true;
      status(`${r.task_ids.length} وظیفه و ${r.event_ids.length} تعهد ثبت شد. برنامه فعال تغییر نکرد؛ پیش‌نمایش و تأیید برنامه مرحله‌ای جداست.`);
      window.dispatchEvent(new CustomEvent('romka:day-draft-saved'));
    } catch (e) {
      if (!retrying && e.status >= 400 && e.status < 500) {
        pending = null; message('ثبت انجام نشد: ' + e.message + '؛ موارد را اصلاح کنید.');
      } else {
        message('نتیجه ثبت نامشخص است. برای جلوگیری از تکرار، ویرایش قفل شد؛ دوباره همین درخواست را ارسال کنید یا پیش از شروع تازه موارد ثبت‌شده را بررسی کنید.');
      }
    } finally { $('day-draft-commit').textContent = pending ? 'تلاش دوباره با همان درخواست' : 'تأیید و ثبت موارد انتخاب‌شده'; setBusy(false); }
  });
  $('day-draft-cancel').addEventListener('click', () => {
    if (busy) return;
    if (pending && !window.confirm('ممکن است موارد ثبت شده باشند. پیش از ثبت دوباره موارد موجود را بررسی کنید. پیش‌نویس بسته شود؟')) return;
    const uncertain = !!pending; pending = null; active = false; panel.hidden = true; fields.disabled = false;
    $('day-draft-commit').textContent = 'تأیید و ثبت موارد انتخاب‌شده';
    status(uncertain ? 'نتیجه قبلی نامشخص است؛ پیش از ثبت مجدد، موارد موجود را بررسی کنید.' : 'پیش‌نویس لغو شد؛ چیزی ثبت نشد.');
  });
})();
