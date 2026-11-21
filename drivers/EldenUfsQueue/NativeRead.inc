// SPDX-License-Identifier: BSD-2-Clause-Patent
// Physical addresses come only from retained, driver-owned snapshot descriptors.
static unsigned nativeBuildPrds(const void *buffer,uint64_t bytes,UfsPrd *out){
    if(!buffer||!out||!bytes||bytes>kXferMax)return 0;
    uintptr_t address=reinterpret_cast<uintptr_t>(buffer);
    unsigned count=__atomic_load_n(&gSnapshotCount,__ATOMIC_ACQUIRE);
    for(unsigned i=0;i<count;i++){
        EldenSnapshot &s=gSnapshots[i];uintptr_t base=reinterpret_cast<uintptr_t>(s.bytes);
        if(address<base||address-base>s.length||bytes>s.length-(address-base))continue;
        struct Page {EldenSnapshot *s;uint64_t offset;} context={&s,address-base};
        auto map=[](void *opaque,uint64_t offset)->uint64_t{
            auto *p=static_cast<Page*>(opaque);return nativeSnapshotPage(p->s,p->offset+offset);
        };
        EldenUfsPrdtPlan plan;
        if(!elden_ufs_prdt_build(address,bytes,s.length-context.offset,gDmaLimit,map,&context,&plan))return 0;
        for(unsigned n=0;n<plan.count;n++){out[n].addr=plan.entries[n].address;out[n].bytes=plan.entries[n].bytes;}
        return plan.count;
    }
    return 0; // ordinary caller memory retains the existing owned bounce path
}
static IOReturn hostRead4k(uint8_t lun,uint64_t lba,uint32_t blocks,void *dst){
    if(!queueReady()||!dst||!blocks||lba>0xffffffffULL-(blocks-1))return kIOReturnBadArgument;
    UfsPrd prd[kMaxPrds];unsigned prds=blocks<=kXferMax/4096?nativeBuildPrds(dst,uint64_t(blocks)*4096,prd):0;
    if(!prds&&blocks>kDataMax/4096){
        const uint32_t step=blocks>kXferMax/4096?kXferMax/4096:kDataMax/4096;
        for(uint32_t done=0;done<blocks;done+=step){
            uint32_t count=blocks-done>step?step:blocks-done;
            IOReturn result=hostRead4k(lun,lba+done,count,static_cast<uint8_t*>(dst)+uint64_t(done)*4096);
            if(result!=kIOReturnSuccess)return result;
        }
        return kIOReturnSuccess;
    }
    NativeSlotGuard guard;if(!guard.valid)return kIOReturnNotReady;
    const UfsSlot &slot=guard.slot;slot.diagnostic->lba=lba;
    __atomic_fetch_add(prds?&gDirectCommands:&gStagedCommands,1ull,__ATOMIC_RELAXED);
    uint8_t cdb[10]={0x28,0,uint8_t(lba>>24),uint8_t(lba>>16),uint8_t(lba>>8),uint8_t(lba),0,uint8_t(blocks>>8),uint8_t(blocks),0};
    uint32_t scsi=0;
    IOReturn result=hostScsiDir(slot,lun,cdb,10,2,blocks*4096U,1000000,&scsi,prds?prd:nullptr,prds,prds?dst:nullptr);
    if(result==kIOReturnSuccess&&!prds)memcpy(dst,slot.data,blocks*4096U);
    return result; // no BUSY retry, cancel/reset or release of uncertain DMA
}
