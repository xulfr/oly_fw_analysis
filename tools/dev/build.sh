#!/bin/bash
# build.sh NAME : record + strict build into /home/user/work/NAME
export PATH=/home/user/work/toolchain/install/bin:$PATH
cd /home/user/caduceus-om5 && rm -rf /home/user/work/$1 && python3 tools/oly_patch_record.py firmware/om5ii --stock /home/user/work/stock/OLY_E_148_1100_0000_0000.BIN --work /home/user/work/$1 2>&1 | grep -E "package_sha|rror|ssert|differ" 
