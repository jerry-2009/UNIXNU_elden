// SPDX-License-Identifier: BSD-2-Clause-Patent
// Included after the existing host/cache primitives. QueueCore/DmaPlan are
// included at translation-unit scope to keep their C ABI types identical.
#if !defined(NATIVE_UFS_READ_ONLY) || !NATIVE_UFS_READ_ONLY
#error This queue adapter is qualified only for the existing read-only root path.
#endif
struct UfsPrd;
struct UfsSlot {
    unsigned index;uint32_t entry,bit;
    uint8_t *utrd,*ucd,*data;uint64_t ucdPhys,dataPhys;
    EldenUfsLease lease;UfsRootDiagnostics *diagnostic;
};
static UfsSlot gSlotGeom[kSlots];
static UfsRootDiagnostics gSlotDiagnostics[kSlots];
static int8_t gEntrySlot[32];
static volatile uint32_t gOutstanding,gSlotGen[kSlots];
static volatile uint64_t gSlotIssuedAt[kSlots];
static volatile uint8_t gSlotOpcode[kSlots];
static bool gListUncached;
static uint64_t gUtrlPhys,gDmaLimit;
static unsigned gSlotCount=1;
static EldenUfsPool gQueuePool={};
static volatile uint32_t gQueueFailed,gQueueFinalStop,gQueueFailureRecorded;
static volatile uint64_t gQueueCommands,gDirectCommands,gStagedCommands;
static IOBufferMemoryDescriptor *gListDma,*gRegionB;
static IOMemoryMap *gListMap;
static IOLock *gSnapshotLock;
struct EldenSnapshot {IOBufferMemoryDescriptor *descriptor;uint8_t *bytes;uint64_t length;};
static EldenSnapshot gSnapshots[64];
static volatile unsigned gSnapshotCount;
static void eldenUfsIrqStop();
static bool eldenUfsIrqRunning();
static void hostWaitCompletion(unsigned,uint32_t,uint64_t,uint64_t);
static uint32_t hostCompletionCount(unsigned s){return __atomic_load_n(&gSlotGen[s],__ATOMIC_ACQUIRE);}
static bool hostInterruptMode(){return eldenUfsIrqRunning();}
static bool queueFailed(){return __atomic_load_n(&gQueueFailed,__ATOMIC_ACQUIRE)!=0;}
static bool queueFinalStop(){return __atomic_load_n(&gQueueFinalStop,__ATOMIC_ACQUIRE)!=0;}
static bool queueReady(){return __atomic_load_n(&gHost.ready,__ATOMIC_ACQUIRE)&&!queueFailed()&&!queueFinalStop();}
static void queueSignalFault(){
    __atomic_store_n(&gQueueFailed,1u,__ATOMIC_RELEASE);
    __atomic_store_n(&gHost.poisoned,true,__ATOMIC_RELEASE);
    __atomic_store_n(&gHost.ready,false,__ATOMIC_RELEASE);
    eldenUfsIrqStop();thread_wakeup((event_t)&gQueuePool);
}
static void queueApplyStopLocked(){
    if(queueFailed()||queueFinalStop())elden_ufs_pool_stop(&gQueuePool,queueFailed());
}
static IOReturn recordSlotTransport(const UfsSlot &slot,IOReturn result,uint32_t ocs){
    slot.diagnostic->result=static_cast<uint32_t>(result);slot.diagnostic->ocs=ocs;
    if(result!=kIOReturnSuccess){
        uint32_t zero=0;
        if(__atomic_compare_exchange_n(&gQueueFailureRecorded,&zero,1u,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){
            // Only the first failing command publishes a legacy diagnostic.
            // No concurrent response decision reads that global snapshot.
            gRootDiagnostic=*slot.diagnostic;recordTransport(result,ocs);
        }
    }
    return result;
}
static bool nativeSlotTake(UfsSlot &out){
    if(!gHost.lock||panic_active()||queueFailed()||queueFinalStop())return false;
    IOLockLock(gHost.lock);queueApplyStopLocked();
    EldenUfsWaiter waiter={};EldenUfsPoolResult result=elden_ufs_pool_enqueue(&gQueuePool,&waiter);
    uint64_t deadline=0;clock_interval_to_deadline(1000,kMillisecondScale,&deadline);
    while(result==EldenUfsQueued&&waiter.state==1){
        queueApplyStopLocked();if(waiter.state!=1)break;
        uint64_t now=mach_absolute_time();
        if(now>=deadline||!preemption_enabled()||!ml_get_interrupts_enabled()){
            elden_ufs_pool_cancel(&gQueuePool,&waiter);break;
        }
        uint64_t remaining=0;absolutetime_to_nanoseconds(deadline-now,&remaining);
        uint32_t micros=remaining/1000<1000?static_cast<uint32_t>(remaining/1000):1000;
        if(!micros){elden_ufs_pool_cancel(&gQueuePool,&waiter);break;}
        if(assert_wait_timeout((event_t)&gQueuePool,THREAD_UNINT,micros,NSEC_PER_USEC)!=THREAD_WAITING){
            elden_ufs_pool_cancel(&gQueuePool,&waiter);break;
        }
        if(queueFailed()||queueFinalStop()){
            clear_wait(current_thread(),THREAD_AWAKENED);queueApplyStopLocked();break;
        }
        IOLockUnlock(gHost.lock);thread_block(THREAD_CONTINUE_NULL);IOLockLock(gHost.lock);
    }
    if(waiter.state==1)elden_ufs_pool_cancel(&gQueuePool,&waiter);
    bool good=waiter.state==2&&!queueFailed()&&!queueFinalStop();
    if(good){out=gSlotGeom[waiter.lease.slot];out.lease=waiter.lease;}
    else if(waiter.state==2)elden_ufs_pool_release(&gQueuePool,&waiter.lease);
    IOLockUnlock(gHost.lock);return good;
}
static void nativeSlotGive(const UfsSlot &slot){
    IOLockLock(gHost.lock);queueApplyStopLocked();
    (void)elden_ufs_pool_release(&gQueuePool,&slot.lease);
    IOLockUnlock(gHost.lock);thread_wakeup((event_t)&gQueuePool);
}
struct NativeSlotGuard {
    UfsSlot slot={};bool valid;
    NativeSlotGuard():valid(nativeSlotTake(slot)){}
    ~NativeSlotGuard(){if(valid)nativeSlotGive(slot);}
};
static IOReturn nativeRingSlot(const UfsSlot &slot){
    IOLockLock(gHost.lock);queueApplyStopLocked();
    auto state=elden_ufs_pool_issue(&gQueuePool,&slot.lease);
    if(state==EldenUfsGranted){
        __atomic_or_fetch(&gOutstanding,slot.bit,__ATOMIC_RELEASE);
        gSlotOpcode[slot.index]=slot.ucd[slot.ucd[0]==1?16:0];
        __atomic_store_n(&gSlotIssuedAt[slot.index],mach_absolute_time(),__ATOMIC_RELAXED);
        hostWrite(0x58,slot.bit);
    }
    IOLockUnlock(gHost.lock);
    return state==EldenUfsGranted?kIOReturnSuccess:kIOReturnNotReady;
}
static bool nativeCompleteSlot(const UfsSlot &slot,uint32_t db,uint32_t ocs,uint32_t status){
    IOLockLock(gHost.lock);queueApplyStopLocked();
    auto result=elden_ufs_pool_complete(&gQueuePool,&slot.lease,db,ocs,status);
    IOLockUnlock(gHost.lock);
    if(result!=EldenUfsGranted)return false;
    __atomic_and_fetch(&gOutstanding,~slot.bit,__ATOMIC_RELEASE);
    __atomic_store_n(&gSlotIssuedAt[slot.index],0,__ATOMIC_RELAXED);return true;
}
static void hostSlotGeometry(unsigned i,uint8_t *utrd,unsigned entry,uint8_t *ucd,uint64_t ucdPhys,uint8_t *data,uint64_t dataPhys){
    gSlotGeom[i]={i,entry,1u<<entry,utrd,ucd,data,ucdPhys,dataPhys,{},&gSlotDiagnostics[i]};
    gEntrySlot[entry]=static_cast<int8_t>(i);
}
static bool nativeRange(uint64_t pa,uint64_t size){return gDmaLimit&&pa&&pa<gDmaLimit&&size&&size<=gDmaLimit-pa;}
static IOBufferMemoryDescriptor *nativeContiguous(unsigned bytes,uint8_t **va,uint64_t *pa,IOOptionBits cache=0){
    auto *dma=IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,
        static_cast<IOOptionBits>(kIODirectionInOut)|static_cast<IOOptionBits>(kIOMemoryPhysicallyContiguous)|
        static_cast<IOOptionBits>(kIOMemoryMapperNone)|cache,bytes,4096);
    if(!dma)return nullptr;
    IOByteCount contiguous=0;*va=static_cast<uint8_t*>(dma->getBytesNoCopy());
    *pa=dma->getPhysicalSegment(0,&contiguous,kIOMemoryMapperNone);
    if(!*va||!*pa||(*pa&4095)||contiguous<bytes||(gDmaLimit&&!nativeRange(*pa,bytes))||
       (!(read32(gHost.hc,0)&0x01000000)&&(*pa>=0x100000000ULL||bytes>0x100000000ULL-*pa))){dma->release();return nullptr;}
    bzero(*va,bytes);cacheCivac(*va,bytes);return dma;
}
static bool eldenAllocateQueue(const char **why){
    unsigned entries=(read32(gHost.hc,0)&31)+1;
    unsigned possible=(entries+1)/2; if(possible>kRegionSlots)possible=kRegionSlots;
    gHost.lock=IOLockAlloc();gSnapshotLock=IOLockAlloc();
    if(!gHost.lock||!gSnapshotLock){*why="queue mutex allocation";return false;}
    const unsigned sizes[]={kDmaBytes,kDmaBytesEightSlots,kDmaBytesOneSlot};
    const unsigned counts[]={kRegionSlots,8,1};
    for(unsigned i=0;i<3&&!gHost.dma;i++){
        if(counts[i]>possible&&counts[i]!=1)continue;
        gHost.dma=nativeContiguous(sizes[i],&gHost.virt,&gHost.phys);
        if(gHost.dma){gHost.dmaBytes=sizes[i];gSlotCount=counts[i];}
    }
    if(!gHost.dma){*why="queue DMA allocation/address";return false;}
    gUtrlPhys=gHost.phys;gListUncached=false;
    for(unsigned i=0;i<32;i++)gEntrySlot[i]=-1;
    for(unsigned i=0;i<gSlotCount;i++)hostSlotGeometry(i,gHost.virt+ufsSlotUtrdOffset(i),ufsSlotEntry(i),
        gHost.virt+ufsSlotUcdOffset(i),gHost.phys+ufsSlotUcdOffset(i),gHost.virt+ufsSlotDataOffset(i),gHost.phys+ufsSlotDataOffset(i));
    return true;
}
@TRANSLATE@
static bool nativeUncachedPage(uintptr_t va,uint64_t pa){
    uint64_t r=0,w=0;queueTranslate(va,&r,&w);
    IOLog("ELDEN_UFS_QUEUE list-map va=%llx pa=%llx read-par=%llx write-par=%llx\n",static_cast<uint64_t>(va),pa,r,w);
    return !(r&1)&&!(w&1)&&((r>>56)&255)==0x44&&((w>>56)&255)==0x44&&
        (r&0x0000fffffffff000ULL)==pa&&(w&0x0000fffffffff000ULL)==pa;
}
static bool eldenUpgradeQueue(const char **why){
    // The inherited identity check has already succeeded for region A. No
    // new stream/bank is configured; every allocation stays in that range.
    gDmaLimit=elden_ufs_dma_limit(read32(gHost.smmu,0x28),(read32(gHost.hc,0)&0x01000000)!=0,true);
    if(!nativeRange(gHost.phys,gHost.dmaBytes)){*why="queue exceeds inherited DMA width";return false;}
    const unsigned entries=(read32(gHost.hc,0)&31)+1;uint8_t *cached=nullptr;uint64_t pa=0;
    auto *list=nativeContiguous(4096,&cached,&pa,kIOMapWriteCombineCache);
    IOMemoryMap *map=list?list->createMappingInTask(kernel_task,0,kIOMapAnywhere|kIOMapWriteCombineCache):nullptr;
    uintptr_t va=map?map->getVirtualAddress():0;
    if(va&&nativeUncachedPage(va,pa)){
        // The old cached alias was cleaned/invalidated by nativeContiguous and
        // is never used again. Descriptor/list objects remain platform-lived.
        auto *memory=reinterpret_cast<volatile uint32_t*>(va);
        for(unsigned i=0;i<1024;i++)memory[i]=0;
        __asm__ volatile("dsb sy":::"memory");
        gListDma=list;gListMap=map;gListUncached=true;gUtrlPhys=pa;
        for(unsigned i=0;i<32;i++)gEntrySlot[i]=-1;
        for(unsigned i=0;i<gSlotCount;i++)hostSlotGeometry(i,reinterpret_cast<uint8_t*>(va)+32*i,i,
            gHost.virt+ufsSlotUcdOffset(i),gHost.phys+ufsSlotUcdOffset(i),gHost.virt+ufsSlotDataOffset(i),gHost.phys+ufsSlotDataOffset(i));
        uint8_t *b=nullptr;uint64_t bpa=0;
        if(gSlotCount==kRegionSlots&&entries==32&&(gRegionB=nativeContiguous(kRegionBBytes,&b,&bpa))){
            for(unsigned i=0;i<kRegionSlots;i++)hostSlotGeometry(kRegionSlots+i,reinterpret_cast<uint8_t*>(va)+32*(kRegionSlots+i),kRegionSlots+i,
                b+i*kUcdStride,bpa+i*kUcdStride,b+kRegionBDataOffset+i*kDataMax,bpa+kRegionBDataOffset+i*kDataMax);
            gSlotCount=32;
        }
    }else {if(map)map->release();if(list)list->release();}
    if(elden_ufs_pool_init(&gQueuePool,gSlotCount,entries,gListUncached?1:2)!=EldenUfsGranted){*why="queue pool geometry";return false;}
    IOLog("ELDEN_UFS_QUEUE configured slots=%u entries=%u uncached=%u list=%llx dma-limit=%llx\n",gSlotCount,entries,gListUncached?1u:0u,gUtrlPhys,gDmaLimit);
    return true;
}
static uint64_t nativeSnapshotPage(void *context,uint64_t offset){
    auto *s=static_cast<EldenSnapshot*>(context);IOByteCount length=0;
    uint64_t pa=s->descriptor->getPhysicalSegment(offset,&length,kIOMemoryMapperNone);
    return length>=4096?pa:0;
}
static uint8_t *eldenAllocateSnapshot(unsigned bytes){
    if(!bytes||(bytes&4095)||bytes>1U<<20||!gSnapshotLock||queueFailed()||queueFinalStop())return nullptr;
    auto *dma=IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,
        static_cast<IOOptionBits>(kIODirectionInOut)|static_cast<IOOptionBits>(kIOMemoryMapperNone),bytes,4096);
    if(!dma)return nullptr;
    if(dma->prepare(kIODirectionInOut)!=kIOReturnSuccess){dma->release();return nullptr;}
    auto abandon=[dma](){if(dma->complete(kIODirectionInOut)==kIOReturnSuccess)dma->release();};
    auto *va=static_cast<uint8_t*>(dma->getBytesNoCopy());
    if(!va||(reinterpret_cast<uintptr_t>(va)&4095)){abandon();return nullptr;}
    EldenSnapshot candidate={dma,va,bytes};
    // A fragmented 1MiB buffer may need a bounce path; reject only pages that
    // the inherited stream cannot address, not the valid PRDT-count fallback.
    for(unsigned at=0;at<bytes;at+=4096)if(!nativeRange(nativeSnapshotPage(&candidate,at),4096)){abandon();return nullptr;}
    IOLockLock(gSnapshotLock);unsigned n=gSnapshotCount;
    if(n==64){IOLockUnlock(gSnapshotLock);abandon();return nullptr;}
    gSnapshots[n]=candidate;__atomic_store_n(&gSnapshotCount,n+1,__ATOMIC_RELEASE);IOLockUnlock(gSnapshotLock);
    return va;
}
static void eldenRetireSnapshot(uint8_t *){
    // Bounded registered snapshots are retained for the platform lifetime,
    // including timeout/panic. There is no free of caller memory under DMA.
}
static unsigned nativeBuildPrds(const void *buffer,uint64_t bytes,UfsPrd *out);
