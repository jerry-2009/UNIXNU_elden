/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include <stdint.h>
/* Only typed phase/error/state values cross this boundary; never key material,
 * addresses, script contents or packet payloads. The syscall result is ignored. */
static __attribute__((noinline)) void elden_bt_trace(unsigned phase,unsigned script,int error,unsigned state,unsigned identity)
{
    register uint64_t a0 __asm__("x0")=UINT64_C(0xfe70001c);
    register uint64_t a1 __asm__("x1")=phase;
    register uint64_t a2 __asm__("x2")=(uint32_t)error;
    register uint64_t a3 __asm__("x3")=(uint64_t)script|((uint64_t)state<<8)|((uint64_t)(identity!=0)<<40);
    register uint64_t a4 __asm__("x4")=UINT64_C(0x42544832);
    register uint64_t number __asm__("x16")=179;
    __asm__ volatile("svc #0x80" : "+r"(a0),"+r"(a1),"+r"(a2),"+r"(a3),"+r"(a4),"+r"(number)
        : : "x5","x6","x7","x8","x9","x10","x11","x12","x13","x14","x15","x17","cc","memory");
}
