// SPDX-License-Identifier: BSD-2-Clause-Patent
#include "BatchTrial.h"
static uint8_t *gBatchBuffers[32];
static bool eldenUfsBatchTrial(const NativeUfsBlock *owner,const char *name,uint64_t absolute,uint64_t bytes){
    const EldenPinnedState *pin=eldenFindPinned(owner);
    if(!pin||!name||(absolute&4095)||(bytes&4095)||pin->blocks!=bytes/4096||!queueReady())return false;
    for(unsigned i=0;i<32;i++)if(!gBatchBuffers[i]&&!(gBatchBuffers[i]=eldenAllocateSnapshot(kDataMax)))return false;
    struct Ops {
        const EldenPinnedState *pin;const char *name;uint64_t absolute;
        UfsSlot slots[32];uint64_t deadlines[32];bool taken[32];uint32_t lengths[32];
        uint64_t ns,irqBefore,sleepBefore,wakeBefore,timeoutBefore,directBefore;
        unsigned qd,blocks,pass,peak,commands;SHA256_CTX hash;
        uint64_t now(){uint64_t value;absolutetime_to_nanoseconds(mach_absolute_time(),&value);return value;}
        bool ready(){return queueReady()&&!panic_active();}
        bool depth(unsigned d){qd=d;return gSlotCount>=d;}
        void begin(unsigned d,unsigned n,unsigned p){
            qd=d;blocks=n;pass=p;ns=0;peak=commands=0;SHA256_Init(&hash);
            irqBefore=__atomic_load_n(&eldenUfsIrqs,__ATOMIC_RELAXED);sleepBefore=__atomic_load_n(&eldenUfsSleeps,__ATOMIC_RELAXED);
            wakeBefore=__atomic_load_n(&eldenUfsWakes,__ATOMIC_RELAXED);timeoutBefore=__atomic_load_n(&eldenUfsWaitTimeouts,__ATOMIC_RELAXED);
            directBefore=__atomic_load_n(&gDirectCommands,__ATOMIC_RELAXED);
        }
        bool issue(unsigned i,uint64_t block,unsigned n){
            if(i>=32||taken[i]||!nativeSlotTake(slots[i]))return false;taken[i]=true;lengths[i]=n*4096;
            uint64_t lba=absolute/4096+block;UfsPrd prds[kMaxPrds];
            unsigned count=nativeBuildPrds(gBatchBuffers[i],n*4096,prds);if(!count)return false;
            uint8_t cdb[10]={0x28,0,uint8_t(lba>>24),uint8_t(lba>>16),uint8_t(lba>>8),uint8_t(lba),0,uint8_t(n>>8),uint8_t(n),0};
            slots[i].diagnostic->lba=lba;uint32_t scsi;
            IOReturn result=hostScsiIssue(slots[i],0,cdb,10,2,n*4096,1000000,&deadlines[i],&scsi,prds,count,gBatchBuffers[i]);
            if(result!=kIOReturnSuccess)return false;
            __atomic_add_fetch(&gDirectCommands,1ull,__ATOMIC_RELAXED);commands++;
            uint32_t db=read32(gHost.hc,0x58);unsigned active=0;while(db){db&=db-1;active++;}if(active>peak)peak=active;
            return true;
        }
        bool await(unsigned i){uint32_t scsi;return hostScsiAwait(slots[i],0,lengths[i],deadlines[i],&scsi,gBatchBuffers[i],2)==kIOReturnSuccess;}
        void sample(uint64_t value){ns+=value;}
        bool verify(unsigned i,uint64_t block,unsigned n){
            for(unsigned k=0;k<n;k++)if(!eldenPinnedRead(pin,block+k,gBatchBuffers[i]+k*4096,4096))return false;
            SHA256_Update(&hash,gBatchBuffers[i],n*4096);return true;
        }
        void cleanup(){for(unsigned i=0;i<32;i++)if(taken[i]){nativeSlotGive(slots[i]);taken[i]=false;}}
        void fail(unsigned stage){queueSignalFault();IOLog("ELDEN_UFS_QD fail name=%s stage=%u qd=%u pass=%u commands=%u\n",name,stage,qd,pass,commands);}
        void end(){
            uint8_t digest[32];char text[65];static const char hex[]="0123456789abcdef";SHA256_Final(digest,&hash);
            for(unsigned i=0;i<32;i++){text[2*i]=hex[digest[i]>>4];text[2*i+1]=hex[digest[i]&15];}text[64]=0;
            IOLog("ELDEN_UFS_QD row name=%s qd=%u bytes=%u pass=%u commands=%u io-ns=%llu db-peak=%u direct=%llu irq=%llu sleeps=%llu wakes=%llu timeouts=%llu sha=%s\n",
                name,qd,blocks*4096,pass,commands,ns,peak,__atomic_load_n(&gDirectCommands,__ATOMIC_RELAXED)-directBefore,
                __atomic_load_n(&eldenUfsIrqs,__ATOMIC_RELAXED)-irqBefore,__atomic_load_n(&eldenUfsSleeps,__ATOMIC_RELAXED)-sleepBefore,
                __atomic_load_n(&eldenUfsWakes,__ATOMIC_RELAXED)-wakeBefore,__atomic_load_n(&eldenUfsWaitTimeouts,__ATOMIC_RELAXED)-timeoutBefore,text);
        }
    };
    auto *io=static_cast<Ops*>(IOMalloc(sizeof(Ops)));if(!io)return false;
    bzero(io,sizeof(Ops));io->pin=pin;io->name=name;io->absolute=absolute;
    IOLog("ELDEN_UFS_QD begin name=%s blocks=%llu slots=%u samples=24\n",name,pin->blocks,gSlotCount);
    bool good=eldenRunBatchTrial(*io,pin->blocks);io->cleanup();IOFree(io,sizeof(Ops));
    IOLog("ELDEN_UFS_QD end name=%s good=%u\n",name,good?1u:0u);return good;
}
