"""Derive an opt-in combined CPU load/PERF observer from the frozen survey."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'profiles/v91/sources/power/CpuPerfSurvey.cpp'
SOURCE_SHA='6c71236e924895b4059264c30baa160a3304239923d7bdfb57ed40ae230e008c'

def source():
    data=SOURCE.read_bytes()
    if hashlib.sha256(data).hexdigest()!=SOURCE_SHA:raise ValueError('Frozen CPU survey differs')
    text=data.decode()
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('CPU survey source anchor differs')
        text=text.replace(old,new)
    replace('#include <stdarg.h>','#include <stdarg.h>\n#include <mach/processor_info.h>\n#include <mach/mach_time.h>\n#include "CpuLoad.h"\n#include "PdObservation.h"')
    replace('int elden_recovery_armed(void);','int elden_recovery_armed(void);\nunsigned elden_pd_power_observation(void);\nprocessor_t cpu_to_processor(int);\nkern_return_t processor_info(processor_t,processor_flavor_t,host_t *,processor_info_t,mach_msg_type_number_t *);\nextern uint32_t hz_tick_interval;')
    replace('static unsigned attempted;','static unsigned attempted,selectedMode;\nstatic uint64_t counterFrequency(){uint64_t hz;__asm__ volatile("mrs %0, cntfrq_el0":"=r"(hz));return hz;}')
    marker='static void worker(void *,wait_result_t){'
    replace(marker,(ROOT/'drivers/EldenCpuPower/Survey.inc').read_text()+'\n'+marker+'\n    if(selectedMode==2){powerObservation();thread_terminate(current_thread());return;}')
    replace('unsigned mode=0;PE_parse_boot_argn("elden-cpu-survey",&mode,sizeof(mode));','unsigned mode=0;if(!PE_parse_boot_argn("elden-cpu-survey",&mode,sizeof(mode)))PE_parse_boot_argn("ecp",&mode,sizeof(mode));')
    replace('if(mode!=1||__atomic_exchange_n(&attempted,1u,__ATOMIC_ACQ_REL))return;','if((mode!=1&&mode!=2)||__atomic_exchange_n(&attempted,1u,__ATOMIC_ACQ_REL))return;\n    selectedMode=mode;')
    return text.encode()
