// (crawler variant, see page_audit.mjs)
// node --experimental-websocket shoot.mjs <base> <user> <pass> <outdir> <width> <path>...  (headless Chromium over CDP; real login form)
import { spawn } from 'node:child_process'; import { mkdirSync, writeFileSync, readdirSync, mkdtempSync, rmSync } from 'node:fs'; import { join } from 'node:path'; import { homedir, tmpdir } from 'node:os';
const [base, user, passArg, out, width, maxPages = '60'] = process.argv.slice(2);
const pass = passArg === '@env' ? (process.env.EIP_AUDIT_PASS || '') : passArg;   // '@env' keeps the password out of the process list mkdirSync(out, { recursive: true });
const root = join(homedir(), '.cache/ms-playwright'); const d = readdirSync(root).find(x => x.startsWith('chromium_headless_shell'));
const bin = join(root, d, readdirSync(join(root, d)).find(x => x.startsWith('chrome')), 'chrome-headless-shell');
const profile = mkdtempSync(join(tmpdir(), 'eip-shot-'));   // temporary browser profile (cookies) outside the screenshots folder, removed at the end
const port = 9300 + Math.floor(Math.random() * 500);
process.on('exit', () => { try { rmSync(profile, { recursive: true, force: true }); } catch {} });   // also after a crash
const proc = spawn(bin, [`--remote-debugging-port=${port}`, '--no-sandbox', '--disable-gpu', `--user-data-dir=${profile}`, '--hide-scrollbars', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms)); let t;
for (let i = 0; i < 50; i++) { try { t = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); if (t.length) break; } catch {} await sleep(200); }
const ws = new WebSocket(t.find(x => x.type === 'page').webSocketDebuggerUrl); await new Promise(r => ws.addEventListener('open', r, { once: true }));
let id = 0; const pend = new Map(); const waiters = [];
ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } if (m.method === 'Page.loadEventFired') waiters.splice(0).forEach(r => r()); });
const send = (method, params = {}) => new Promise(r => { const n = ++id; pend.set(n, r); ws.send(JSON.stringify({ id: n, method, params })); });
const load = () => new Promise(r => waiters.push(r));
const ev = async x => (await send('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true })).result?.result?.value;
const w = +width, mob = w < 600, size = h => send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: mob });
await send('Page.enable'); await size(mob ? 800 : 900);
let l = load(); await send('Page.navigate', { url: base + '/login/' }); await l; await sleep(400);
if (user !== '-') { l = load(); await ev(`(()=>{const f=document.querySelector('form');f.username.value=${JSON.stringify(user)};f.password.value=${JSON.stringify(pass)};f.submit()})()`); await l; await sleep(400); }

// Page audit: log in once, crawl same-origin GET links breadth-first (never logout / downloads), and report per page: HTTP status,
// horizontal overflow, Gregorian dates in visible text, JavaScript errors, missing title. Prints one JSON line per page; exit code 1
// if any page fails. Temporary browser profile only (see above).
const statuses = new Map(); const jsErrors = [];
ws.addEventListener('message', e => { const m = JSON.parse(e.data);
  if (m.method === 'Network.responseReceived' && m.params.type === 'Document') statuses.set(m.params.response.url, m.params.response.status);
  if (m.method === 'Runtime.exceptionThrown') jsErrors.push(m.params.exceptionDetails.text); });
await send('Network.enable'); await send('Runtime.enable');
const seen = new Set(['/login/', '/logout/']); const patterns = new Set(); /* one page per URL shape: /students/7/360/ and /students/8/360/ count once */ const queue = ['/dashboard/']; const results = []; let failed = 0;
const SKIP = /logout|download|template|\.xlsx|\/media\/|\/static\/|\/admin\//;
while (queue.length && results.length < +maxPages) {
  const p = queue.shift(); jsErrors.length = 0;
  l = load(); await send('Page.navigate', { url: base + p }); await l; await ev('document.fonts.ready.then(()=>1)'); await sleep(350);
  const info = await ev(`(()=>{const t=document.body.innerText;const links=[...document.querySelectorAll('a[href^="/"]')].map(a=>a.getAttribute('href').split('#')[0]);
    return {url:location.pathname+location.search,title:document.title,sw:document.documentElement.scrollWidth,iw:innerWidth,
    greg:(t.match(/(?<![\\d.])(19|20)\\d{2}[-\\/](0?[1-9]|1[0-2])[-\\/](0?[1-9]|[12]\\d|3[01])(?![\\d])/g)||[]).length,links}})()`);
  const final = base + info.url.split('?')[0];      // after redirects (for example /dashboard/ -> the role's home)
  const status = [...statuses].reverse().find(([u]) => u.startsWith(final))?.[1] ?? 0;
  const problems = [];
  if (status >= 400 || status === 0) problems.push('status ' + status);
  if (info.sw > info.iw + 1) problems.push(`overflow ${info.sw}>${info.iw}`);
  if (info.greg) problems.push(`gregorian dates ${info.greg}`);
  if (jsErrors.length) problems.push('js ' + jsErrors[0]);
  if (!info.title || info.title.trim() === '') problems.push('no title');
  if (problems.length) failed++;
  results.push({ path: p, ok: !problems.length, problems }); console.log(JSON.stringify({ user, path: p, status, problems }));
  for (const href of info.links) { const shape = href.split('?')[0].replace(/\d+/g, 'N'); if (SKIP.test(href) || seen.has(href) || patterns.has(shape) || href === '/') continue; seen.add(href); patterns.add(shape); queue.push(href); }
}
console.log(JSON.stringify({ user, pages: results.length, failed }));
ws.close(); proc.kill(); await sleep(300); rmSync(profile, { recursive: true, force: true });
process.exit(failed ? 1 : 0);
