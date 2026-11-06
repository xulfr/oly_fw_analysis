#!/usr/bin/env node
// Native MN103 guard execution with explicit loader words, not a camera boot.
// node research/test_om5ii_startup_guards.mjs /path/to/om-emu BEFORE.bin AFTER.bin
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';

process.env.OM_EMU_MODEL = 'E148';
const [emu, beforePath, afterPath] = process.argv.slice(2);
if (!afterPath) throw Error('Supply OM-Emu checkout, before and after expanded images');
const mod = async p => import(pathToFileURL(path.resolve(emu, p)).href);
const { createMachine } = await mod('emu/src/machine.mjs');
const { R, PC, step } = await mod('emu/src/core/cpu.mjs');
const before = fs.readFileSync(beforePath), after = fs.readFileSync(afterPath);
const base = 0x60021020;
assert.equal(before.length, after.length);
// The fix is exactly three readiness-address operands. Features, ND and OSD
// are not replaced by no-op hooks to make the regression pass.
const differences = [];
for (let i = 0; i < before.length; i++) if (before[i] !== after[i]) {
  assert.equal(before[i], 0x98); assert.equal(after[i], 0x94);
  differences.push(base+i);
}
assert.equal(differences.length, 3);
const word = n => { const b = Buffer.alloc(4); b.writeUInt32LE(n); return b; };

function runGuard(image, submitted, ready, entry, stops, d0=111) {
  const m = createMachine({ rom: new Uint8Array(0) });
  m.dbgWrite(base, image);
  m.dbgWrite(0xa26e2698, word(submitted));
  m.dbgWrite(0xa26e2694, word(ready));
  // Zero busy demonstrates a legal RAM value before the decoder reaches it.
  m.dbgWrite(0xa0ca7ff8, new Uint8Array([0]));
  R.fill(0); R[PC] = entry; R[0] = d0; R[1] = 1; R[8] = 0x62010000;
  for (let i = 0; i < 100; i++) {
    const pc = R[PC] >>> 0;
    if (stops.includes(pc)) return pc;
    step();
  }
  throw Error('Guard failed to reach an expected continuation');
}
const stock = 0x602d19bb, extension = 0x602d000d;
const wb = (img, submitted, ready) => runGuard(img, submitted, ready,
    0x602d19b6, [stock, extension]);
// Negative control: the exact failed source enters extension logic while the
// decoder has only accepted the job. Completed word remains zero.
assert.equal(wb(before, 0x20, 0), extension);
assert.equal(wb(after, 0x20, 0), stock);
assert.equal(wb(after, 0, 0), stock);
assert.equal(wb(after, 0x20, 0x20), extension);
// Other sections' completed bits do not authorise section 6.
assert.equal(wb(after, 0xff, 0xdf), stock);
const resetStock = 0x602db536, resetExtension = 0x602f4c5b;
const reset = (img, ready) => runGuard(img, 0x20, ready,
    0x602db531, [resetStock, resetExtension], 1);
assert.equal(reset(before, 0), resetExtension);
assert.equal(reset(after, 0), resetStock);
assert.equal(reset(after, 0x20), resetExtension);
// Execute the two native publication sequences themselves. These are distinct
// words; setting SUBMITTED does not set READY. The caller/task schedule and
// hardware decoder are deliberately outside this small regression.
{
  const m = createMachine({ rom: new Uint8Array(0) });
  m.dbgWrite(base, after);
  m.dbgWrite(0xa26e2694, Buffer.alloc(8));
  R.fill(0); R[PC] = 0x600464ba; R[3] = 5;
  for (let n=0; (R[PC] >>> 0) !== 0x600464cd && n<20; n++) step();
  assert.equal(R[PC] >>> 0, 0x600464cd);
  assert.equal(Buffer.from(m.dbgRead(0xa26e2698, 4)).readUInt32LE(), 0x20);
  assert.equal(Buffer.from(m.dbgRead(0xa26e2694, 4)).readUInt32LE(), 0);
  R[PC] = 0x600465be; R[2] = 0x20;
  for (let n=0; (R[PC] >>> 0) !== 0x600465cc && n<20; n++) step();
  assert.equal(R[PC] >>> 0, 0x600465cc);
  assert.equal(Buffer.from(m.dbgRead(0xa26e2694, 4)).readUInt32LE(), 0x20);
}
console.log(JSON.stringify({ native_guard_cases: 8, failed_image_negative_controls: 2,
  native_publication_sequences: 2,
  changed_addresses: differences.map(a => '0x'+a.toString(16)),
  limitation: 'Explicit loader/RAM states; no physical boot, cache or decompressor model.' }, null, 2));
