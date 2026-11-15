// SPDX-License-Identifier: BSD-2-Clause-Patent
// Actual transformed functions are included below. Only hardware/scheduler primitives are modeled.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <functional>
#include <utility>
#include "TransferPoll.h"
#include "RootTransportLayout.h"
using IOReturn = int;
using wait_result_t = int;
using event_t = const volatile void *;
enum { kIOReturnSuccess, kIOReturnBadArgument, kIOReturnNotReady, kIOReturnBusy,
       kIOReturnIOError, kIOReturnTimeout, THREAD_UNINT, NSEC_PER_USEC=1000,
       kMicrosecondScale=1000, THREAD_WAITING=-1, THREAD_AWAKENED=0, THREAD_TIMED_OUT=1 };
static void *THREAD_CONTINUE_NULL;
alignas(64) static uint8_t dma[kDmaBytes];
static struct { uintptr_t hc; uint8_t *virt; uint64_t phys; bool poisoned,ready; } gHost;
static struct {
    uint64_t command,elapsedTicks,waitTicks;
    uint32_t type,lun,opcode,scsi,response,protocol,residual,sense,dmaOcs,dmaResponse;
    uint32_t polls,dbSeen,isSeen;
} gRootDiagnostic;
static uint64_t now;
static uint32_t status,doorbell,ie,attachReadback,waitMicros;
static uint64_t attachRouter;
static unsigned attaches,masks,clears,blocks,asserts,cacheWrites,ringWrites;
static int attachResult;
static bool masked,irqEnabled,preemptEnabled,inPanic,waitPending,awakened,refuseWait,refuseIE;
static std::function<void()> onAssert,onBlock,onAttach,onEnable,onDoorbell,onClock;
static void once(std::function<void()> &fn) { auto local=std::move(fn);fn={};if(local)local(); }
static void eldenUfsIrqStop();
static uint32_t read32(uintptr_t, unsigned off) {
    if(off==0x20)return status;
    if(off==0x24)return ie;
    assert(off==0x58);once(onDoorbell);return doorbell;
}
static void hostWrite(unsigned off,uint32_t value) {
    if(off==0x20) { assert(value==1);status&=~1u;return; }
    if(off==0x24) { assert(value<=1);if(!refuseIE||!value)ie=value;if(value)once(onEnable);return; }
    assert(off==0x58&&value==1);doorbell=1;ringWrites++;
}
extern "C" IOReturn armcpu_spi_attach(uint32_t id,bool edge,void(*)(void*),void*,uint32_t*r,uint64_t*a) {
    assert(id==297&&!edge);attaches++;once(onAttach);
    if(!attachResult){masked=false;*r=attachReadback;*a=attachRouter;}return attachResult;
}
extern "C" IOReturn armcpu_spi_mask(uint32_t id,bool value) {assert(id==297);masked=value;masks++;return 0;}
static void IOLog(const char*,...) {}
static uint64_t mach_absolute_time(){once(onClock);return now++;}
static void nanoseconds_to_absolutetime(uint64_t n,uint64_t*t){*t=n;}
static void absolutetime_to_nanoseconds(uint64_t t,uint64_t*n){*n=t;}
static void clock_interval_to_deadline(uint32_t v,uint32_t s,uint64_t*d){*d=now+uint64_t(v)*s;}
static bool ml_get_interrupts_enabled(){return irqEnabled;}
static bool preemption_enabled(){return preemptEnabled;}
static unsigned panic_active(){return inPanic;}
static int current_thread(){return 1;}
static int assert_wait_timeout(event_t,int,uint32_t us,uint32_t scale) {
    assert(!waitPending&&us&&us<=1000&&scale==1000);asserts++;waitMicros=us;
    if(refuseWait)return THREAD_AWAKENED;
    waitPending=true;awakened=false;once(onAssert);return THREAD_WAITING;
}
static void thread_wakeup(event_t){if(waitPending)awakened=true;}
static void clear_wait(int,int){assert(waitPending);waitPending=false;clears++;}
static wait_result_t thread_block(void*) {
    assert(waitPending);blocks++;once(onBlock);waitPending=false;
    if(awakened)return THREAD_AWAKENED;
    now+=uint64_t(waitMicros)*1000;return THREAD_TIMED_OUT;
}
static void IODelay(unsigned us){now+=uint64_t(us)*1000;}
static void cacheInvalidate(const void*,size_t){}
static void cacheCivac(const void*,size_t){cacheWrites++;}
static IOReturn recordTransport(IOReturn r,uint32_t){return r;}
#define NATIVE_UFS_SM8750 1
#include "transport.inc"
static void complete(uint32_t ocs=0,bool interrupt=true) {
    doorbell=0;*reinterpret_cast<uint32_t*>(dma+8)=ocs;
    if(interrupt){status|=1;eldenUfsInterrupt(nullptr);}
}
static void reset(bool start=true) {
    now=1000000;status=doorbell=ie=0;attachReadback=0xa003;attachRouter=0;attachResult=0;
    attaches=masks=clears=blocks=asserts=cacheWrites=ringWrites=0;masked=true;
    irqEnabled=preemptEnabled=true;inPanic=waitPending=awakened=refuseWait=refuseIE=false;
    onAssert=onBlock=onAttach=onEnable=onDoorbell=onClock={};
    gHost={1,dma,0x100000,false,true};gRootDiagnostic={};memset(dma,0,sizeof(dma));
    eldenUfsIrqState=eldenUfsIrqAttached=eldenUfsGen=0;eldenUfsIrqHc=0;eldenUfsSpinTicks=0;
    eldenUfsIrqs=eldenUfsSleeps=eldenUfsWakes=eldenUfsWaitTimeouts=0;
    eldenUfsWaitOther=eldenUfsIrqSpurious=eldenUfsWaitTicks=eldenUfsCommands=0;
#if ELDEN_UFS_WAIT_TRIAL
    eldenUfsForcePoll=0;
#endif
    if(start)eldenUfsIrqStart();
}
static bool wait(uint32_t seen=0,uint64_t started=0,uint64_t deadline=1000000000){return eldenUfsCompletionWait(seen,started,deadline);}
int main(){ unsigned cases=0;
#if ELDEN_UFS_WAIT_TRIAL
    reset();eldenUfsForcePoll=1;assert(!wait()&&!blocks&&!asserts);cases++;
#endif
    reset();assert(ie==1&&!masked&&eldenUfsIrqRunning());eldenUfsIrqStart();assert(attaches==1);cases++;
    reset(false);attachResult=1;eldenUfsIrqStart();assert(!ie&&masked&&!masks&&!eldenUfsIrqRunning());cases++;
    for(unsigned rb:{0xa002u,0xa001u,0xa007u,0xb003u}){reset(false);attachReadback=rb;eldenUfsIrqStart();assert(!ie&&masked&&!eldenUfsIrqRunning());cases++;}
    reset(false);attachRouter=1;eldenUfsIrqStart();assert(!ie&&masked);cases++;
    reset(false);refuseIE=true;eldenUfsIrqStart();assert(!ie&&masked&&!eldenUfsIrqRunning());cases++;
    reset(false);eldenUfsIrqStop();eldenUfsIrqStart();assert(!attaches&&!ie&&!masks);cases++;
    for(bool duringAttach:{true,false}){reset(false);(duringAttach?onAttach:onEnable)=[]{eldenUfsIrqStop();};eldenUfsIrqStart();assert(masked&&!ie&&!eldenUfsIrqRunning());cases++;}
    reset();complete();assert(wait()&&clears==1&&!blocks&&!waitPending);cases++;
    reset();onAssert=[]{complete();};assert(wait()&&clears==1&&!blocks);cases++;
    reset();onBlock=[]{complete();};assert(wait()&&blocks==1&&eldenUfsWakes==1&&!eldenUfsWaitTimeouts);cases++;
    reset();onBlock=[]{eldenUfsIrqStop();};assert(wait()&&eldenUfsWaitOther==1&&!eldenUfsWakes&&masked&&!ie);cases++;
    reset();onAssert=[]{eldenUfsIrqStop();};assert(wait()&&!blocks&&clears==1);cases++;
    reset();assert(wait()&&eldenUfsWaitTimeouts==1&&waitMicros==1000&&!eldenUfsWakes);cases++;
    reset();assert(wait(0,0,now+57000)&&waitMicros==57);cases++;
    for(unsigned i=0;i<7;i++){reset();if(i==0)irqEnabled=false;if(i==1)preemptEnabled=false;if(i==2)inPanic=true;
        bool r=i==3?wait(0,now,now+1000000):i==4?wait(0,now+1,now+1000000):i==5?wait(0,0,now):i==6?wait(0,0,now+500):wait();
        assert(!r&&!asserts&&!blocks);cases++;}
    reset();refuseWait=true;assert(!wait()&&!blocks&&!waitPending);cases++;
    reset();eldenUfsInterrupt(nullptr);assert(!eldenUfsGen&&!eldenUfsIrqs&&eldenUfsIrqSpurious==1);cases++;
    reset();status=1;doorbell=1;eldenUfsInterrupt(nullptr);assert(!eldenUfsGen&&eldenUfsIrqs==1&&!status);cases++;
    reset();status=kUfsFatalStatus|1;eldenUfsInterrupt(nullptr);assert(status==kUfsFatalStatus&&masked&&!ie&&!eldenUfsIrqRunning());cases++;
    reset();HardwareTransferPort port{};onDoorbell=[]{complete();};assert(port.doorbell()==0&&port.generation==0&&eldenUfsGen==1);assert(wait(port.generation)&&clears==1);cases++;
    reset();doorbell=1;*reinterpret_cast<uint32_t*>(dma+8)=15;onBlock=[]{complete(15);};
    port.started=0;port.deadline=now+2000000;UfsTransferPoll pending;
    assert(pollUfsTransfer(port,pending)==UfsTransferEnd::Timeout&&pending.rechecked&&pending.ocs==15);cases++;
    for(unsigned mode=0;mode<4;mode++){reset();uint32_t ocs=42;
        if(mode==0)onBlock=[]{complete();};
        if(mode==1)onBlock=[]{status=kUfsFatalStatus|1;eldenUfsInterrupt(nullptr);};
        if(mode==2)onBlock=[]{complete(15);};
        if(mode==3)onBlock=[]{complete(2);};
        auto r=hostSubmit(2,4096,2000,&ocs);assert(ringWrites==1&&eldenUfsCommands==1);
        if(mode==0)assert(r==kIOReturnSuccess&&!gHost.poisoned&&ocs==0);
        if(mode==1||mode==2){assert(r==(mode==1?kIOReturnIOError:kIOReturnTimeout)&&gHost.poisoned&&!gHost.ready&&masked&&!ie);
            unsigned oldWrites=cacheWrites;assert(!hostClearUcd());assert(hostSubmit(2,4096,2000,&ocs)==kIOReturnNotReady&&cacheWrites==oldWrites&&ringWrites==1);}
        if(mode==3)assert(r==kIOReturnIOError&&!gHost.poisoned&&ocs==2);
        cases++;
    }
    reset();elden_ufs_wait_shutdown();unsigned masksBefore=masks;eldenUfsIrqStop();assert(masks>masksBefore&&!wait());cases++;
    printf("PASS %u actual completion/submit cases\n",cases);
}
