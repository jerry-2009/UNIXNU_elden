/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "GovernorControl.h"

/* The runtime allocates a zeroed Control once after acquiring the CPUCP owner.
 * Only its worker calls initialize/step. The recovery callback posts a separate
 * atomic stop request; its next Input carries that request to this worker. */
extern "C" size_t elden_cpu_governor_context_bytes(void){return sizeof(elden_cpufreq::Control);}
extern "C" bool elden_cpu_governor_initialize(elden_cpufreq::Control *c,
    const scmi::Io *io,const elden_cpufreq::Config *config,bool ready){
    return c&&io&&config&&elden_cpufreq::initialize(c,*io,*config,ready);
}
extern "C" void elden_cpu_governor_step(elden_cpufreq::Control *c,
    const elden_cpufreq::Input *input){
    if(c&&input)elden_cpufreq::step(c,*input);
}
extern "C" bool elden_cpu_governor_message_allowed(const elden_cpufreq::Control *c,
    uint32_t protocol,uint32_t message){return c&&elden_cpufreq::allowed(c,protocol,message);}
extern "C" bool elden_cpu_governor_terminal(const elden_cpufreq::Control *c){
    return c&&elden_cpufreq::terminal(c);
}
