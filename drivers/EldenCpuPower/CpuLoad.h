/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include <stdint.h>

/* PROCESSOR_CPU_LOAD_INFO counters, in USER/SYSTEM/IDLE/NICE order.
 * Each counter is independently truncated by XNU to hz_tick_interval.
 * Report intervals, not instantaneous load or inferred hardware MHz. */
struct EldenCpuTicks { bool valid; uint32_t ticks[4]; uint64_t at; };
struct EldenCpuLoad { bool valid; uint32_t busy_pm; uint64_t total, idle; };
static inline EldenCpuLoad elden_cpu_load(const EldenCpuTicks &a,
                                         const EldenCpuTicks &b,
                                         uint64_t tick_interval) {
    EldenCpuLoad out={};
    if(!a.valid||!b.valid||!tick_interval||b.at<=a.at)return out;
    uint64_t elapsed=b.at-a.at,expected=elapsed/tick_interval;
    /* At least 50 ticks; at most 10 seconds at the actual XNU tick rate is
     * enforced by the caller. A three-tick tolerance covers independent
     * truncation of USER/SYSTEM/IDLE (NICE is always zero in Darwin 23). */
    if(expected<50||expected>10000)return out;
    for(unsigned i=0;i<4;++i)out.total+=(uint32_t)(b.ticks[i]-a.ticks[i]);
    out.idle=(uint32_t)(b.ticks[2]-a.ticks[2]);
    if(!out.total||out.total+3<expected||out.total>expected+3||out.idle>out.total)
        return {};
    out.busy_pm=(uint32_t)((out.total-out.idle)*1000/out.total);
    out.valid=true;return out;
}
