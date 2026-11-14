#!/bin/bash
# run.sh BUILD OUT 'keys' [opts...]
b=$1; o=$2; k=$3; shift 3
cd /home/user/work && PRE=${PRE:-scripts/mount.mjs} OM_EMU_MODEL=E148 node scripts/sess.mjs /home/user/xulfr-om-emu $b/strict/decoded/0100.bin $b/strict/decoded/0101.bin $o "$k" --ready --card=${CARD:-card1} --peekP "$@" 2>&1 | grep -v "image stores so far"
