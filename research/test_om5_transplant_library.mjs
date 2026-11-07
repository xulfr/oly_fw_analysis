#!/usr/bin/env node
// A bounded native compatibility test, not a boot simulation.
// node research/test_om5_transplant_library.mjs OM_EMU E144-expanded.bin E148-expanded.bin
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

const [emu, recipientFile, donorFile] = process.argv.slice(2);
if (!donorFile) throw Error('Supply OM-Emu checkout and both expanded stock images');
process.env.OM_EMU_MODEL = 'E144';
const mod = p => import(pathToFileURL(path.resolve(emu, p)).href);
const { createMachine } = await mod('emu/src/machine.mjs');
const { R, PC, step } = await mod('emu/src/core/cpu.mjs');
const { imageBase, resetHead, coreByte, vectorPage, kernelCpus, modeDial } =
    await mod('emu/src/fw/facts.mjs');
const images = { E144: fs.readFileSync(recipientFile), E148: fs.readFileSync(donorFile) };
const pins = {
  E144: '692f1b9eb6f89fe6467ade3c88092305b0423ac1aa6ba759eac83b6cd5d36487',
  E148: '7ae7d4c60990cc859c070e0ceb6cbe612f9c5b260713f2f1256e51d137851c61',
};
const facts = {};
for (const [name, img] of Object.entries(images)) {
  assert.equal(createHash('sha256').update(img).digest('hex'), pins[name]);
  const head = resetHead(img);
  facts[name] = {
    base: imageBase(img), flashBase: head.flash_base, copies: head.copies,
    library: head.library, coreByte: coreByte(img, 0x8ff00000, 0x1000),
    vectors: vectorPage(img), cpus: kernelCpus(img), dial: modeDial(img).names,
  };
  assert.deepEqual(head.library.image, [0x1681fe0, 0x1800, 0x800]);
}
for (const key of ['base', 'flashBase', 'library', 'coreByte', 'vectors', 'cpus', 'dial'])
  assert.deepEqual(facts.E144[key], facts.E148[key], key);
// Same locations do not mean the resident library has the same entry points.
const entries = { E144: 0x4700114b, E148: 0x47001154 };
const returns = { E144: 0x470011bf, E148: 0x470011c8 };
const destination = 0x62010000;
function fill(libraryModel, callerModel, value, size, staleD2 = 0x12345678) {
  const m = createMachine({ rom: new Uint8Array(0) });
  m.dbgWrite(0x47000800, images[libraryModel].subarray(0x1681fe0, 0x1681fe0+0x1800));
  m.dbgWrite(destination-4, Buffer.alloc(40, 0xa5));
  R.fill(0); R[PC] = entries[callerModel];
  R[0] = value; R[1] = size; R[2] = staleD2; R[4] = destination; R[8] = 0x62020000;
  let steps = 0;
  while ((R[PC] >>> 0) !== returns[libraryModel] && steps++ < 500) step();
  assert.equal(R[PC] >>> 0, returns[libraryModel], 'reached native return');
  const bytes = Buffer.from(m.dbgRead(destination-4, 40));
  assert.deepEqual(bytes.subarray(0, 4), Buffer.alloc(4, 0xa5));
  assert.deepEqual(bytes.subarray(4+size), Buffer.alloc(36-size, 0xa5));
  return bytes.subarray(4, 4+size);
}
let controls = 0;
for (const model of ['E144', 'E148']) for (const value of [0, 0x55, 0xff])
  for (const size of [0, 1, 4, 16, 31]) {
    assert.deepEqual(fill(model, model, value, size), Buffer.alloc(size, value));
    controls++;
  }
const mixed = fill('E144', 'E148', 0, 16);
assert.notDeepEqual(mixed, Buffer.alloc(16));
console.log(JSON.stringify({
  stock_controls: controls, incompatible_library_negative_controls: 1,
  mixed_zero_fill: mixed.toString('hex'), reset_facts: facts,
  conclusion: 'Keep the E148 startup library with E148 callers. Shared placement is not ABI compatibility.',
  limitation: 'Native memset only, with explicit RAM and registers. No board boot or hardware validation.',
}, null, 2));
