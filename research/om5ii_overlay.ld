SECTIONS
{
 .overlay_hook 0x6081e2f1 : { *(.overlay_hook) }
 .overlay 0x60845d00 : { *(.overlay_code) *(.overlay_data) }
 ASSERT(ADDR(.overlay) + SIZEOF(.overlay) <= 0x60846000,
        "Overlay crosses the native section-5 loaded end; redesign placement")
}
