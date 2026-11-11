#!/usr/bin/env node
// Drive OM-Emu's headless player on an arbitrary (stock or patched) expanded E148 main and resource block:
// the firmware's own GUI, key by key, with optional watchpoints over the loaded image.
//   OM_EMU_MODEL=E148 node tools/om5ii_ui_session.mjs OM_EMU_DIR MAIN.bin RES.bin OUT_DIR 'key key ...' [options]
// keys: ok menu up down left right info delete s1 s2 play ... (OM-Emu key ids); wait:MS idles.
// --ready     publish all ten section-completion bits (0xa26e2694) after the start; OM-Emu does not run E148's loader
// --watch     log every store into the loaded main image (both aliases) and every access to the state handle word
// --peek=ADDR:LEN  print guest memory after each step
// --json      print one JSON summary line at the end (used by research/test_om5ii_image_stores.mjs)
// A PNG of the composite is written per step (channel order is the compositor's, not display RGB).
// This is bounded emulation: no ISP, no C3D wheel, no real loader, cache or second CPU. Not a camera test.
import fs from 'node:fs'; import path from 'node:path'; import zlib from 'node:zlib';
import { createHash } from 'node:crypto'; import { pathToFileURL } from 'node:url';
const [emu, mainP, resP, outDir, script, ...opts] = process.argv.slice(2);
const J = pathToFileURL(path.resolve(emu, 'emu')).href;
const { expandImage } = await import(J + '/src/fw/expand.mjs');
const { Player } = await import(J + '/src/lab/player.mjs');
const { PLAYER_PARSER } = await import(J + '/scenarios/session_replay.mjs');
fs.mkdirSync(outDir, { recursive: true });
const rom = expandImage(new Uint8Array(fs.readFileSync(mainP)));
const resBlock = new Uint8Array(fs.readFileSync(resP));
const env = { rom, resBlock, createHash, deflate: (b, l) => new Uint8Array(zlib.deflateSync(b, { level: l })), inflate: (b) => new Uint8Array(zlib.inflateSync(b)) };
const pl = new Player({ ...PLAYER_PARSER, no_browser: true, idle: 'off', a15: 'on', out: outDir, no_wait_on_error: true, device: 'tft' }, { ...env, wallClock: () => performance.now() / 1000 });
pl.open_session();
const s = pl.session, lab = s.lab;
globalThis.__s = s;
const crc = (() => { const t = new Int32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c; } return (b) => { let c = -1; for (const x of b) c = t[(c ^ x) & 255] ^ (c >>> 8); return (c ^ -1) >>> 0; }; })();
function png(w, h, rgba, file) {
  const raw = Buffer.alloc((w * 4 + 1) * h);
  for (let y = 0; y < h; y++) { raw[y * (w * 4 + 1)] = 0; Buffer.from(rgba.buffer, rgba.byteOffset + y * w * 4, w * 4).copy(raw, y * (w * 4 + 1) + 1); for (let x = 0; x < w; x++) raw[y * (w * 4 + 1) + 4 + x * 4] = 255; }
  const chunk = (t, d) => { const b = Buffer.alloc(12 + d.length); b.writeUInt32BE(d.length); b.write(t, 4); d.copy(b, 8); b.writeUInt32BE(crc(b.subarray(4, 8 + d.length)), 8 + d.length); return b; };
  const ih = Buffer.alloc(13); ih.writeUInt32BE(w); ih.writeUInt32BE(h, 4); ih[8] = 8; ih[9] = 6;
  fs.writeFileSync(file, Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ih), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]));
}
let n = 0; const log = [];
const shot = (name) => { try { const [w, h, raw] = s.frame('boundary', true); const f = path.join(outDir, `${String(n).padStart(2, '0')}-${name}.png`); png(w, h, raw, f); return createHash('sha256').update(raw).digest('hex').slice(0, 12); } catch (e) { return 'frame error: ' + e.message.split('\n')[0].slice(0, 160); } };
const st = () => `0x${lab.state().toString(16)} ${lab.state_names.get(lab.state()) ?? '?'}`;
const press = (k) => { s.key(k, 'down'); s.camapp.pump(); s.idle_slice(lab.lab_time() + 150e6); s.key(k, 'up'); s.camapp.pump(); s.idle_slice(lab.lab_time() + 1200e6); };
const hex = (v) => '0x' + (v >>> 0).toString(16);

const M = lab.sim?.m ?? lab.m; const hits = new Map(); const handle = new Map(); let sample = null;
if (opts.includes('--watch')) {
  // every store into the loaded main image, through either alias (the image is 0x17c0000 bytes at 0x60021020)
  M.setWatchpoints([{ id: 1, lo: 0x60021020, hi: 0x617e1020, kind: 2, stop: false }, { id: 2, lo: 0xa0021020, hi: 0xa17e1020, kind: 2, stop: false }, { id: 3, lo: 0x6218c2fe, hi: 0x6218c300, kind: 3, stop: false }, { id: 4, lo: 0xa218c2fe, hi: 0xa218c300, kind: 3, stop: false }],
    { onLog: (r) => { sample ??= r; if (r.id >= 3) { const k2 = hex(r.pc) + ' ' + r.dir; handle.set(k2, (handle.get(k2) ?? 0) + 1); return; } const k = hex(r.pc ?? 0) + ' -> ' + hex(r.addr ?? r.address ?? 0); hits.set(k, (hits.get(k) ?? 0) + 1); } });
}
const peeks = opts.filter((o) => o.startsWith('--peek=')).map((o) => o.slice(7).split(':'));
const peek = () => peeks.length ? ' peek ' + peeks.map(([a, n]) => a + '=' + Buffer.from(M.dbgRead(parseInt(a, 16), Number(n ?? 4))).toString('hex')).join(' ') : '';
const report = (tag) => { if (!opts.includes('--watch')) return; console.log(`  [image stores so far @${tag}] ${hits.size ? [...hits].map(([k, v]) => k + ' x' + v).join('; ') : 'none'}`); };
try {
  s.idle_slice(lab.lab_time() + 1500e6);
  if (opts.includes('--ready')) (lab.sim?.m ?? lab.m).dbgWrite(0xa26e2694, new Uint8Array([0xff, 0x03, 0, 0]));
  console.log(`start: ${st()} ${shot('start')}`); n++;
  for (const tok of script.split(/\s+/).filter(Boolean)) {
    if (tok.startsWith('wait:')) { s.idle_slice(lab.lab_time() + Number(tok.slice(5)) * 1e6); }
    else press(tok);
    { const line = `${tok}: ${st()} ${shot(tok.replace(':', '_'))}${peek()}`; log.push(line); console.log(line); } n++; report(tok);
  }
if (opts.includes('--watch')) console.log('  [handle word accesses by pc] ' + ([...handle].map(([k, v]) => k + ' x' + v).join('; ') || 'none'));
  if (opts.includes('--json')) console.log('JSON ' + JSON.stringify({ image_stores: [...hits], handle: [...handle], steps: log }));
} catch (e) { console.log('STOP: ' + String(e.stack ?? e).split('\n').slice(0, 12).join('\n')); process.exitCode = 1; }
