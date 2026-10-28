/* Calendar presentation only. API and database dates remain ISO Gregorian. */
(function (root) {
  "use strict";
  const parts = new Intl.DateTimeFormat("en-US-u-ca-persian-nu-latn", {
    timeZone: "UTC", year: "numeric", month: "numeric", day: "numeric"
  });
  function fields(date) {
    const p = Object.fromEntries(parts.formatToParts(date).map(x => [x.type, x.value]));
    return [+p.year, +p.month, +p.day];
  }
  function normalize(s) {
    return String(s).replace(/[۰-۹٠-٩]/g, c => String(c.charCodeAt(0) - (c.charCodeAt(0) >= 0x6f0 ? 0x6f0 : 0x660))).trim();
  }
  function fromISO(iso) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || "")) return "";
    const d = new Date(iso + "T00:00:00Z");
    if (Number.isNaN(d.valueOf()) || d.toISOString().slice(0, 10) !== iso) return "";
    const [y, m, day] = fields(d);
    return `${y}/${String(m).padStart(2, "0")}/${String(day).padStart(2, "0")}`;
  }
  function toISO(input) {
    const match = normalize(input).match(/^(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})$/);
    if (!match) return null;
    const target = match.slice(1).map(Number);
    if (target[1] < 1 || target[1] > 12 || target[2] < 1 || target[2] > 31) return null;
    // Binary search Gregorian days; round-trip check rejects non-existent leap days.
    let lo = Date.UTC(1900, 0, 1) / 86400000, hi = Date.UTC(2200, 11, 31) / 86400000;
    while (lo <= hi) {
      const mid = Math.floor((lo + hi) / 2), f = fields(new Date(mid * 86400000));
      const cmp = f[0] - target[0] || f[1] - target[1] || f[2] - target[2];
      if (cmp === 0) return new Date(mid * 86400000).toISOString().slice(0, 10);
      if (cmp < 0) lo = mid + 1; else hi = mid - 1;
    }
    return null;
  }
  function todayTehran(now = new Date()) {
    const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Tehran", year: "numeric", month: "2-digit", day: "2-digit"
    }).formatToParts(now).map(x => [x.type, x.value]));
    return `${p.year}-${p.month}-${p.day}`;
  }
  function display(iso) {
    const s = fromISO(iso);
    return s ? s.replace(/\d/g, c => "۰۱۲۳۴۵۶۷۸۹"[+c]) : "—";
  }
  function timestamp(s) {
    if (!s) return "—";
    const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(s) ? s : s + "Z");
    if (Number.isNaN(d.valueOf())) return "—";
    return new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
      timeZone: "Asia/Tehran", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hour12: false
    }).format(d);
  }
  const api = {fromISO, toISO, display, todayTehran, timestamp};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.RomkaDate = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
