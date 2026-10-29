// Wake-word logic with a fake SpeechRecognition: no microphone, no browser.
// The rule under test: listening never starts unless the user opts in, the wake
// word is required before anything is captured, and every stop condition holds.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor(id) {
    this.id = id; this.value = ''; this.textContent = ''; this.hidden = false; this.disabled = false;
    this.checked = false; this.listeners = {}; this.dataset = {}; this.style = {}; this.children = [];
  }
  addEventListener(name, cb) { (this.listeners[name] ||= []).push(cb); }
  setAttribute(name, value) { this[name] = value; }
  getAttribute(name) { return this[name]; }
  focus() {}
  async click() { if (!this.disabled) for (const cb of this.listeners.click || []) await cb({target: this}); }
  async change() { for (const cb of this.listeners.change || []) await cb({target: this}); }
}
const ids = ['voice-widget', 'voice-panel', 'voice-open', 'voice-close', 'voice-mic', 'voice-stop', 'voice-new',
  'voice-status', 'voice-text', 'voice-history', 'voice-auto-speak', 'voice-send', 'voice-read', 'voice-silence',
  'voice-reply', 'voice-confirm', 'voice-action-title', 'voice-action-name', 'voice-duration-field',
  'voice-action-duration', 'voice-action-apply', 'voice-action-cancel', 'voice-plan-confirm', 'voice-plan-apply',
  'voice-plan-cancel', 'voice-today', 'voice-preview', 'logout-btn', 'wake-box', 'wake-enabled', 'wake-words',
  'wake-words-field', 'wake-note', 'wake-start', 'wake-stop', 'wake-status'];
const els = Object.fromEntries(ids.map(id => [id, new Element(id)]));
els['voice-panel'].hidden = true; els['voice-confirm'].hidden = true; els['voice-plan-confirm'].hidden = true;
els['voice-stop'].disabled = true; els['voice-read'].disabled = true;
els['wake-words'].value = 'رومکا, romka, hey romka, سلام رومکا';
els['wake-controls'] = new Element('wake-controls'); els['wake-controls'].hidden = true;
els['wake-words-field'].hidden = true;
els['voice-open'].textContent = 'دستیار صوتی';   // as rendered by base.html

const memory = new Map();
const storage = {
  getItem: k => (memory.has(k) ? memory.get(k) : null),
  setItem: (k, v) => memory.set(k, String(v)),
  removeItem: k => memory.delete(k),
};
const created = [];
let failNextStart = false;
class Recognition {
  constructor() {
    this.lang = ''; this.continuous = false; this.interimResults = false; this.maxAlternatives = 1;
    this.started = false; this.aborted = false; this.stopped = false; created.push(this);
  }
  start() { if (failNextStart) { failNextStart = false; throw new Error('blocked'); } this.started = true; if (this.onstart) this.onstart(); }
  stop() { this.stopped = true; if (this.onend) this.onend(); }
  abort() { this.aborted = true; if (this.onend) this.onend(); }
  speak(transcript) { if (this.onresult) this.onresult({resultIndex: 0, results: [Object.assign([{transcript}], {isFinal: true})]}); }
}
const docListeners = {};
const document = {
  getElementById: id => els[id],
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener: (name, cb) => { (docListeners[name] ||= []).push(cb); },
  fire: (name, event) => { for (const cb of docListeners[name] || []) cb(event); },
  body: {dataset: {}},
  hidden: false,
};
const spoken = [];
const win = {SpeechRecognition: Recognition, document, addEventListener: () => {}, dispatchEvent: () => {},
  location: {assign() {}},
  speechSynthesis: {cancel() {}, getVoices: () => [], speak(u) { spoken.push(u.text); }}};
const sandbox = {window: win, document, sessionStorage: storage, localStorage: storage, fetch: async () => ({ok: true, json: async () => ({})}),
  console, CustomEvent: class {constructor(t) {this.type = t;}}, setTimeout, clearTimeout, setInterval, clearInterval, Date, JSON, Math, Number, String, Array, Object};
vm.runInNewContext(fs.readFileSync('app/web/static/js/voice.js', 'utf8'), sandbox);

const wake = () => win.RomkaVoiceWake();

(async () => {
  // 1) Nothing listens until the user turns it on.
  assert.equal(created.length, 0, 'no recognition on load');
  const initial = wake();
  assert.equal(initial.enabled, false); assert.equal(initial.listening, false); assert.equal(initial.remainingMs, 0);
  assert.equal(els['wake-controls'].hidden, true, 'controls stay hidden until opt-in');
  assert.equal(els['voice-open'].textContent, 'دستیار صوتی');

  // 2) Opt-in starts a continuous listener that waits for the wake word.
  els['wake-enabled'].checked = true;
  await els['wake-enabled'].change();
  assert.equal(created.length, 1, 'one listener after opt-in');
  assert.equal(created[0].continuous, true);
  assert.equal(created[0].interimResults, true);
  assert.equal(created[0].lang, 'fa-IR');
  assert.equal(els['wake-controls'].hidden, false);
  assert.equal(wake().enabled, true);
  assert.equal(wake().listening, true);
  assert.equal(els['voice-open'].textContent.includes('گوش می‌دهم'), true, 'the floating button says it is listening');
  assert.equal(els['voice-mic'].disabled, true, 'push-to-talk cannot compete with the wake listener');

  // 3) Ordinary speech must not open the panel or capture anything.
  created[0].speak('امروز هوا خوب است');
  assert.equal(els['voice-panel'].hidden, true, 'panel stays closed without the wake word');
  assert.equal(created.length, 1, 'no command capture started');

  // 4) The wake word opens the panel and starts exactly one command capture.
  created[0].speak('رومکا برنامه امروز');
  await new Promise(r => setTimeout(r, 220));
  assert.equal(els['voice-panel'].hidden, false, 'panel opened by the wake word');
  assert.equal(created.length, 2, 'command capture started once');
  assert.equal(created[1].continuous, false, 'command capture is push-to-talk, not continuous');
  assert.equal(els['wake-status'].textContent.includes('رومکا فعال شد'), true, 'the wake line reports the activation');
  assert.match(els['voice-status'].textContent, /ضبط/, 'the main status moves on to the capture prompt');
  assert.equal(wake().enabled, true, 'consent stays on after one command');
  assert.equal(wake().listening, false, 'the wake listener yielded to push-to-talk');
  assert.equal(els['wake-enabled'].checked, true, 'the toggle keeps showing the consent');

  // 5) The transcribed command is never sent on its own.
  created[1].speak('برنامه امروز');
  assert.equal(els['voice-text'].value.includes('برنامه امروز'), true, 'text waits for review');

  // 6) When push-to-talk ends, the wake listener re-arms while consent is on.
  created[1].stop();
  await new Promise(r => setTimeout(r, 400));
  assert.equal(created.length, 3, 'the wake listener re-armed after the command');
  assert.equal(wake().listening, true);
  assert.equal(created[2].continuous, true, 're-armed listener waits for the wake word again');

  // 7) Opt-in is per browser and survives a reload.
  assert.equal(storage.getItem('romka.voice.wake.v1'), 'on', 'consent is remembered in this browser only');
  els['wake-enabled'].checked = true; await els['wake-enabled'].change();
  assert.equal(storage.getItem('romka.voice.wakewords.v1').length > 0, true, 'wake words are remembered');

  // 8) A hidden tab stops listening immediately.
  document.hidden = true;
  document.fire('visibilitychange');
  assert.equal(wake().enabled, false, 'hidden tab stops the wake listener');
  assert.equal(els['wake-enabled'].checked, false);

  // 9) A denied microphone turns the feature off instead of retrying forever.
  els['wake-enabled'].checked = true; await els['wake-enabled'].change();
  const denied = created[created.length - 1];
  denied.onerror({error: 'not-allowed'});
  assert.equal(wake().enabled, false, 'not-allowed stops the feature');
  assert.equal(els['wake-status'].textContent.includes('اجازه'), true);

  // 10) A blocked start() leaves the toggle off rather than a half-on state.
  failNextStart = true;
  els['wake-enabled'].checked = true; await els['wake-enabled'].change();
  assert.equal(els['wake-enabled'].checked, false, 'a failed start resets the toggle');
  assert.equal(wake().listening, false);

  // 11) Stopping by hand is always possible and leaves no listener behind.
  els['wake-enabled'].checked = true; await els['wake-enabled'].change();
  assert.equal(wake().listening, true);
  await els['wake-stop'].click();
  assert.equal(wake().enabled, false);
  assert.equal(wake().listening, false);
  assert.equal(created[created.length - 1].aborted, true, 'listener aborted, not left running');

  assert.equal(spoken.length, 0, 'the wake word never speaks on its own');
  console.log('wake-word widget: all checks passed');
})().catch(e => { console.error(e); process.exit(1); });
