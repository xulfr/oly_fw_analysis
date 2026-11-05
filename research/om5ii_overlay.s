/* Offline prototype only. A candidate builder supplies overlay_data.s from
 * locally supplied stock and patched images. No camera use is qualified. */
.equ overlay_return,0x6081e2f7
.equ section_wait,0x60046395
.section .overlay_hook,"ax"
 jmp overlay_install
 .byte 0xcb

.section .overlay_code,"ax"
.globl overlay_install
.extern overlay_table
overlay_install:
 call overlay_worker,[],0
 mov 0x60b3eb97,a0
overlay_jump:
 .byte 0xdc
 .long overlay_return-overlay_jump
overlay_worker:
 mov d0,a0
 mov psw,d0
 movm [d2,d3,a2,a3],(sp)
 add -24,sp
 /* The section_wait call uses the first 8 bytes of this frame. */
 mov a0,(8,sp)
 mov d1,(12,sp)
 mov a1,(16,sp)
 mov d0,(20,sp)
 /* Task 92 has just launched FIRMUP_CLI. Wait for stock Section 7 before
  * inspecting any of its bytes. The loaded bit can still follow a read error,
  * so the full original-byte preflight below is essential. */
 mov 7,d0
overlay_wait_call:
 .byte 0xdd
 .long section_wait-overlay_wait_call
 .byte 0x80,0x08
 mov overlay_table,a2
 mov 16,d3
overlay_check_row:
 mov (a2),a0
 mov (4,a2),a1
 mov (12,a2),d2
overlay_check_byte:
 movbu (a0),d0
 movbu (a1),d1
 cmp d0,d1
 bne overlay_done
 inc a0
 inc a1
 add -1,d2
 bne overlay_check_byte
 add 16,a2
 add -1,d3
 bne overlay_check_row

 mov overlay_table,a2
 mov 16,d3
overlay_copy_row:
 mov (a2),a0
 mov (8,a2),a1
 mov (12,a2),d2
overlay_copy_byte:
 movbu (a1),d0
 movbu d0,(a0)
 inc a0
 inc a1
 add -1,d2
 bne overlay_copy_byte
 add 16,a2
 add -1,d3
 bne overlay_copy_row
overlay_done:
 mov (8,sp),d0
 mov (12,sp),d1
 mov (16,sp),a1
 mov (20,sp),d2
 mov d2,psw
 ret [d2,d3,a2,a3],40
