#!/usr/bin/env node
// Execute both native address guards at interval boundaries and across aliases.
// node research/test_om5i_flash_guard.mjs OM_EMU E144-main E148-main PORT-main
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

const [emu, recipientFile, donorFile, portFile] = process.argv.slice(2);
if (!portFile) throw Error('Supply OM-Emu, both expanded stock images and port expanded image');
process.env.OM_EMU_MODEL = 'E144';
const mod = p => import(pathToFileURL(path.resolve(emu, p)).href);
const { createMachine } = await mod('emu/src/machine.mjs');
const { R, PC, step } = await mod('emu/src/core/cpu.mjs');
const [recipient, donor, port] = [recipientFile, donorFile, portFile].map(p => fs.readFileSync(p));
assert.equal(createHash('sha256').update(recipient).digest('hex'),
  '692f1b9eb6f89fe6467ade3c88092305b0423ac1aa6ba759eac83b6cd5d36487');
assert.equal(createHash('sha256').update(donor).digest('hex'),
  '7ae7d4c60990cc859c070e0ceb6cbe612f9c5b260713f2f1256e51d137851c61');
const base = 0x60021020, start = 0x60021714, end = 0x6002182c;
const returns = new Set([0x60021726, 0x6002173b, 0x6002174c, 0x6002175a,
  0x6002176f, 0x60021784, 0x60021792, 0x600217a0, 0x600217b5, 0x600217ca,
  0x600217d8, 0x600217e6, 0x600217fb, 0x60021810, 0x6002181e]);
// Branch at 0x6002182a has two exits: the next guard and the later continuation.
const exits = new Set([...returns, end, 0x60021889]);
const m = createMachine({ rom: new Uint8Array(0) });
function run(image, address, length) {
  m.dbgWrite(start, image.subarray(start-base, end-base));
  R.fill(0); R[PC] = start; R[6] = address; R[3] = length;
  for (let i=0; i<100; i++) {
    const pc = R[PC] >>> 0;
    if (exits.has(pc)) return pc;
    step();
  }
  throw Error('Native guard did not reach a bounded exit');
}
let cases = 0, negativeControls = 0;
for (const boundary of [0x40060000, 0x40780000, 0x41f40000, 0x42140000,
                       0x463c0000, 0x46620000, 0x469e0000, 0x46c40000, 0x50000000]) {
  for (const alias of [0, 0x40000000]) for (const delta of [-4, -1, 0, 1, 4])
    for (const size of [0, 1, 4, 16, 0x1000]) {
      const address = boundary+alias+delta;
      const expected = run(recipient, address, size);
      assert.equal(run(port, address, size), expected, `${address.toString(16)} + ${size}`);
      if (run(donor, address, size) !== expected) negativeControls++;
      cases++;
    }
}
assert.ok(negativeControls > 0, 'Unadapted donor must disagree at recipient boundaries');
console.log(JSON.stringify({native_boundary_cases: cases, unadapted_donor_disagreements: negativeControls,
  scope: 'Native range-guard exits only; no physical NAND, updater, controller or full camera boot.'}, null, 2));
