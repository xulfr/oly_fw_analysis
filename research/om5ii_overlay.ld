SECTIONS
{
 .overlay_hook 0x6081e2f1 : { *(.overlay_hook) }
 .overlay 0x60845d00 : { *(.overlay_code) *(.overlay_data) }
}
