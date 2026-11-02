// node --experimental-websocket shoot.mjs <base> <user> <pass> <outdir> <width> <path>...  (headless Chromium over CDP; real login form)
import { spawn } from 'node:child_process'; import { mkdirSync, writeFileSync, readdirSync } from 'node:fs'; import { join } from 'node:path'; import { homedir } from 'node:os';
const [base, user, pass, out, width, ...paths] = process.argv.slice(2); mkdirSync(out, { recursive: true });
const root = join(homedir(), '.cache/ms-playwright'); const d = readdirSync(root).find(x => x.startsWith('chromium_headless_shell'));
const bin = join(root, d, readdirSync(join(root, d)).find(x => x.startsWith('chrome')), 'chrome-headless-shell');
const port = 9300 + Math.floor(Math.random() * 500);
const proc = spawn(bin, [`--remote-debugging-port=${port}`, '--no-sandbox', '--disable-gpu', `--user-data-dir=${out}/.p${port}`, '--hide-scrollbars', 'about:blank'], { stdio: 'ignore' });
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
for (const p of paths) {
  l = load(); await send('Page.navigate', { url: base + p }); await l; await ev('document.fonts.ready.then(()=>1)'); await sleep(900);
  await size(Math.min(await ev('document.documentElement.scrollHeight'), 2600));
  const s = await send('Page.captureScreenshot', { format: 'png' }); const f = join(out, `${user}${p.replace(/[^a-z0-9]+/gi, '_')}${w}.png`);
  writeFileSync(f, Buffer.from(s.result.data, 'base64')); console.log(f); await size(mob ? 800 : 900);
}
ws.close(); proc.kill();
