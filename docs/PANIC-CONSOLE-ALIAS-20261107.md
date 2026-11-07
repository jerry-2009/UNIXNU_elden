# Duplicate panic output with the GOP kprintf sink

The Y700 photograph shows ordinary IOLog text once but each panic character
twice. Both consdebug_putc and consdebug_putc_unbuffered first write to the
console, then append debug_putc to the panic buffer, then send to PE_kputc when
the console is not serial and serial output is enabled. The existing board GOP
adaptation sets PE_kputc to console_write_unbuffered. Both output calls therefore
reach the same display for each character.

The patch skips the second call only when PE_kputc equals
console_write_unbuffered. It retains the console call, panic-buffer append,
normal kprintf, and an independent serial/USB sink if selected later. Repeated
characters in the original message are preserved; this does not filter text.

Apply after elden-gop-console.patch through console-series. Check both buffered
and unbuffered panic entry points with an aliased console sink, independent sink,
disabled serial output and serial console. Hardware acceptance is the same
read-only LUN0 root-check report with single characters and unchanged values.
