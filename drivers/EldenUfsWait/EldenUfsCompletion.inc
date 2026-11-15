/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* UFSHCI completion IRQ/hybrid-wait pattern from ShengUfs34ff541; board IRQ is
 * SM8750 DTS6f97250e SPI265 = INTID297. Completion remains TransferPoll's job. */
// Included in the transport namespace; kernel headers belong at TU scope.
extern "C" IOReturn armcpu_spi_attach(uint32_t,bool,void(*)(void*),void*,uint32_t*,uint64_t*);
extern "C" IOReturn armcpu_spi_mask(uint32_t,bool);
enum { EldenIrqOff, EldenIrqStarting, EldenIrqRunning, EldenIrqClosed };
static volatile uint32_t eldenUfsIrqState,eldenUfsIrqAttached,eldenUfsGen;
static uintptr_t eldenUfsIrqHc;
static volatile uint64_t eldenUfsIrqs,eldenUfsSleeps,eldenUfsWakes,eldenUfsWaitTimeouts;
static volatile uint64_t eldenUfsWaitOther,eldenUfsIrqSpurious;
static uint64_t eldenUfsSpinTicks;
static volatile uint64_t eldenUfsWaitTicks,eldenUfsCommands;
static uint32_t eldenUfsGeneration(){return __atomic_load_n(&eldenUfsGen,__ATOMIC_ACQUIRE);}
static bool eldenUfsIrqRunning(){return __atomic_load_n(&eldenUfsIrqState,__ATOMIC_ACQUIRE)==EldenIrqRunning;}
static void eldenUfsIrqStop(){
    uint32_t previous=__atomic_exchange_n(&eldenUfsIrqState,EldenIrqClosed,__ATOMIC_ACQ_REL);
    // May race startup. Repeat the hardware withdrawal even when already closed:
    // startup must recheck Closed after attach/IE and call this again. Never mask
    // another owner's line after an exclusive-attach refusal. No host mutex here.
    if(__atomic_load_n(&eldenUfsIrqHc,__ATOMIC_ACQUIRE))hostWrite(0x24,0);
    if(__atomic_load_n(&eldenUfsIrqAttached,__ATOMIC_ACQUIRE))(void)armcpu_spi_mask(297,true);
    if(previous!=EldenIrqClosed){
        __atomic_add_fetch(&eldenUfsGen,1u,__ATOMIC_RELEASE);
        thread_wakeup((event_t)&eldenUfsGen);
    }
}
static void eldenUfsInterrupt(void*){
    uint32_t status=read32(gHost.hc,0x20);
    if(status&1){hostWrite(0x20,1);__atomic_add_fetch(&eldenUfsIrqs,1ull,__ATOMIC_RELAXED);}
    else __atomic_add_fetch(&eldenUfsIrqSpurious,1ull,__ATOMIC_RELAXED);
    if(__atomic_load_n(&eldenUfsIrqState,__ATOMIC_ACQUIRE)==EldenIrqClosed)return;
    if(status&kUfsFatalStatus){eldenUfsIrqStop();return;}
    if((status&1)&&!(read32(gHost.hc,0x58)&1)){
        __atomic_add_fetch(&eldenUfsGen,1u,__ATOMIC_RELEASE);
        thread_wakeup((event_t)&eldenUfsGen);
    }
}
static void eldenUfsIrqStart(){
    uint32_t expected=EldenIrqOff;
    if(!__atomic_compare_exchange_n(&eldenUfsIrqState,&expected,EldenIrqStarting,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return;
    __atomic_store_n(&eldenUfsIrqHc,gHost.hc,__ATOMIC_RELEASE);
    if(__atomic_load_n(&eldenUfsIrqState,__ATOMIC_ACQUIRE)==EldenIrqClosed){eldenUfsIrqStop();return;}
    uint32_t readback=0;uint64_t router=~0ull;
    IOReturn rc=armcpu_spi_attach(297,false,eldenUfsInterrupt,nullptr,&readback,&router);
    if(rc!=kIOReturnSuccess){eldenUfsIrqStop();IOLog("ELDEN_UFS_IRQ attach=%x; polling retained\n",rc);return;}
    __atomic_store_n(&eldenUfsIrqAttached,1u,__ATOMIC_RELEASE);
    if(__atomic_load_n(&eldenUfsIrqState,__ATOMIC_ACQUIRE)==EldenIrqClosed){eldenUfsIrqStop();return;}
    if((readback&7)!=3||((readback>>8)&255)!=0xa0||router!=0){
        eldenUfsIrqStop();IOLog("ELDEN_UFS_IRQ readback refused=%x router=%llx\n",readback,router);return;
    }
    nanoseconds_to_absolutetime(200000,&eldenUfsSpinTicks);
    hostWrite(0x20,1);hostWrite(0x24,1);
    if(read32(gHost.hc,0x24)!=1){eldenUfsIrqStop();IOLog("ELDEN_UFS_IRQ IE refused; polling retained\n");return;}
    expected=EldenIrqStarting;
    if(!__atomic_compare_exchange_n(&eldenUfsIrqState,&expected,EldenIrqRunning,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){
        eldenUfsIrqStop();return;
    }
    IOLog("ELDEN_UFS_IRQ configured intid=297 readback=%x router=%llx spin-us=200; delivery unverified\n",readback,router);
}
static bool eldenUfsCompletionWait(uint32_t seen,uint64_t started,uint64_t deadline){
    // Unlike sheng, no one-microsecond event-stream qualification exists for all
    // Elden cores. Keep the existing bounded yield delay during the spin budget.
    uint64_t now=mach_absolute_time();
    if(!eldenUfsIrqRunning()||panic_active()||!ml_get_interrupts_enabled()||!preemption_enabled()||
       now<started||now-started<eldenUfsSpinTicks||now>=deadline)return false;
    uint64_t remaining=0;absolutetime_to_nanoseconds(deadline-now,&remaining);
    uint32_t micros=remaining/1000<1000?(uint32_t)(remaining/1000):1000;
    if(!micros)return false;
    if(assert_wait_timeout((event_t)&eldenUfsGen,THREAD_UNINT,micros,NSEC_PER_USEC)!=THREAD_WAITING)return false;
    if(eldenUfsGeneration()!=seen||!eldenUfsIrqRunning()){
        clear_wait(current_thread(),THREAD_AWAKENED);return true;
    }
    __atomic_add_fetch(&eldenUfsSleeps,1ull,__ATOMIC_RELAXED);
    wait_result_t result=thread_block(THREAD_CONTINUE_NULL);
    if(result==THREAD_AWAKENED&&eldenUfsIrqRunning()&&eldenUfsGeneration()!=seen)__atomic_add_fetch(&eldenUfsWakes,1ull,__ATOMIC_RELAXED);
    else if(result==THREAD_TIMED_OUT)__atomic_add_fetch(&eldenUfsWaitTimeouts,1ull,__ATOMIC_RELAXED);
    else __atomic_add_fetch(&eldenUfsWaitOther,1ull,__ATOMIC_RELAXED);
    return true;
}
static void eldenUfsWaitAccount(uint64_t ticks){__atomic_fetch_add(&eldenUfsWaitTicks,ticks,__ATOMIC_RELAXED);__atomic_fetch_add(&eldenUfsCommands,1ull,__ATOMIC_RELAXED);}
extern "C" void elden_ufs_wait_shutdown(){
    eldenUfsIrqStop();uint64_t ns=0;absolutetime_to_nanoseconds(__atomic_load_n(&eldenUfsWaitTicks,__ATOMIC_RELAXED),&ns);
    IOLog("ELDEN_UFS_IRQ stop commands=%llu wait-us=%llu irqs=%llu sleeps=%llu wakes=%llu timeouts=%llu other=%llu spurious=%llu; polling remains, DMA retained\n",
        __atomic_load_n(&eldenUfsCommands,__ATOMIC_RELAXED),ns/1000,
        __atomic_load_n(&eldenUfsIrqs,__ATOMIC_RELAXED),__atomic_load_n(&eldenUfsSleeps,__ATOMIC_RELAXED),
        __atomic_load_n(&eldenUfsWakes,__ATOMIC_RELAXED),__atomic_load_n(&eldenUfsWaitTimeouts,__ATOMIC_RELAXED),
        __atomic_load_n(&eldenUfsWaitOther,__ATOMIC_RELAXED),__atomic_load_n(&eldenUfsIrqSpurious,__ATOMIC_RELAXED));
}
