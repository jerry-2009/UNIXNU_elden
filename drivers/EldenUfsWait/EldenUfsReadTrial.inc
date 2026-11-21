// SPDX-License-Identifier: BSD-2-Clause-Patent
#if !defined(ELDEN_PINNED_ROOT) || !ELDEN_PINNED_ROOT
#error UFS read trial requires the qualified pinned-root source path.
#endif
#include "UfsReadTrial.h"
static bool eldenUfsReadTrial(const NativeUfsBlock *owner,const char *name,
                             uint64_t absolute,uint64_t bytes) {
    const EldenPinnedState *pin=eldenFindPinned(owner);
    if(!pin||!name||(absolute&4095)||(bytes&4095)||bytes/4096!=pin->blocks||
       !eldenUfsIrqRunning()||panic_active()||!ml_get_interrupts_enabled()||!preemption_enabled()) {
        IOLog("ELDEN_UFS_TRIAL refused pin/geometry/IRQ/scheduler\n");return false;
    }
    auto *buffer=static_cast<uint8_t*>(IOMalloc(kDataMax));
    if(!buffer)return false;
    struct Ops {
        const EldenPinnedState *pin;const char *name;uint64_t absolute;uint8_t *buffer;
        uint64_t beforeIrqs,beforeSleeps,beforeWakes,beforeTimeouts,irqs,sleeps,wakes,timeouts;
        bool ready(){return eldenUfsIrqRunning()&&gHost.ready&&!gHost.poisoned&&!panic_active();}
        uint64_t now(){uint64_t ns=0;absolutetime_to_nanoseconds(mach_absolute_time(),&ns);return ns;}
        void polling(bool value){__atomic_store_n(&eldenUfsForcePoll,value?1u:0u,__ATOMIC_RELEASE);}
        void before(){
            beforeIrqs=__atomic_load_n(&eldenUfsIrqs,__ATOMIC_RELAXED);
            beforeSleeps=__atomic_load_n(&eldenUfsSleeps,__ATOMIC_RELAXED);
            beforeWakes=__atomic_load_n(&eldenUfsWakes,__ATOMIC_RELAXED);
            beforeTimeouts=__atomic_load_n(&eldenUfsWaitTimeouts,__ATOMIC_RELAXED);
        }
        void after(){
            irqs=__atomic_load_n(&eldenUfsIrqs,__ATOMIC_RELAXED)-beforeIrqs;
            sleeps=__atomic_load_n(&eldenUfsSleeps,__ATOMIC_RELAXED)-beforeSleeps;
            wakes=__atomic_load_n(&eldenUfsWakes,__ATOMIC_RELAXED)-beforeWakes;
            timeouts=__atomic_load_n(&eldenUfsWaitTimeouts,__ATOMIC_RELAXED)-beforeTimeouts;
        }
        int read(uint64_t index,unsigned blocks){return hostRead4k(0,absolute/4096+index,blocks,buffer);}
        bool verify(uint64_t index,unsigned block){return eldenPinnedRead(pin,index,buffer+block*4096,4096);}
        void record(unsigned seq,unsigned mode,uint64_t index,unsigned blocks,uint64_t ns){
            uint8_t digest[32];char hex[65];static const char digits[]="0123456789abcdef";
            SHA256_CTX hash;SHA256_Init(&hash);SHA256_Update(&hash,buffer,blocks*4096);SHA256_Final(digest,&hash);
            for(unsigned i=0;i<32;++i){hex[i*2]=digits[digest[i]>>4];hex[i*2+1]=digits[digest[i]&15];}hex[64]=0;
            IOLog("ELDEN_UFS_TRIAL row name=%s seq=%u mode=%u block=%llu bytes=%u ns=%llu irqs=%llu sleeps=%llu wakes=%llu timeouts=%llu sha=%s\n",
                  name,seq,mode,index,blocks*4096,ns,irqs,sleeps,wakes,timeouts,hex);
        }
        void finish(bool good,unsigned count){IOLog("ELDEN_UFS_TRIAL end name=%s good=%u rows=%u poll-restored=%u\n",name,good?1u:0u,count,
            __atomic_load_n(&eldenUfsForcePoll,__ATOMIC_ACQUIRE)==0?1u:0u);}
    } io={pin,name,absolute,buffer,0,0,0,0,0,0,0,0};
    IOLog("ELDEN_UFS_TRIAL begin name=%s blocks=%llu samples=64 modes=poll,hybrid IRQ=both warm=4 QD=1\n",name,pin->blocks);
    bool result=eldenRunUfsReadTrial(io,pin->blocks);
    IOFree(buffer,kDataMax);return result;
}
