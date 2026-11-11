#!/usr/bin/env node
// Regression for research/OM5II-IMAGE-STORE-FAULT-2026-11-11.md. Bounded OM-Emu GUI sessions, not a camera test.
//   node research/test_om5ii_image_stores.mjs OM_EMU_DIR STOCK_MAIN STOCK_RES FAILED_DIR FIXED_DIR
// STOCK_*: expanded stock main and the stock resource block. FAILED_DIR / FIXED_DIR: `oly_patch.py --decoded` outputs
// of commit 25a336e (package e2ca5b28..., the 8 November camera failure) and of the current source.
import { spawnSync } from 'node:child_process';
import assert from 'node:assert/strict';
import path from 'node:path';
import os from 'node:os';
import fs from 'node:fs';

const [emu, stockMain, stockRes, failed, fixed] = process.argv.slice(2);
if (!fixed) throw new Error('usage: OM_EMU_DIR STOCK_MAIN STOCK_RES FAILED_DIR FIXED_DIR');
const tool = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../tools/om5ii_ui_session.mjs');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'om5ii-stores-'));
function session(main, res, keys, tag) {
  const p = spawnSync(process.execPath, ['--max-old-space-size=10240', tool, emu, main, res, path.join(tmp, tag), keys, '--ready', '--watch', '--json'],
    { encoding: 'utf8', env: { ...process.env, OM_EMU_MODEL: 'E148' }, maxBuffer: 1 << 26 });
  assert.equal(p.status, 0, p.stdout.slice(-2000) + p.stderr.slice(-2000));
  return JSON.parse(p.stdout.split('\n').find((l) => l.startsWith('JSON ')).slice(5));
}
const pcs = (r) => new Set(r.image_stores.map(([k]) => parseInt(k.split(' -> ')[0], 16)));
const dests = (r) => new Set(r.image_stores.map(([k]) => parseInt(k.split(' -> ')[1], 16)));
// Open the Super Control Panel, its Picture Mode direct screen, walk right onto Color Profile 1-3, open the colour
// page, switch axis twice with Delete, leave through the menu.
const WALK = 'ok ok right right right right right right right right right down delete delete up menu menu';
const STOCK_STORE_PC = 0x60d52ed0;     // stock GUI code: its own section-7 words 0x61110d0c.. and 0x61111114..

const stock = session(stockMain, stockRes, WALK, 'stock');
assert.deepEqual([...pcs(stock)], [STOCK_STORE_PC], 'stock stores into its image from one site only');

// Negative control: the build that failed on the camera stores into sections 2 and 6 on the first highlight move.
const bad = session(path.join(failed, 'decoded/0100.bin'), path.join(failed, 'decoded/0101.bin'), WALK, 'failed');
const badDest = dests(bad);
assert.ok(badDest.has(0x605af575), 'failed build: cached store into section 2 (refresh_profile)');
assert.ok(badDest.has(0xa0ca7ff8), 'failed build: store into section 6 tail (busy)');
assert.ok(badDest.has(0xa0ca7fc0), 'failed build: store into section 6 tail (axis)');
const firstMove = bad.steps.findIndex((l) => l.startsWith('right:'));
assert.ok(firstMove > 0);

for (const [keys, tag, armed] of [[WALK, 'fixed-unarmed', false], ['s1 ' + WALK, 'fixed-armed', true]]) {
  const r = session(path.join(fixed, 'decoded/0100.bin'), path.join(fixed, 'decoded/0101.bin'), keys, tag);
  assert.deepEqual([...pcs(r)], [STOCK_STORE_PC], `${tag}: no store into the loaded image except stock's own`);
  const writers = r.handle.filter(([k]) => k.endsWith(' w'));
  assert.equal(writers.length, armed ? 1 : 0, `${tag}: handle written ${armed ? 'once, by arm_gate' : 'never'}`);
  for (const [k] of r.handle) {
    const pc = parseInt(k, 16);
    assert.ok(pc >= 0x613f2ed8 && pc < 0x613f3000, `${tag}: handle word touched only by .st8 (pc ${k})`);
  }
  // Same screens as the failed build drew (carousel and labels are unchanged data); when armed the axis title changes
  const names = r.steps.map((l) => l.split(' ').slice(0, 3).join(' '));
  assert.ok(names.filter((n) => n.includes('ID_ST_DIRECT_PICTUREMODE_ART')).length >= 12);
  const frames = r.steps.map((l) => l.split(' ')[3]);
  const del = r.steps.map((l, i) => [l, i]).filter(([l]) => l.startsWith('delete:')).map(([, i]) => i);
  const changed = frames[del[0]] !== frames[del[0] - 1] && frames[del[1]] !== frames[del[0]];
  assert.equal(changed, armed, `${tag}: Delete ${armed ? 'cycles the axis' : 'is inert before the first half-press'}`);
}
fs.rmSync(tmp, { recursive: true, force: true });
console.log(JSON.stringify({ sessions: 4, stock_store_site: '0x60d52ed0', failed_build_image_stores: [...badDest].filter((a) => !dests(stock).has(a)).map((a) => '0x' + a.toString(16)),
  fixed_build_image_stores: 0, limitation: 'OM-Emu GUI sessions with explicit section-ready bits; no camera, loader, ISP or second CPU.' }, null, 2));
