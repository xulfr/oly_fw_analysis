#!/usr/bin/env python3
"""Find the E148 counterpart of an E147 code address by instruction shape (operands of calls, jumps and
abs32 addresses wildcarded). usage: xm.py ADDR [nbytes] [src dst]"""
import re, subprocess, sys
OBJ='/home/user/work/toolchain/install/bin/mn10300-elf-objdump'
B=0x60021020
def blob(n): return open(f'/home/user/work/dec/{n}_main.bin','rb').read()
def ins(n, a, ln):
    out=subprocess.run([OBJ,'-b','binary','-m','mn10300','-D','-z','--insn-width=16',f'--adjust-vma={B:#x}',
        f'--start-address={a:#x}',f'--stop-address={a+ln:#x}',f'/home/user/work/dec/{n}_main.bin'],capture_output=True,text=True).stdout
    r=[]
    for l in out.splitlines():
        m=re.match(r'\s*([0-9a-f]+):\t((?:[0-9a-f]{2} )+)\s*\t?(.*)',l)
        if m: r.append((int(m.group(1),16),bytes.fromhex(m.group(2).replace(' ','')),m.group(3).strip()))
    return r
def shape(I):
    pat=b''; 
    for a,b,t in I:
        op=t.split()[0] if t else ''
        if op in('call','calls','jmp','jsr') and len(b)>=5: pat+=re.escape(b[:1])+b'.{4}'+re.escape(b[5:]) if b[0] in(0xdd,0xdc) else re.escape(b[:1])+b'.{2}'+re.escape(b[3:]) if b[0] in (0xcd,0xcc) and len(b)==5 else re.escape(b[:2])+b'.'*(len(b)-2)
        elif op=='call' : pat+=re.escape(b[:1])+b'.{2}'+re.escape(b[3:])
        elif re.search(r'0x[0-9a-f]{6,8}',t) and len(b)>=6: pat+=re.escape(b[:2])+b'.{4}'+re.escape(b[6:])
        elif op.startswith('b') and len(b)==2: pat+=re.escape(b[:1])+b'.'
        else: pat+=re.escape(b)
    return pat
def find(addr, ln=48, src='e147', dst='e148'):
    I=ins(src,addr,ln); p=shape(I); d=blob(dst)
    return [m.start()+B for m in re.finditer(p,d,re.S)]
if __name__=='__main__':
    a=int(sys.argv[1],16); ln=int(sys.argv[2]) if len(sys.argv)>2 else 48
    src,dst=(sys.argv[3],sys.argv[4]) if len(sys.argv)>4 else ('e147','e148')
    print(hex(a),[hex(x) for x in find(a,ln,src,dst)][:8])
