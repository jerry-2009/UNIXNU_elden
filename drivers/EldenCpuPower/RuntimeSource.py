"""Add explicit mode3 to the SHA-bound v146 observer; retain mode1/2 bodies."""
from pathlib import Path
import hashlib
from SurveySource import source as observer
HERE=Path(__file__).resolve().parent
OBSERVER_SHA='253d6075754dd6e1673b973afa152709296e1ab5105454ab2d862b65e7b57486'
RECOVERY=HERE.parents[1]/'profiles/v97-wcn/EldenSdamRecovery.inc'
RECOVERY_SHA='ce63730b121d825dd9405cd9c537eaf7c0c73f78ed6dba0fe6c5021472a45781'
def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('Runtime source anchor differs: '+old[:70])
    return text.replace(old,new)
def source():
    original=observer()
    if hashlib.sha256(original).hexdigest()!=OBSERVER_SHA:raise ValueError('Observer source differs')
    text=original.decode()
    text=replace(text,'#include "CpuPerfAccess.h"','#include "CpuPerfAccess.h"\n#include "GovernorControl.h"')
    text=replace(text,'int elden_recovery_armed(void);','''int elden_recovery_armed(void);
int elden_recovery_rpc_ready(void);
unsigned elden_recovery_deadline_remaining(void),elden_charge_policy_ready(void);
bool elden_battery_temperature_get(int *,uint32_t *,uint32_t *);
boolean_t ml_at_interrupt_context(void);
extern volatile uint32_t native_touch_seq;''')
    marker='static void worker(void *,wait_result_t){'
    text=replace(text,marker,(HERE/'Runtime.inc').read_text(encoding='utf-8')+'\n'+marker+'\n    if(selectedMode==3){governorWorker();thread_terminate(current_thread());return;}')
    text=replace(text,'(mode!=1&&mode!=2)','(mode!=1&&mode!=2&&mode!=3)')
    return (text+'''
extern "C" int elden_cpu_governor_request_stop(void){
    __atomic_store_n(&governorStop,1u,__ATOMIC_RELEASE);
    for(unsigned wait=0;wait<500;++wait){
        unsigned state=__atomic_load_n(&governorRun,__ATOMIC_ACQUIRE);
        if(state==0||state==2)return 1;
        if(state==3)return 0;
        IOSleep(10);
    }
    return 0;
}
''').encode()
def recovery():
    data=RECOVERY.read_bytes()
    if hashlib.sha256(data).hexdigest()!=RECOVERY_SHA:raise ValueError('Current UFS recovery source differs')
    text=data.decode()
    declaration='extern "C" int elden_wcn_request_stop(void) __attribute__((weak_import));'
    text=replace(text,declaration,'extern "C" int elden_cpu_governor_request_stop(void) __attribute__((weak_import));\n'+declaration)
    marker='static void eldenRecoveryShutdown(void){\n  __atomic_store_n(&gEldenRpcHoldLogs,0,__ATOMIC_RELEASE);'
    text=replace(text,marker,marker+'''
  if(elden_cpu_governor_request_stop){
    int stopped=elden_cpu_governor_request_stop();
    eldenSdamLog(stopped?"\\nELDEN_CPU_GOV RPC stop=1; original levels confirmed or no writes\\n":
        "\\nELDEN_CPU_GOV RPC stop=0; restore/owner unconfirmed, continuing reset\\n");
  }''')
    return text.encode()
