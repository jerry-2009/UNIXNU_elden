_Head:
	/* Set _Entry address */
	adr		x1, _Payload

	/* Jump to the real code */
	b		_Start

	/* Fake Linux kernel header */

_StackBase:
	/* Text Offset */
	.quad UEFI_BASE

_StackSize:
	/* Image Size: firmware plus embedded FAT payload when present */
#ifdef EMBEDDED_PAYLOAD_SIZE
	.quad	UEFI_SIZE + (EMBEDDED_PAYLOAD_SIZE)
#else
	.quad	UEFI_SIZE
#endif

	/* Flags */
	.quad 0

	/* Reserved */
	.quad 0

	/* Reserved */
	.quad 0

	/* Reserved */
	.quad 0

	/* ARM64 Magic */
	.ascii "ARM\x64"

	/* Reserved */
	.long 0

_Start:
	mov		x4, x1
	ldr		x5, _StackBase
	cmp		x4, x5
	beq		_Entry
#ifdef EMBEDDED_PAYLOAD_SIZE
	ldr		x6,  _CopySize
#else
	ldr		x6,  _StackSize
#endif

_CopyLoop:
	ldp		x2, x3, [x4], #16
	stp		x2, x3, [x5], #16
	subs	x6, x6, #16
	b.ne	_CopyLoop
	ldr		x5, _StackBase

_Entry:
#ifdef EMBEDDED_PAYLOAD_SIZE
	/* x1 still holds the decompressed image base; the payload follows the FD. */
	add		x2, x1, #UEFI_SIZE
	ldr		x3, =EMBEDDED_PAYLOAD_SIZE
#endif
	br		x5

_Dead:
	/* We should never get here */
	b		_Dead

#ifdef EMBEDDED_PAYLOAD_SIZE
.align 3
_CopySize:
	/* Only the firmware volume is copied; the payload stays in place. */
	.quad	UEFI_SIZE
#endif

.text
.align 4

_Payload:
	/* Your code will get ran right after this binary */
