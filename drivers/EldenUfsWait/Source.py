"""Add completion IRQ support over the exact guarded single-slot transport."""
from pathlib import Path
import hashlib,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'drivers/EldenCpuActivation'))
from EarlyStorageSource import source as guarded_source,recovery as guarded_recovery
CPU=ROOT/'profiles/v91/sources/cpu/ArmCpu.cpp'
CPU_SHA='f48f1b313b2a5034a461f685a4fd0d4c40eace4268389a318c12c8fa7a98ff9a'
COMMANDS=ROOT/'profiles/v91/native-build/extra/05dd92a331a2/RootCommands.h'
COMMANDS_SHA='05dd92a331a20657b3773278011a913b74cf8c220b98fd3e96aebeea3190d8df'
def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('UFS wait source anchor differs: '+old[:60])
    return text.replace(old,new)
def cpu_source():
    data=CPU.read_bytes()
    if hashlib.sha256(data).hexdigest()!=CPU_SHA:raise ValueError('ArmCpu input differs')
    text=data.decode();sig='extern "C" IOReturn armcpu_spi_attach (uint32_t intid, bool edge, void (*handler) (void *), void *context,'
    text=replace(text,sig,'static IOReturn eldenSpiAttachUnlocked (uint32_t intid, bool edge, void (*handler) (void *), void *context,')
    text+='''
// Registration serialization follows ArmCpu d90e457b. No dispatch table or
// affinity/PSCI/timer behavior changes; an IRQ handler never takes this lock.
static IOLock *gEldenSpiRegistrationLock;
extern "C" IOReturn armcpu_spi_attach(uint32_t id,bool edge,void(*handler)(void*),void*context,uint32_t*readback,uint64_t*router){
  IOLock *lock=__atomic_load_n(&gEldenSpiRegistrationLock,__ATOMIC_ACQUIRE);
  if(!lock){
    IOLock *candidate=IOLockAlloc();if(!candidate)return kIOReturnNoResources;
    if(!__atomic_compare_exchange_n(&gEldenSpiRegistrationLock,&lock,candidate,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))IOLockFree(candidate);else lock=candidate;
  }
  IOLockLock(lock);IOReturn result=eldenSpiAttachUnlocked(id,edge,handler,context,readback,router);IOLockUnlock(lock);return result;
}
extern "C" IOReturn armcpu_spi_mask(uint32_t id,bool masked){
  if(!gDist||!armcpu_gic_ready||id<32||id>=1020)return kIOReturnNotReady;
  uint32_t used=__atomic_load_n(&gSpiUsed,__ATOMIC_ACQUIRE);bool found=false;
  for(uint32_t i=0;i<used;++i)if(gSpi[i].id==id)found=true;
  if(!found)return kIOReturnNotFound;
  write32(gDist,(masked?0x180u:0x100u)+(id/32)*4,1u<<(id%32));
  __asm__ volatile("dsb sy":::"memory");return kIOReturnSuccess;
}
'''
    return text.encode()
def commands():
    data=COMMANDS.read_bytes()
    if hashlib.sha256(data).hexdigest()!=COMMANDS_SHA:raise ValueError('RootCommands input differs')
    text=data.decode()
    text=replace(text,'  uint64_t deadline;','  uint64_t deadline,started;\n  uint32_t generation;')
    text=replace(text,'  uint32_t doorbell () { return read32 (gHost.hc, 0x58); }','  uint32_t doorbell () { generation=eldenUfsGeneration();return read32 (gHost.hc, 0x58); }')
    text=replace(text,'  void delay () {','  void delay () {\n    if(eldenUfsCompletionWait(generation,started,deadline))return;')
    text=replace(text,'  uint64_t started = mach_absolute_time ();','  uint64_t started = mach_absolute_time ();port.started=started;')
    text=replace(text,'  gRootDiagnostic.elapsedTicks = mach_absolute_time () - started;','  gRootDiagnostic.elapsedTicks = mach_absolute_time () - started;\n  eldenUfsWaitAccount(gRootDiagnostic.elapsedTicks);')
    if text.count('gHost.poisoned = true;')!=6:raise ValueError('Quarantine sites differ')
    text=text.replace('gHost.poisoned = true;','eldenUfsIrqStop();gHost.poisoned = true;')
    return text.encode()
def source():
    text=guarded_source().decode()
    text=replace(text,'#include <kern/thread.h>','#include <kern/thread.h>\n#include <kern/sched_prim.h>\n#include <kern/clock.h>\n#include <machine/machine_routines.h>')
    text=replace(text,'#include "RootCommands.h"','#include "EldenUfsCompletion.inc"\n#include "RootCommands.h"')
    text=replace(text,'      gHost.ready = true;\n      return true;','      gHost.ready = true;\n      eldenUfsIrqStart();\n      return true;')
    return text.encode()
def recovery():
    text=guarded_recovery().decode()
    decl='extern "C" int elden_wcn_request_stop(void) __attribute__((weak_import));'
    text=replace(text,decl,'extern "C" void elden_ufs_wait_shutdown(void);\n'+decl)
    marker='static void eldenRecoveryShutdown(void){\n  __atomic_store_n(&gEldenRpcHoldLogs,0,__ATOMIC_RELEASE);'
    text=replace(text,marker,marker+'\n  elden_ufs_wait_shutdown();')
    return text.encode()
