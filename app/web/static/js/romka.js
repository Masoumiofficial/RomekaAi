/* ROMKA front-end — vanilla JS, no build step, no CDN, no tracking. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  /* Session transport: cookie when the browser allows it, signed bearer token
     when the embedded preview blocks third-party cookies. Token lives in
     sessionStorage only for this tab and is never written to the URL. */
  const SESSION_KEY = "romka.session.v1";
  const loadSession = () => { try { return JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null"); } catch(e) { return null; } };
  const saveSession = (token, csrfToken) => { try { sessionStorage.setItem(SESSION_KEY, JSON.stringify({token, csrf: csrfToken})); } catch(e) {} };
  const clearSession = () => { try { sessionStorage.removeItem(SESSION_KEY); } catch(e) {} };
  const authHeaders = (extra) => {
    const h = Object.assign({}, extra || {});
    const s = loadSession();
    if (s && s.token) h["Authorization"] = "Bearer " + s.token;
    return h;
  };
  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || document.body.dataset.csrf || (loadSession()?.csrf || "");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  // Translate only known application codes, never rewrite user content or identifiers.
  const labels = {weekly:"هفتگی", monthly:"ماهانه", yearly:"سالانه", daily:"روزانه",
    active:"فعال", approved:"تأییدشده", discovered:"شناسایی‌شده", pending_review:"در انتظار بررسی",
    rejected:"ردشده", inactive:"غیرفعال", executed:"اجراشده", pending_approval:"در انتظار تأیید",
    accepted:"پذیرفته", low:"کم", medium:"متوسط", high:"زیاد", verified:"تأییدشده",
    inferred:"استنباط‌شده", unverified:"تأییدنشده", session:"جلسه", preference:"ترجیحات",
    project:"پروژه", event:"رویداد", agent:"متخصص", retrievable:"بازیابی‌پذیر",
    planning:"برنامه‌ریزی", backend:"بخش سرور", data:"داده", ui:"رابط کاربری", agents:"متخصصان",
    memory:"حافظه", tools:"ابزارها", skills:"مهارت‌ها", jobs:"کارهای زمان‌بندی‌شده",
    telegram:"تلگرام", bale:"بله", local:"محلی", gapgpt:"گپ‌جی‌پی‌تی", openai_compatible:"سازگار با OpenAI"};
  const label = (value) => labels[value] || value || "—";
  // These phrases are from ROMKA's bundled specialist definitions, not user data.
  const specialistText = (s) => String(s || "").replace(/برنامهریز|برنامهریزی|متخصصها|سیستمعامل|نمیکند|نمیدهد|مشخصکردن|تصمیمگیری|دادههای|پروژهها|میشود|میکند/g,
    word => ({"برنامهریز":"برنامه‌ریز", "برنامهریزی":"برنامه‌ریزی", "متخصصها":"متخصص‌ها", "سیستمعامل":"سیستم‌عامل", "نمیکند":"نمی‌کند", "نمیدهد":"نمی‌دهد", "مشخصکردن":"مشخص‌کردن", "تصمیمگیری":"تصمیم‌گیری", "دادههای":"داده‌های", "پروژهها":"پروژه‌ها", "میشود":"می‌شود", "میکند":"می‌کند"}[word]));
  function runtimeWarning(w) {
    if (w === "ENVIRONMENT is not 'production'.") return "برنامه در محیط توسعه اجرا می‌شود؛ برای استفاده عمومی آماده نیست.";
    if (w.startsWith("DEV demo account is active")) return "حساب آزمایشی فعال است؛ برنامه را در این حالت به‌صورت عمومی منتشر نکنید.";
    if (w.startsWith("External provider has a key")) return "کلید ارائه‌دهنده خارجی تنظیم شده است؛ برای تأیید اتصال در این اجرا، از تنظیمات تست اتصال را بزنید.";
    if (w.startsWith("AI provider is the offline")) return "موتور محلی آفلاین فعال است و مدل زبانی آنلاین نیست.";
    if (w.includes("AI_PRIMARY_API_KEY is empty")) return "کلید ارائه‌دهنده خالی است؛ موتور محلی فعال است.";
    if (w.startsWith("Telegram channel disabled")) return "تلگرام غیرفعال است؛ توکن تنظیم نشده است.";
    if (w.startsWith("Bale channel disabled")) return "بله غیرفعال است؛ توکن یا اتصال تأیید نشده است.";
    if (w.startsWith("Using local dev secret")) return "کلید محرمانه محلی مخصوص محیط توسعه استفاده می‌شود.";
    if (w.startsWith("COOKIE_SECURE")) return "کوکی امن غیرفعال است؛ نشست ممکن است از طریق HTTP منتقل شود.";
    if (w.startsWith("SQLite in production")) return "برای محیط عملیاتی، استفاده از پایگاه داده PostgreSQL توصیه می‌شود.";
    return w;
  }
  const hhmm = (m) => `${String(Math.floor(m/60)).padStart(2,"0")}:${String(m%60).padStart(2,"0")}`;
  const API = "/api/v1";
  const page = document.body.dataset.page;
  let toastTimer;
  function toast(msg, bad=false) {
    const t = $("toast"); if (!t) return;
    t.textContent = msg; t.style.borderColor = bad ? "var(--danger)" : "var(--border)";
    t.classList.add("show"); clearTimeout(toastTimer); toastTimer = setTimeout(()=>t.classList.remove("show"), 3600);
  }
  async function api(path, opts={}) {
    const method = opts.method || (opts.body ? "POST" : "GET");
    const init = { method, credentials: "include", headers: authHeaders({ "Content-Type": "application/json" }) };
    if (method !== "GET") init.headers["X-CSRF-Token"] = csrf();
    if (opts.body !== undefined) init.body = JSON.stringify(opts.body);
    let r;
    try { r = await fetch(API + path, init); } catch (e) { throw new Error("ارتباط با سرور برقرار نشد."); }
    let data = {};
    try { data = await r.json(); } catch(e) { data = {error:{message:"پاسخ نامعتبر"}}; }
    if (!r.ok || data.ok === false) {
      const m = data?.error?.message || `خطای ${r.status}`;
      throw new Error(m);
    }
    return data;
  }
  function setHTML(id, html) { const e = $(id); if (e) e.innerHTML = html; }
  function notice(text, kind="warn") { return `<div class="notice ${kind==="danger"?"danger":kind==="ok"?"ok":""}">${esc(text)}</div>`; }
  const errBox = (e) => `<div class="notice danger">${esc(e.message || e)}</div>`;

  /* ── session guard for embedded previews (third-party cookies blocked) ── */
  if (page !== "auth" && document.body.dataset.auth === "client") {
    const stored = loadSession();
    if (!stored || !stored.token) { location.replace("/auth"); }
    else {
      const meta = document.querySelector('meta[name="csrf-token"]');
      document.body.dataset.csrf = stored.csrf || "";
      if (meta) meta.content = stored.csrf || "";
      api("/auth/me").then(r => {
        if (r.csrf_token) {
          document.body.dataset.csrf = r.csrf_token;
          if (meta) meta.content = r.csrf_token;
        }
        const foot = document.querySelector(".sidebar-foot .small");
        if (foot && r.user) foot.textContent = r.user.display_name || r.user.email;
      }).catch(() => { clearSession(); location.replace("/auth"); });
    }
  }

  /* ── chrome ── */
  const savedTheme = localStorage.getItem("romka-theme");
  if (savedTheme) document.documentElement.dataset.theme = savedTheme;
  $("theme-btn")?.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next; localStorage.setItem("romka-theme", next);
  });
  $("menu-btn")?.addEventListener("click", () => $("sidebar")?.classList.toggle("open"));
  $("logout-btn")?.addEventListener("click", async () => {
    try { await api("/auth/logout", {method:"POST"}); } catch(e) {}
    clearSession();
    location.href = "/auth";
  });
  document.querySelectorAll(".tab").forEach(tab => tab.addEventListener("click", () => {
    const box = tab.closest(".auth-card, .content") || document;
    box.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    box.querySelectorAll(".panel").forEach(p => p.classList.toggle("active", p.id === "panel-" + tab.dataset.tab));
  }));
  async function loadChrome() {
    try {
      const s = await api("/status");
      const tag = $("env-tag"); if (tag) { tag.textContent = s.environment === "production" ? "تولید" : "توسعه";
        tag.className = "tag " + (s.environment === "production" ? "ok" : "warn"); }
      const p = (s.providers||[]).find(x => x.role === "primary") || (s.providers||[])[0];
      setHTML("sb-provider", esc(p ? (p.external ? "خارجی" : "محلی") : "—"));
      if ($("status-list")) setHTML("status-list", (s.runtime_warnings||[]).map(runtimeWarning).map(w =>
        `<div class="list-item"><span class="tag warn">توجه</span><span class="grow">${esc(w)}</span></div>`).join("") || notice("همه چیز پیکربندی شده است.","ok"));
    } catch(e) {}
  }

  /* ── auth page ── */
  if (page === "auth") {
    let mode = "login";
    document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => {
      mode = t.dataset.tab;
      $("name-field").style.display = mode === "register" ? "block" : "none";
      $("submit-btn").textContent = mode === "register" ? "ایجاد حساب" : "ورود";
      $("auth-msg").textContent = "";
    }));
    const afterAuth = (data) => {
      if (data.session_token) saveSession(data.session_token, data.csrf_token);
      location.href = "/";
    };
    const go = async (path, body) => {
      $("submit-btn").disabled = true; $("auth-msg").textContent = "در حال پردازش…";
      try { afterAuth(await api(path, {body})); }
      catch(e) { $("auth-msg").innerHTML = errBox(e); $("submit-btn").disabled = false; }
    };
    $("auth-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const body = { email: $("email").value, password: $("password").value };
      if (mode === "register") { body.display_name = $("display_name").value; body.timezone = "Asia/Tehran"; }
      go(mode === "register" ? "/auth/register" : "/auth/login", body);
    });
    $("guest-btn").addEventListener("click", async () => {
      try { afterAuth(await api("/auth/guest", {body:{}})); }
      catch(e) { $("auth-msg").innerHTML = errBox(e); }
    });
    $("demo-fill")?.addEventListener("click", () => {
      mode = "login";
      document.querySelectorAll(".auth-card .tab").forEach(t => t.classList.toggle("active", t.dataset.tab === "login"));
      $("name-field").style.display = "none"; $("submit-btn").textContent = "ورود";
      $("email").value = $("demo-fill").dataset.email;
      $("password").value = $("demo-fill").dataset.password;
      $("auth-msg").textContent = "اطلاعات حساب آزمایشی پر شد؛ دکمه «ورود» را بزنید.";
    });
  }

  /* ── anatomy (shared) ── */
  async function initAnatomy() {
    const list = $("region-list"); if (!list) return;
    let data;
    try { data = await api("/agents/regions"); } catch(e) { setHTML("region-detail", errBox(e)); return; }
    const colors = ["#8b7cf6","#ff9bb3","#ff7a6b","#4fa8ff","#6fd3d1","#7bd1a8","#9cc5ff","#e8b86d"];
    list.innerHTML = data.regions.map((r,i) => `<div class="region-row" data-region="${esc(r.id)}">
      <span class="swatch" style="background:${colors[i%colors.length]}"></span>
      <span>${esc(r.label)}</span><span class="count">${r.active_agents.length} متخصص</span></div>`).join("");
    const detail = (id) => {
      const r = data.regions.find(x => x.id === id); if (!r) return;
      document.querySelectorAll(".anatomy .region, .region-row").forEach(x =>
        x.classList.toggle("active", x.dataset.region === id));
      const c = r.real_counts || {};
      setHTML("region-detail", `<div class="strong">${esc(r.label)}</div>
        <div class="small muted" style="margin:6px 0">متخصصان فعال: ${esc(r.active_agents.join("، ") || "—")}
        ${r.inactive_count ? ` · ${r.inactive_count} غیرفعال` : ""}</div>
        <div class="row" style="gap:6px"><span class="tag">${c.tasks||0} وظیفه باز</span>
        <span class="tag">${c.events||0} رویداد</span><span class="tag">${c.goals||0} هدف</span>
        <span class="tag">${c.memory||0} حافظه</span></div>
        <div style="margin-top:10px"><a class="btn sm" href="/chat">گفت‌وگو با این حوزه</a></div>`);
      if ($("anatomy-hint")) $("anatomy-hint").textContent = r.label;
    };
    list.querySelectorAll(".region-row").forEach(x => {
      x.addEventListener("click", () => detail(x.dataset.region));
      x.addEventListener("keydown", (e) => { if (e.key === "Enter") detail(x.dataset.region); });
    });
    document.querySelectorAll(".anatomy .region").forEach(g => {
      g.addEventListener("click", () => detail(g.dataset.region));
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); detail(g.dataset.region); } });
      if (data.regions.find(r => r.id === g.dataset.region)?.active_agents.length === 0) g.classList.add("inactive");
    });
  }

  /* ── dashboard ── */
  if (page === "dashboard") {
    initAnatomy(); loadChrome();
    const tl = (plan) => {
      if (!plan || !plan.blocks?.length) return `<div class="empty">هنوز برنامه‌ای ساخته نشده است.</div>`;
      return plan.blocks.map(b => `<div class="tl-item ${b.type === "fixed" ? "fixed" : b.type === "buffer" ? "buffer" : ""}">
        <div class="tl-time">${esc(b.start)} – ${esc(b.end)}</div>
        <div class="tl-body"><div class="tl-title">${esc(b.title)}</div>
        <div class="xs faint">${b.type === "fixed" ? "تعهد ثابت" : b.type === "buffer" ? "زمان بافر" : "کار برنامه‌ریزی‌شده"}</div></div></div>`).join("");
    };
    Promise.all([api("/planner/today"), api("/planner/tasks"), api("/data/goals"),
                 api("/agents"), api("/data/projects"), api("/memory/conflicts"), api("/status")])
      .then(([today, tasks, goals, agents, projects, conflicts, status]) => {
        const plan = today.plan; const m = plan?.metrics || {};
        setHTML("k-tasks", tasks.count); setHTML("k-tasks-d", `${tasks.items.filter(x=>x.status==="scheduled").length} زمان‌بندی‌شده`);
        setHTML("k-min", m.scheduled_minutes ?? "—"); setHTML("k-util", m.utilization_pct != null ? m.utilization_pct + "٪" : "—");
        $("k-bar") && ($("k-bar").style.width = Math.min(100, m.utilization_pct||0) + "%");
        setHTML("k-agents", agents.items.filter(a=>a.active).length);
        setHTML("k-provider", (status.providers||[]).some(p=>p.external&&p.available) ? "ارائه‌دهنده خارجی" : "موتور محلی قطعی");
        setHTML("today-date", RomkaDate.display(today.date)); setHTML("today-timeline", tl(plan));
        setHTML("plan-warn", (plan?.warnings||[])[0] || (plan ? "برنامه معتبر و بدون تداخل است." : ""));
        setHTML("priority-list", goals.items.length ? goals.items.slice(0,6).map(g =>
          `<div class="list-item"><span class="tag accent">${esc(label(g.horizon))}</span><span class="grow">${esc(g.title)}</span>
           <span class="faint xs">اولویت ${g.priority}</span></div>`).join("") : `<div class="empty">هدفی ثبت نشده است.</div>`);
        setHTML("mem-chips", `<span class="tag">${projects.count} پروژه</span><span class="tag ${conflicts.items.length?"warn":"ok"}">${conflicts.items.length} تعارض حافظه</span>`);
        const warns = (status.runtime_warnings||[]).map(runtimeWarning);
        if (conflicts.items.length) warns.unshift(`${conflicts.items.length} مورد داده متناقض/تأییدنشده در حافظه دارید.`);
        setHTML("sys-list", warns.length ? warns.map(w=>`<div class="list-item"><span class="tag warn">وضعیت</span><span class="grow">${esc(w)}</span></div>`).join("") : `<div class="empty">هیچ هشداری وجود ندارد.</div>`);
        if (status.runtime_warnings?.length) setHTML("runtime-notice", notice(runtimeWarning(status.runtime_warnings[0])));
      }).catch(e => setHTML("sys-list", errBox(e)));
    $("btn-light")?.addEventListener("click", async () => {
      try { const r = await api("/planner/light-day", {body:{}}); toast(`نسخه سبک: ${r.alternative.scheduled.length} کار باقی ماند (پیشنهاد، ذخیره نشد).`); }
      catch(e){ toast(e.message,true); }
    });
    $("quick-send")?.addEventListener("click", async () => {
      const t = $("quick-ask").value.trim(); if (!t) return;
      setHTML("quick-answer","در حال پردازش…");
      try { const r = await api("/chat/send", {body:{text:t}}); setHTML("quick-answer", esc(r.answer)); }
      catch(e){ setHTML("quick-answer", errBox(e)); }
    });
  }

  /* ── chat ── */
  if (page === "chat") {
    loadChrome();
    let convId = null, streaming = false;
    const renderMsg = (m) => `<div class="msg ${m.role}"><div class="bubble">${esc(m.content)}</div>
      <div class="msg-meta"><span>${m.role === "user" ? "شما" : "رومکا"}</span>
      ${(m.active_agent_ids||[]).length?`<span class="tag accent">${esc(m.active_agent_ids.join(" + "))}</span>`:""}
      ${m.confidence?`<span>اطمینان ${Math.round(m.confidence*100)}٪</span>`:""}</div></div>`;
    const loadConvs = async () => {
      try { const r = await api("/chat/conversations");
        setHTML("conv-list", r.items.length ? r.items.map(c=>`<div class="conv-item ${c.id===convId?"active":""}" data-id="${c.id}">${esc(c.title)} <span class="faint xs">#${c.id}</span></div>`).join("") : `<div class="empty">گفت‌وگویی نیست.</div>`);
        document.querySelectorAll(".conv-item").forEach(x=>x.addEventListener("click",()=>{convId=+x.dataset.id;loadMsgs();loadConvs();}));
      } catch(e){ toast(e.message,true); }
    };
    const loadMsgs = async () => {
      if (!convId) { setHTML("chat-log", `<div class="empty">پیامی ثبت نشده. شروع کنید.</div>`); return; }
      try { const r = await api(`/chat/conversations/${convId}/messages`);
        setHTML("chat-log", r.items.length ? r.items.map(renderMsg).join("") : `<div class="empty">پیامی نیست.</div>`);
        const log = $("chat-log"); log.scrollTop = log.scrollHeight;
      } catch(e){ toast(e.message,true); }
    };
    const after = (r) => {
      convId = r.conversation_id; loadMsgs(); loadConvs();
      setHTML("chat-agents", esc((r.active_agents||[]).map(a=>a.name).join(" + ") || "رومکا"));
      const p = r.provider || {};
      setHTML("chat-meta", `<div class="stack" style="gap:8px">
        <div><span class="tag">ارائه‌دهنده</span> ${esc(p.name||"—")} · ${esc(p.model||"محلی")}</div>
        <div><span class="tag">هزینه</span> ${p.cost_usd ?? 0} دلار</div>
        <div><span class="tag">نقد مستقل</span> ${esc(r.critic?.verdict||"—")} (${r.critic?.score??0})</div>
        <div><span class="tag">منابع حافظه</span> ${(r.sources||[]).length} مورد</div>
        <div><span class="tag">سابقه ارسال‌شده</span> ${r.history_turns_used ?? 0} رفت‌وبرگشت</div>
        ${(r.warnings||[]).length?`<div class="notice">${r.warnings.slice(0,3).map(esc).join("<br>")}</div>`:""}
        </div>`);
      setHTML("chat-actions", (r.suggested_actions||[]).map(a=>`<button class="btn sm" data-ep="${esc(a.endpoint)}" data-type="${esc(a.type)}">${esc(a.label)}</button>`).join(""));
      document.querySelectorAll("#chat-actions button").forEach(b=>b.addEventListener("click", async()=>{
        try {
          if (b.dataset.type === "replan") { await api(b.dataset.ep, {body:{extended_events:{}, energy_mode:"normal"}}); toast("بازبرنامه‌ریزی انجام شد؛ به برنامه‌ریز مراجعه کنید."); }
          else { await fetch(API + b.dataset.ep, {method:"POST", credentials:"include", headers:authHeaders({"Content-Type":"application/json","X-CSRF-Token":csrf()}), body: JSON.stringify({energy_mode: b.dataset.type === "light_day" ? "low" : "normal"})}); toast("برنامه ساخته شد؛ به برنامه‌ریز مراجعه کنید."); }
        } catch(e){ toast(e.message,true); }
      }));
    };
    const send = async () => {
      const text = $("chat-text").value.trim(); if (!text) return;
      $("chat-text").value = "";
      const log = $("chat-log");
      if (log.querySelector(".empty")) log.innerHTML = "";
      log.insertAdjacentHTML("beforeend", renderMsg({role:"user",content:text}));
      log.scrollTop = log.scrollHeight;
      const holder = document.createElement("div"); holder.className = "msg assistant";
      holder.innerHTML = `<div class="bubble">…</div>`; log.appendChild(holder);
      try {
        if (!streaming) {
          const r = await api("/chat/send",{body:{text, conversation_id:convId, include_history:$("chat-history-optin").checked}});
          holder.outerHTML = renderMsg({role:"assistant",content:r.answer,active_agent_ids:r.active_agents.map(a=>a.id),confidence:r.confidence});
          after(r);
        } else {
          const resp = await fetch(API+"/chat/stream",{method:"POST",credentials:"include",
            headers:authHeaders({"Content-Type":"application/json","X-CSRF-Token":csrf()}),body:JSON.stringify({text,conversation_id:convId,include_history:$("chat-history-optin").checked})});
          if (!resp.ok) { const e = await resp.json(); throw new Error(e?.error?.message || `خطای ${resp.status}`); }
          const reader = resp.body.getReader(); const dec = new TextDecoder(); let buf="", full="", meta=null;
          while(true){ const {done,value}=await reader.read(); if(done) break;
            buf += dec.decode(value,{stream:true});
            const parts = buf.split("\n\n"); buf = parts.pop();
            for(const p of parts){ const line=p.split("\n").find(l=>l.startsWith("data: ")); if(!line)continue;
              const ev=JSON.parse(line.slice(6));
              if(ev.event==="delta"){ full+=ev.text; holder.querySelector(".bubble").textContent=full; log.scrollTop=log.scrollHeight; }
              if(ev.event==="done") meta=ev.meta; if(ev.event==="error") full+=ev.message; }
          }
          holder.outerHTML = renderMsg({role:"assistant",content:full,active_agent_ids:meta?.active_agents||[],confidence:meta?.critic?.score});
          if(meta){ convId=meta.conversation_id; loadConvs(); setHTML("chat-meta",`<div class="notice ok">پاسخ جریانی کامل شد. سابقه ارسال‌شده: ${meta.history_turns_used ?? 0} رفت‌وبرگشت. نقد: ${esc(meta.critic.verdict)} (${meta.critic.score})</div>`); }
        }
      } catch(e){ holder.outerHTML = `<div class="msg assistant"><div class="bubble">${esc(e.message)}</div></div>`; }
    };
    $("chat-send")?.addEventListener("click",send);
    $("chat-text")?.addEventListener("keydown",e=>{ if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();} });
    $("new-conv")?.addEventListener("click",()=>{convId=null;setHTML("chat-log",`<div class="empty">گفت‌وگوی جدید.</div>`);loadConvs();});
    $("stream-toggle")?.addEventListener("click",()=>{streaming=!streaming;$("stream-toggle").textContent=`⇢ جریانی: ${streaming?"روشن":"خاموش"}`;});
    loadConvs();
  }

  /* ── planner ── */
  if (page === "planner") {
    loadChrome();
    $("plan-date").value = RomkaDate.display(RomkaDate.todayTehran());
    const selectedDay = () => {
      const iso = RomkaDate.toISO($("plan-date").value);
      if (!iso) throw new Error("تاریخ شمسی معتبر را به صورت سال/ماه/روز وارد کنید؛ مثلاً ۱۴۰۵/۰۸/۰۶.");
      return iso;
    };
    const renderPlan = (p) => {
      if (!p) { setHTML("plan-timeline",`<div class="empty">برنامه‌ای وجود ندارد.</div>`); return; }
      const m = p.metrics||{};
      setHTML("plan-metrics", `<span class="tag ${m.unrealistic?"warn":"ok"}">اعتبار: ${p.validation?.valid?"تأییدشده":"دارای تعارض"}</span>
        <span class="tag">زمان آزاد ${m.free_minutes} دقیقه</span><span class="tag">برنامه‌ریزی ${m.scheduled_minutes} دقیقه</span>
        <span class="tag">اشغال ${m.utilization_pct}٪</span><span class="tag">بافر ${m.buffer_minutes} دقیقه</span>`);
      setHTML("plan-warnings",(p.warnings||[]).map(w=>notice(w)).join("") || notice("هیچ تداخل یا هشداری وجود ندارد.","ok"));
      setHTML("plan-timeline", p.blocks.map(b=>`<div class="tl-item ${b.type==="fixed"?"fixed":b.type==="buffer"?"buffer":""}">
        <div class="tl-time">${esc(b.start)} – ${esc(b.end)}</div><div class="tl-body"><div class="tl-title">${esc(b.title)}</div>
        <div class="xs faint">${b.type==="task"?`اولویت ${b.priority} · ${esc(b.category||"")}`:"تعهد ثابت یا بافر"}</div></div></div>`).join(""));
      setHTML("plan-deferred",(p.deferred||[]).length?`<div class="strong">به‌تعویق‌افتاده‌ها:</div>`+p.deferred.map(d=>`<div class="small">• ${esc(d.title)} — ${esc(d.message)}</div>`).join(""):"");
    };
    const loadTasks = async () => {
      try { const r = await api("/planner/tasks");
        setHTML("task-count", r.count);
        setHTML("task-list", r.items.length?r.items.map(t=>`<div class="list-item ${t.status==="done"?"done":""}">
          <span class="tag ${t.priority<=2?"accent":""}">P${t.priority}</span><span class="grow">${esc(t.title)}</span>
          <span class="faint xs">تخمین ${t.duration_min}′${t.actual_min?` · واقعی ${t.actual_min}′`:""}</span>
          <input type="number" min="1" max="1440" placeholder="واقعی" data-act="${t.id}" class="mini" aria-label="مدت واقعی به دقیقه" style="width:74px">
          <button class="btn sm ghost" data-done="${t.id}" title="انجام شد">✓</button>
          <button class="btn sm ghost danger" data-del="${t.id}" title="حذف">×</button></div>`).join(""):`<div class="empty">وظیفه‌ای ثبت نشده.</div>`);
        document.querySelectorAll("[data-done]").forEach(b=>b.addEventListener("click",async()=>{
          const box=document.querySelector(`[data-act="${b.dataset.done}"]`);
          const actual=box && box.value ? +box.value : null;
          try{
            const r=await api(`/planner/tasks/${b.dataset.done}/complete`,{body: actual?{actual_minutes:actual}:{}});
            const c=r.calibration||{};
            toast(actual?`انجام شد؛ ${actual} دقیقه واقعی ثبت شد (${c.samples||0} نمونه برای کالیبراسیون).`:"انجام شد.");
            renderCalibration(c); loadTasks(); loadWeek();
          }catch(e){toast(e.message,true);}
        }));
        document.querySelectorAll("[data-del]").forEach(b=>b.addEventListener("click",async()=>{try{await api(`/planner/tasks/${b.dataset.del}`,{method:"DELETE"});loadTasks();}catch(e){toast(e.message,true);}}));
      } catch(e){ toast(e.message,true); }
    };
    const renderCalibration = (c) => {
      if(!c) return;
      const badge=$("calib-badge"); if(!badge) return;
      badge.className="tag "+(c.applied?(c.confidence==="high"?"ok":"warn"):"");
      badge.textContent = c.applied ? `کالیبراسیون فعال ×${c.ratio} (${c.samples} نمونه)`
                                    : `کالیبراسیون غیرفعال (${c.samples}/${c.min_samples} نمونه)`;
      setHTML("calib-note", c.note||"");
    };
    const loadWeek = async () => {
      try{
        const w=await api("/planner/week");
        const t=w.totals||{};
        const rows=w.days.filter(d=>d.tasks||d.fixed_min);
        setHTML("week-box", (rows.length?rows.map(d=>`<div class="list-item"><span class="tag">${esc(RomkaDate.display(d.date))}</span>
          <span class="grow">${d.tasks} کار · ${d.planned_min}′ برنامه · ${d.fixed_min}′ ثابت</span>
          <span class="faint xs">${d.done}/${d.tasks} انجام</span></div>`).join("")
          : `<div class="empty">در ۷ روز گذشته هیچ وظیفه/رویدادی ثبت نشده است.</div>`)
          + `<div class="xs faint" style="margin-top:6px">جمع: ${t.tasks||0} کار · ${t.planned_min||0}′ برنامه‌ریزی · ${t.fixed_min||0}′ ثابت${t.completion_pct!=null?` · تکمیل ${t.completion_pct}%`:""} — ${esc(w.note)}</div>`);
        renderCalibration(w.calibration);
      }catch(e){ setHTML("week-box", errBox(e)); }
    };
    const loadEvents = async () => {
      try { const r = await api("/planner/events?day="+selectedDay());
        setHTML("event-list", r.items.length?r.items.map(x=>`<div class="list-item"><span class="tag warn">#${x.id}</span>
          <span class="grow">${esc(x.title)}</span><span class="faint xs">${hhmm(x.start_min)}–${hhmm(x.end_min)}</span></div>`).join(""):`<div class="empty">رویدادی ثابت نشده.</div>`);
      } catch(e){ toast(e.message,true); }
    };
    const refreshPlan = async () => {
      try { const r = await api("/planner/today?day="+selectedDay()); renderPlan(r.plan); } catch(e){ toast(e.message,true); }
    };
    $("review-btn")?.addEventListener("click",async()=>{
      try{
        const r=await api("/planner/review?day="+selectedDay()+"&mode=night");
        const c=r.counts||{}, tm=r.time||{};
        setHTML("review-box", `<div class="notice ok">${esc(r.summary)}</div>
          <div class="row" style="gap:6px;margin:8px 0"><span class="tag">${c.done}/${c.tasks} انجام</span>
          <span class="tag">${c.events} تعهد ثابت</span>
          <span class="tag ${tm.delta_min>0?"warn":""}">تخمین ${tm.estimated_min}′ / واقعی ${tm.actual_min}′</span>
          ${r.adherence_pct!=null?`<span class="tag">پایبندی ${r.adherence_pct}%</span>`:""}</div>
          ${(r.overruns||[]).map(o=>`<div class="small">• «${esc(o.title)}» ${o.estimated_min}′ تخمین → ${o.actual_min}′ واقعی</div>`).join("")}
          ${(r.warnings||[]).map(w=>notice(w)).join("")}
          <div class="strong" style="margin-top:8px">${r.next_actions?.length?"قدم‌های بعدی:":"کاری برای فردا ثبت نشده."}</div>
          ${(r.next_actions||[]).map(a=>`<div class="small">• ${esc(a.title)} (${a.duration_min}′، ${esc(a.reason)})</div>`).join("")}
          <div class="xs faint" style="margin-top:8px">${esc(r.note)}</div>`);
        renderCalibration(r.calibration);
      }catch(e){ setHTML("review-box", errBox(e)); }
    });
    $("example-btn")?.addEventListener("click",()=>{ $("intake-text").value="امروز باید روی انتشار گپینه کار کنم، نویدبان را بررسی کنم، یک جلسه کاری دارم، خرید کنم و ساعت شش باشگاه بروم."; });
    loadWeek();
    $("intake-btn")?.addEventListener("click",async()=>{
      const t=$("intake-text").value.trim(); if(!t)return toast("متن وارد کنید.",true);
      try { const r=await api("/planner/intake",{body:{text:t,date:selectedDay(),save:$("intake-save").checked}});
        setHTML("intake-parsed",`<div class="notice ok">${r.parsed.detected.length} بخش شناسایی شد · ${r.created_task_ids.length} وظیفه و ${r.created_event_ids.length} رویداد ذخیره شد.</div>
          <div class="small">${r.parsed.chunks.map(esc).join(" · ")}</div>`);
        renderPlan(r.plan); loadTasks(); loadEvents(); toast("برنامه ساخته و اعتبارسنجی شد.");
      } catch(e){ setHTML("intake-parsed",errBox(e)); }
    });
    const gen = async (mode) => {
      try { const r=await api("/planner/generate",{body:{date:selectedDay(),energy_mode:mode}}); renderPlan(r.plan); toast("برنامه محاسبه شد."); }
      catch(e){ toast(e.message,true); }
    };
    $("gen-btn")?.addEventListener("click",()=>gen("normal"));
    $("low-btn")?.addEventListener("click",()=>gen("low"));
    $("replan-btn")?.addEventListener("click",async()=>{
      const id=$("rp-event").value, end=+$("rp-end").value;
      try { const body={date:selectedDay(),extended_events:{},completed_task_ids:[],replan_from_min:end||null};
      if(id&&end) body.extended_events[id]=end;
      const r=await api("/planner/replan",{body}); renderPlan(r.plan);
        const d=r.plan.diff||{}; setHTML("replan-diff",`<div class="notice">نسخه ${r.plan.version} · ${(d.moved||[]).length} کار جابه‌جا شد · ${(d.newly_deferred||[]).length} کار به تعویق افتاد.</div>`);
      } catch(e){ setHTML("replan-diff",errBox(e)); }
    });
    $("add-task-btn")?.addEventListener("click",async()=>{
      const body={title:$("new-task").value.trim(),duration_min:+$("new-dur").value||60,priority:+$("new-pri").value||3};
      const rr=$("new-rrule").value.trim(); if(rr) body.recurrence_rule=rr;
      if(!body.title) return toast("عنوان لازم است.",true);
      try { await api("/planner/tasks",{body}); $("new-task").value=""; loadTasks(); toast("وظیفه افزوده شد."); }
      catch(e){ toast(e.message,true); }
    });
    $("new-rrule")?.addEventListener("change",async()=>{
      const v=$("new-rrule").value.trim(); if(!v)return;
      try { const r=await api("/planner/recurrence?rule="+encodeURIComponent(v)+"&count=6"); setHTML("rrule-preview","تکرارها: "+r.dates.map(RomkaDate.display).join("، ")); }
      catch(e){ setHTML("rrule-preview",esc(e.message)); }
    });
    $("add-event-btn")?.addEventListener("click",async()=>{
      const body={title:$("ev-title").value.trim(),start_min:+$("ev-start").value,end_min:+$("ev-end").value,category:$("ev-cat").value};
      if(!body.title||body.end_min<=body.start_min)return toast("عنوان/زمان نامعتبر است.",true);
      try { await api("/planner/events?day="+selectedDay(),{body}); loadEvents(); toast("رویداد اضافه شد."); } catch(e){ toast(e.message,true); }
    });
    $("plan-date").addEventListener("change", () => { try { selectedDay(); loadEvents(); refreshPlan(); } catch(e) { toast(e.message,true); } });
    loadTasks(); loadEvents(); refreshPlan();
  }

  /* ── agents ── */
  if (page === "agents") {
    loadChrome(); initAnatomy();
    Promise.all([api("/agents"),api("/agents/runs")]).then(([a,r])=>{
      setHTML("a-count",a.items.length); setHTML("a-active",a.items.filter(x=>x.active).length); setHTML("a-version",a.version);
      setHTML("agent-grid",a.items.map(x=>`<div class="agent-card"><div class="agent-avatar" style="color:${esc(x.color)};border-color:${esc(x.color)}55">${esc(x.icon)}</div>
        <div style="flex:1;min-width:0"><div class="row spread"><span class="strong">${esc(specialistText(x.name))}</span>
        <span class="tag ${x.active?"ok":""}">${x.active?"فعال":"غیرفعال"}</span></div>
        <div class="xs faint">${esc(specialistText(x.title))} · v${esc(x.version)}</div>
        <p class="small muted" style="margin:8px 0">${esc(specialistText(x.mission))}</p>
        <div class="xs faint">ابزارها: ${esc(x.allowed_tools.join("، ")||"—")}</div>
        <div class="xs faint">لایه‌های مجاز: ${esc(x.allowed_memory_layers.map(label).join("، "))}</div></div></div>`).join(""));
      setHTML("run-list",r.items.length?r.items.slice(0,12).map(x=>`<div class="list-item"><span class="tag ${x.verdict==="accepted"?"ok":"warn"}">${esc(label(x.verdict))}</span>
        <span class="grow">${esc(x.agent_id)}</span><span class="faint xs">${x.quality_score}</span></div>`).join(""):`<div class="empty">اجرایی ثبت نشده.</div>`);
    }).catch(e=>toast(e.message,true));
  }

  /* ── business ── */
  if (page === "business") {
    loadChrome();
    const load = async () => {
      try { const [p,g,t]=await Promise.all([api("/data/projects"),api("/data/goals"),api("/planner/tasks")]);
        setHTML("project-list",p.items.length?p.items.map(x=>`<div class="list-item" style="flex-wrap:wrap">
          <span class="tag accent">${esc(x.name)}</span><span class="grow">${esc(x.goal||x.description||"")}</span>
          <span class="faint xs">${x.done_tasks}/${x.done_tasks+x.open_tasks} کار</span>
          <div class="progress" style="width:100%;margin-top:6px"><i style="width:${x.progress_pct}%"></i></div></div>`).join(""):`<div class="empty">پروژه‌ای ثبت نشده.</div>`);
        setHTML("goal-list",g.items.length?g.items.map(x=>`<div class="list-item"><span class="tag ${x.priority<=2?"accent":""}">${esc(label(x.horizon))}</span>
          <span class="grow">${esc(x.title)}</span><span class="faint xs">${esc(x.success_metric||"")}</span></div>`).join(""):`<div class="empty">هدفی ثبت نشده.</div>`);
        const done=t.items.filter(x=>x.status==="done").length, total=t.items.length;
        setHTML("biz-insight",`وظایف ثبت‌شده: ${total} · انجام‌شده: ${done} · باز: ${total-done}.
          پیشرفت واقعی ${total?Math.round(100*done/total):0}٪ است. صرفاً افزایش تعداد وظایف، پیشرفت محسوب نمی‌شود؛
          برای هر پروژه یک معیار قابل اندازه‌گیری و یک آزمون هفتگی تعریف کنید.`);
      } catch(e){ toast(e.message,true); }
    };
    $("add-project-btn")?.addEventListener("click",async()=>{
      const body={name:$("proj-name").value.trim(),goal_text:$("proj-goal").value.trim(),priority:+$("proj-pri").value||3};
      if($("proj-due").value.trim()) {
        body.due_date=RomkaDate.toISO($("proj-due").value);
        if(!body.due_date) return toast("موعد شمسی نامعتبر است؛ مثلاً ۱۴۰۵/۰۸/۰۶ وارد کنید.",true);
      }
      if(!body.name)return toast("نام پروژه لازم است.",true);
      try{await api("/data/projects",{body});load();toast("پروژه ساخته شد.");}catch(e){toast(e.message,true);}
    });
    $("add-goal-btn")?.addEventListener("click",async()=>{
      const t=$("goal-title").value.trim(); if(!t)return;
      try{await api("/data/goals",{body:{title:t}});$("goal-title").value="";load();}catch(e){toast(e.message,true);}
    });
    load();
  }

  /* ── health ── */
  if (page === "health") {
    loadChrome();
    const load = async () => {
      try { const r = await api("/fitness/overview");
        if(!r.ready){ setHTML("health-alert",notice(r.message)); return; }
        const e=r.energy;
        setHTML("energy-kpis",[["کالری هدف",e.target_kcal+" کیلوکالری"],["پروتئین",e.protein_g+" گرم"],
          ["کربوهیدرات",e.carbs_g+" گرم"],["چربی",e.fat_g+" گرم"]].map(([l,v])=>`<div class="card flat" style="padding:12px"><div class="kpi"><span class="l">${l}</span><span class="v" style="font-size:18px">${v}</span></div></div>`).join(""));
        setHTML("energy-note",`${e.method} · سوخت پایه ${e.bmr_kcal} · مصرف روزانه ${e.tdee_kcal} · آب پیشنهادی ${e.water_ml} میلی‌لیتر. ${e.disclaimer}`);
        setHTML("workout-meta",`${r.workout.days} جلسه در هفته · ${r.workout.rest_days} روز استراحت`);
        setHTML("workout-plan",r.workout.sessions.map(s=>`<div class="list-item" style="flex-wrap:wrap">
          <span class="tag accent">${esc(s.title)}</span><span class="grow">${esc(s.goal)}</span>
          <div style="width:100%;margin-top:6px" class="small">${s.warmup}</div>
          ${s.exercises.map(x=>`<div style="width:100%;border-top:1px solid var(--border-soft);padding-top:6px;margin-top:6px">
            <div class="strong">${esc(x.name)} — ${x.sets}×${esc(x.reps)}</div>
            <div class="xs faint">${esc(x.target_muscles)} · استراحت ${x.rest_seconds}ث · ${esc(x.intensity)}</div>
            <div class="xs">${esc(x.weight_selection)}</div>
            <div class="xs faint">تکنیک: ${esc(x.technique)} | جایگزین: ${esc(x.alternative)}</div>
            <div class="xs" style="color:var(--warn)">${esc(x.safety)} · ${esc(x.progression_rule)}</div></div>`).join("")}
          <div style="width:100%" class="xs faint">${esc(s.cooldown)}</div></div>`).join(""));
        setHTML("meal-plan",r.meals.meals.map(m=>`<div class="list-item" style="flex-wrap:wrap"><span class="tag">${esc(m.time)}</span>
          <span class="grow strong">${esc(m.title)}</span>
          ${m.items.map(i=>`<div style="width:100%" class="xs">• ${esc(i.name)} — ${esc(i.amount)} · ${i.kcal} کیلوکالری · پروتئین ${i.protein_g} گرم</div>`).join("")}
          <div style="width:100%" class="xs faint">جایگزین: ${esc(m.alternatives.join(" / "))}</div></div>`).join("")+
          `<div class="small faint">${esc(r.meals.note)}</div>`);
        setHTML("log-list",r.logs.length?r.logs.slice(-8).reverse().map(l=>`<div class="list-item"><span class="tag ${l.pain_flag?"danger":""}">${esc(l.exercise)}</span>
          <span class="grow">${l.sets}×${l.reps} @ ${l.weight_kg} کیلوگرم</span><span class="faint xs">RPE ${l.rpe}</span></div>`).join(""):`<div class="empty">جلسه‌ای ثبت نشده.</div>`);
        const pr=Object.entries(r.progression||{});
        if(pr.length) setHTML("prog-result",pr.map(([k,v])=>notice(`${k}: ${v.message}`,v.can_increase?"ok":"warn")).join(""));
      } catch(e){ setHTML("health-alert",errBox(e)); }
    };
    $("assess-btn")?.addEventListener("click",async()=>{
      const split=(id)=>($(id).value||"").split(/[،,]/).map(x=>x.trim()).filter(Boolean);
      const body={age:+$("f-age").value,height_cm:+$("f-height").value,weight_kg:+$("f-weight").value,
        sex:$("f-sex").value,activity:$("f-activity").value,goal:$("f-goal").value,experience:$("f-exp").value,
        days_per_week:+$("f-days").value,session_minutes:60,equipment:split("f-equip"),
        injuries:split("f-injuries"),allergies:split("f-allergies"),food_preferences:[]};
      try{await api("/fitness/assessment",{body});toast("ارزیابی ذخیره شد.");load();}catch(e){toast(e.message,true);}
    });
    $("log-btn")?.addEventListener("click",async()=>{
      const body={exercise:$("l-ex").value.trim(),weight_kg:+$("l-weight").value,sets:+$("l-sets").value,
        reps:+$("l-reps").value,rpe:+$("l-rpe").value,planned_sets:+$("l-planned").value,pain_flag:$("l-pain").checked};
      if(!body.exercise)return toast("حرکت را وارد کنید.",true);
      try{const r=await api("/fitness/logs",{body});const p=r.progression;
        setHTML("prog-result",notice(`${label(p.decision)}: ${p.message} ${p.reasons?.length?"("+p.reasons.join("، ")+")":""}`,p.can_increase?"ok":"warn"));
        toast("جلسه ذخیره شد.");load();}catch(e){toast(e.message,true);}
    });
    load();
  }

  /* ── memory ── */
  if (page === "memory") {
    loadChrome();
    const load = async (q="") => {
      try { const [r,c]=await Promise.all([api("/memory"+(q?"?q="+encodeURIComponent(q):"")),api("/memory/conflicts")]);
        setHTML("mem-conflicts",c.items.length?notice(`${c.items.length} داده متناقض/تأییدنشده دارید. رومکا به‌جای حدس زدن، درباره آنها سؤال می‌کند.`):"");
        setHTML("mem-list",r.items.length?r.items.map(x=>`<div class="list-item" style="flex-wrap:wrap">
          <span class="tag ${x.sensitivity==="sensitive"?"danger":x.confidence==="verified"?"ok":"warn"}">${esc(label(x.layer))}</span>
          <span class="grow"><strong>${esc(x.key)}</strong><div class="xs faint">${esc(JSON.stringify(x.value))}</div></span>
          <span class="faint xs">${esc(label(x.source))} · ${esc(label(x.confidence))}</span>
          <button class="btn sm ghost danger" data-del="${x.id}">حذف</button></div>`).join(""):`<div class="empty">موردی ثبت نشده.</div>`);
        document.querySelectorAll("[data-del]").forEach(b=>b.addEventListener("click",async()=>{
          try{await api(`/memory/${b.dataset.del}`,{method:"DELETE"});load(q);toast("حذف شد.");}catch(e){toast(e.message,true);}
        }));
      } catch(e){ setHTML("mem-list",errBox(e)); }
    };
    $("mem-search")?.addEventListener("click",()=>load($("mem-q").value.trim()));
    $("mem-add")?.addEventListener("click",async()=>{
      let value=$("m-value").value.trim(); try{value=JSON.parse(value);}catch(e){}
      const body={layer:$("m-layer").value,key:$("m-key").value.trim(),value,sensitivity:$("m-sens").value};
      if(!body.key)return toast("کلید لازم است.",true);
      try{await api("/memory",{body});$("m-key").value="";$("m-value").value="";load();toast("ذخیره شد.");}catch(e){toast(e.message,true);}
    });
    $("mem-export")?.addEventListener("click",async()=>{
      try{const r=await api("/memory/export");const blob=new Blob([JSON.stringify(r,null,2)],{type:"application/json"});
        const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="romka-memory.json";a.click();}catch(e){toast(e.message,true);}
    });
    load();
  }

  /* ── settings ── */
  if (page === "settings") {
    loadChrome();
    api("/profile").then(r=>{ if(!r.profile)return;
      const p=r.profile;$("s-wake").value=p.wake_time;$("s-sleep").value=p.sleep_time;$("s-work").value=p.work_start;
      $("s-workend").value=p.work_end;$("s-cap").value=p.daily_focus_capacity_min;$("s-buf").value=p.buffer_pct;
      $("s-commute").value=p.commute_minutes;$("s-tz").value=r.user.timezone||""; $("o-tz")&&($("o-tz").value=r.user.timezone||"");
    }).catch(()=>{});
    $("save-profile")?.addEventListener("click",async()=>{
      const body={timezone:$("s-tz").value,wake_time:+$("s-wake").value,sleep_time:+$("s-sleep").value,
        work_start:+$("s-work").value,work_end:+$("s-workend").value,daily_focus_capacity_min:+$("s-cap").value,
        buffer_pct:+$("s-buf").value,commute_minutes:+$("s-commute").value,
        goals:($("s-goals").value||"").split(/[،,]/).map(x=>x.trim()).filter(Boolean)};
      try{await api("/profile",{method:"PUT",body});toast("پروفایل ذخیره شد.");}catch(e){toast(e.message,true);}
    });
    Promise.all([api("/status"),api("/budget"),api("/skills"),api("/channels/status"),
                 api("/security-events"),api("/actions"),api("/channels/identities")]).then(([s,b,sk,ch,se,ac,ids])=>{
      setHTML("provider-list",(s.providers||[]).map(p=>`<div class="list-item"><span class="tag ${p.available?"ok":"warn"}">${esc(label(p.name))}</span>
        <span class="grow">${esc(p.model||"—")}</span><span class="faint xs">${p.external?(p.verified_live?"خارجی · زنده تأییدشده":"خارجی · زنده تأییدنشده"):"محلی"}</span></div>
        ${p.reason?`<div class="xs warn" style="width:100%">${esc(p.reason)}</div>`:""}`).join(""));
      setHTML("budget-box",`<div class="grid g-2">
        ${[["مصرف روزانه",b.state.daily_spent_usd+" / "+b.state.daily_budget_usd],["مصرف ماهانه",b.state.monthly_spent_usd+" / "+b.state.monthly_budget_usd],
           ["حداکثر فراخوانی",b.state.max_calls_per_request],["حداکثر گام ایجنت",b.state.max_agent_steps]].map(([l,v])=>
          `<div class="card flat" style="padding:12px"><div class="kpi"><span class="l">${l}</span><span class="v" style="font-size:16px">${esc(v)}</span></div></div>`).join("")}</div>
          <p class="small faint" style="margin-top:10px">هیچ فراخوانی مدل نمی‌تواند بدون سقف هزینه ایجاد کند؛ حلقه‌های تکراری متوقف می‌شوند.</p>`);
      setHTML("skills-meta",`${sk.count} کاندیدا · ممیزی ${esc(RomkaDate.display(sk.audit_date))}`);
      const tb=document.querySelector("#skills-table tbody");
      if(tb) tb.innerHTML=sk.items.map(x=>`<tr><td><div class="strong">${esc(x.name)}</div><div class="xs faint">${esc(label(x.domain))}</div></td>
        <td class="xs">${esc(x.license||"—")}</td><td class="mono xs">${esc(x.version||"—")}</td>
        <td>${x.score?.score?.total??"—"}</td><td><span class="tag ${x.status==="active"||x.status==="approved"?"ok":x.status.includes("review")?"warn":""}">${esc(label(x.status))}</span></td>
        <td class="xs">${esc(label(x.risk))}</td>
        <td>${x.status==="active"?`<button class="btn sm ghost" data-roll="${esc(x.slug)}">بازگشت</button>`:
          (x.status==="approved"?`<button class="btn sm" data-act="${esc(x.slug)}">فعال‌سازی</button>`:`<span class="faint xs">—</span>`)}</td></tr>`).join("");
      document.querySelectorAll("[data-act]").forEach(btn=>btn.addEventListener("click",async()=>{
        try{await api(`/skills/${btn.dataset.act}/activate`,{body:{}});toast("فعال شد.");}catch(e){toast(e.message,true);}
      }));
      document.querySelectorAll("[data-roll]").forEach(btn=>btn.addEventListener("click",async()=>{
        try{await api(`/skills/${btn.dataset.roll}/rollback`,{body:{}});toast("بازگشت انجام شد.");}catch(e){toast(e.message,true);}
      }));
      setHTML("channel-list",Object.entries(s.channels||{}).map(([k,v])=>`<div class="list-item"><span class="tag ${v.configured?"ok":"warn"}">${esc(label(k))}</span>
        <span class="grow">${v.configured?"پیکربندی‌شده":"غیرفعال"}</span><span class="faint xs">زنده: ${v.verified_live?"بله":"خیر"}</span></div>`).join(""));
      setHTML("sec-list",se.items.length?se.items.slice(0,12).map(x=>`<div class="list-item"><span class="tag warn">${esc(label(x.event_type))}</span>
        <span class="grow">${esc(x.detail)}</span><span class="faint xs">${esc(RomkaDate.timestamp(x.created_at))}</span></div>`).join(""):`<div class="empty">رخدادی ثبت نشده.</div>`);
      setHTML("act-list",ac.items.length?ac.items.slice(0,12).map(x=>`<div class="list-item"><span class="tag ${x.status==="executed"?"ok":"warn"}">${esc(label(x.status))}</span>
        <span class="grow">${esc(x.tool)} — ${esc(x.goal)}</span>
        ${x.status==="pending_approval"?`<button class="btn sm" data-approve="${x.id}">تأیید</button>`:""}</div>`).join(""):`<div class="empty">اقدامی ثبت نشده.</div>`);
      document.querySelectorAll("[data-approve]").forEach(b=>b.addEventListener("click",async()=>{
        try{await api(`/actions/${b.dataset.approve}/approve`,{body:{},method:"POST"});toast("تأیید و اجرا شد.");}catch(e){toast(e.message,true);}
      }));
      setHTML("ch-list",ids.items.length?ids.items.map(x=>`<div class="list-item"><span class="tag">${esc(label(x.channel))}</span><span class="grow mono">${esc(x.external_id)}</span></div>`).join(""):`<div class="empty">هویتی متصل نشده.</div>`);
    }).catch(e=>{ setHTML("status-list",errBox(e)); });
    $("verify-provider")?.addEventListener("click",async()=>{
      const btn=$("verify-provider"); btn.disabled=true;
      setHTML("provider-verify","<span class=\"faint\">در حال انجام یک فراخوانی آزمایشی…</span>");
      try{
        const r=await api("/providers/verify",{method:"POST",body:{}});
        setHTML("provider-verify", r.verified_live
          ? notice(`اتصال زنده تأیید شد: ${r.provider} / ${r.model} · ${r.latency_ms}ms · ${r.cost_usd}$`,"ok")
          : notice(r.reason || r.error || "اتصال زنده تأیید نشد."));
      }catch(e){ setHTML("provider-verify",errBox(e)); }
      finally{ btn.disabled=false; }
    });
    $("ch-add")?.addEventListener("click",async()=>{
      const body={channel:$("ch-name").value,external_id:$("ch-id").value.trim()};
      if(!body.external_id)return toast("شناسه لازم است.",true);
      try{await api("/channels/identities",{body});toast("اتصال ثبت شد.");location.reload();}catch(e){toast(e.message,true);}
    });
  }

  /* ── onboarding ── */
  if (page === "onboarding") {
    loadChrome();
    $("o-save")?.addEventListener("click",async()=>{
      const body={display_name:$("o-name").value,timezone:$("o-tz").value,wake_time:+$("o-wake").value,
        sleep_time:+$("o-sleep").value,goals:($("o-goals").value||"").split(/[،,]/).map(x=>x.trim()).filter(Boolean),
        energy_drains:($("o-drains").value||"").split(/[،,]/).map(x=>x.trim()).filter(Boolean)};
      try{await api("/profile",{method:"PUT",body});location.href="/";}catch(e){toast(e.message,true);}
    });
  }
})();
