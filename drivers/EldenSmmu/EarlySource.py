"""Explicit early SMMU variant over frozen UFS/CPU/WCN/PCIe sources."""
import importlib.util,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'drivers/EldenUfsIdle'))
import IdleSource
def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('Early SMMU source anchor drift: '+old[:80])
    return text.replace(old,new,1)
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def recovery():
    text=IdleSource.recovery().decode()
    marker='\n/* ELDEN_SMP_GUARD_END */'
    extra='''
static unsigned gEldenSmmuEarlyWindow;
extern "C" int elden_wifi_smmu_early_initialize(void);
extern "C" int elden_wifi_smmu_early_guard(void){
  uint64_t now=eldenDeadlineCounter();
  return __atomic_load_n(&gEldenSmmuEarlyWindow,__ATOMIC_ACQUIRE)&&gEldenEarlyMode==3&&
    __atomic_load_n(&gEldenEarlyPrepared,__ATOMIC_ACQUIRE)&&!__atomic_load_n(&gEldenEarlyError,__ATOMIC_ACQUIRE)&&
    !__atomic_load_n(&gEldenSmpPanic,__ATOMIC_ACQUIRE)&&!__atomic_load_n(&gEldenRpcState,__ATOMIC_ACQUIRE)&&
    now>=gEldenEarlyArmedAt&&now-gEldenEarlyArmedAt<19200000ULL*90;
}
extern "C" __attribute__((noinline)) int elden_wifi_smmu_early_invoke(void){
  __atomic_store_n(&gEldenSmmuEarlyWindow,1u,__ATOMIC_RELEASE);
  int result=elden_wifi_smmu_early_initialize();
  __atomic_store_n(&gEldenSmmuEarlyWindow,0u,__ATOMIC_RELEASE);
  char line[96];snprintf(line,sizeof(line),"\\nELDEN_SMMU early-return=%d before-host-start=1\\n",result);eldenSdamLog(line);
  return result;
}
'''
    return replace(text,marker,extra+marker).encode()
def ufs():
    text=IdleSource.normal_source().decode()
    text=replace(text,'#include <kern/thread.h>','#include <kern/thread.h>\nextern "C" __attribute__((noinline)) int elden_wifi_smmu_early_invoke(void);')
    marker='  gHost.smmu = gHost.smmuMap->getVirtualAddress ();'
    extra='''
  unsigned smmuEarly=0;PE_parse_boot_argn("esm",&smmuEarly,sizeof(smmuEarly));
  if(smmuEarly==1){
    (void)elden_wifi_smmu_early_invoke();
  }
'''
    return replace(text,marker,marker+extra).encode()
def cpu():
    sys.path.insert(0,str(ROOT/'drivers/EldenUfsWait'));from Source import cpu_source
    text=cpu_source().decode()
    text=replace(text,'static const uint32_t kSgiPpiEnable = 0xffffU | (1U << 27);','static const uint32_t kSgiPpiEnable = 1U | (1U << 27);')
    text=replace(text,'    for (uint64_t intid = 0; intid < 16; intid++) {',
        '    for (uint64_t intid = 0; intid < 16; intid++) {\n      if (!(kSgiPpiEnable & (1U << intid))) { continue; }')
    return text.encode()
def wcn():
    old=module('smmu_wcn_parent',ROOT/'drivers/EldenPcie/NativeHookSource.py').source().decode()
    old=replace(old,'void elden_pcie_native_stop_begin(void);','void elden_pcie_native_stop_begin(void);\nvoid elden_wifi_smmu_stop_begin(void);')
    return replace(old,'    elden_pcie_native_stop_begin();','    elden_pcie_native_stop_begin();\n    elden_wifi_smmu_stop_begin();').encode()
def pcie_generated():
    parent=module('smmu_pcie_parent',ROOT/'drivers/EldenPcie/EndpointNativeSource.py')
    files=parent.generated();text=files['Native.cpp'].decode()
    text=replace(text,'#include "EndpointNative.h"','#include "EndpointNative.h"\n#include "EldenWifiSmmuNative.h"');files['Native.cpp']=text.encode()
    text=files['NativeRuntime.inc'].decode()
    marker='static int power_up(void *p,unsigned gen,uint64_t *epoch){'
    extra='''
    unsigned smmu=0;PE_parse_boot_argn("esm",&smmu,sizeof(smmu));
    if(smmu==1){
        EldenWifiSmmuStatus state={};int rc=elden_wifi_smmu_status(&state);
        log("\\nELDEN_SMMU late status=%d ready=%u fault=%u fsr=%x stage=%u\\n",rc,state.ready,state.fault_claimed,state.fault_status,state.stage);
        if(rc||!elden_wifi_smmu_ready())return -11;
    }
'''
    files['NativeRuntime.inc']=replace(text,marker,marker+extra).encode();return files
