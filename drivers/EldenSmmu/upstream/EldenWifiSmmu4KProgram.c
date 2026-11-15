/* SPDX-License-Identifier: MIT */
#include "EldenWifiSmmu4KProgram.h"
#define FSR_FAULT UINT32_C(0xc00001fe)
static int read_image(const EldenWifiSmmu4KIo *io,size_t gr1,size_t cb,unsigned bank,
    EldenWifiSmmu4KContextImage *v)
{
    v->reserved_zero=0;
    return io->read32(io->cookie,gr1+bank*4,&v->cbar) ||
        io->read32(io->cookie,gr1+0x800+bank*4,&v->cba2r) ||
        io->read32(io->cookie,cb+0x30,&v->tcr) ||
        io->read32(io->cookie,cb+0x10,&v->tcr2) ||
        io->read64(io->cookie,cb+0x20,&v->ttbr0) ||
        io->read64(io->cookie,cb+0x28,&v->ttbr1) ||
        io->read32(io->cookie,cb+0x38,&v->mair0) ||
        io->read32(io->cookie,cb+0x3c,&v->mair1) ||
        io->read32(io->cookie,cb,&v->sctlr);
}
static int write32(const EldenWifiSmmu4KIo *io,size_t at,uint32_t value,EldenWifiSmmu4KProgramResult *r)
{
    ++r->writes;return io->write32(io->cookie,at,value);
}
static int write64(const EldenWifiSmmu4KIo *io,size_t at,uint64_t value,EldenWifiSmmu4KProgramResult *r)
{
    ++r->writes;return io->write64(io->cookie,at,value);
}
/* TLBIASID (+0x610, value = ASID) or, with all set, TLBIALL (+0x618, value ignored), then TLBSYNC/TLBSTATUS. */
static EldenWifiSmmu4KStatus sync_tlb(const EldenWifiSmmu4KIo *io,size_t cb,unsigned asid,unsigned all,
    unsigned budget,EldenWifiSmmu4KProgramResult *r)
{
    r->tlb_synchronized=0;
    if(io->barrier(io->cookie) || write32(io,cb+(all?0x618:0x610),all?0:asid,r) ||
        write32(io,cb+0x7f0,UINT32_MAX,r) || io->barrier(io->cookie))return EldenWifiSmmu4KIoError;
    for(unsigned i=0;i<budget;++i) {
        uint32_t status;++r->poll_reads;
        if(io->read32(io->cookie,cb+0x7f4,&status))return EldenWifiSmmu4KIoError;
        if(!(status&1)) {
            /* Order the completed device observation before callers recycle
             * normal-memory tables or publish subsequent context work. */
            if(io->barrier(io->cookie))return EldenWifiSmmu4KIoError;
            r->tlb_synchronized=1;return EldenWifiSmmu4KSuccess;
        }
    }
    return EldenWifiSmmu4KTimeout;
}
static EldenWifiSmmu4KStatus sync_asid(const EldenWifiSmmu4KIo *io,size_t cb,unsigned asid,
    unsigned budget,EldenWifiSmmu4KProgramResult *r)
{
    return sync_tlb(io,cb,asid,0,budget,r);
}
static EldenWifiSmmu4KStatus disable_sync(const EldenWifiSmmu4KIo *io,size_t cb,unsigned asid,
    unsigned budget,EldenWifiSmmu4KProgramResult *r)
{
    r->must_retain_tables=1;r->disabled_verified=0;
    uint32_t value;
    if(write32(io,cb,0,r) || io->barrier(io->cookie) || io->read32(io->cookie,cb,&value))return EldenWifiSmmu4KIoError;
    if(value)return EldenWifiSmmu4KStateMismatch;
    r->disabled_verified=1;r->enabled=0;
    EldenWifiSmmu4KStatus status=sync_asid(io,cb,asid,budget,r);
    if(status==EldenWifiSmmu4KSuccess)r->must_retain_tables=0;
    return status;
}
static EldenWifiSmmu4KStatus prepare(const EldenWifiSmmu4KIo *io,unsigned bank,
    const EldenWifiSmmu4KContextConfig *config,unsigned budget,EldenWifiSmmu4KProgramResult *r,
    EldenWifiSmmu4KContextConfig *actual,EldenWifiSmmu4KContextImage *image,size_t *gr1)
{
    if(!r)return EldenWifiSmmu4KArgument;
    *r=(EldenWifiSmmu4KProgramResult){0};
    r->must_retain_tables=1;
    if(!io || !config || !io->read32 || !io->read64 || !io->write32 || !io->write64 ||
        !io->barrier || io->register_bytes<0x2c || !budget || budget>1048576 || bank>255)return EldenWifiSmmu4KArgument;
    r->phase=1;
    if(io->read32(io->cookie,0x20,&r->id0) || io->read32(io->cookie,0x24,&r->id1) ||
        io->read32(io->cookie,0x28,&r->id2))return EldenWifiSmmu4KIoError;
    unsigned shift=(r->id1>>31)?16:12;
    size_t pages=(size_t)1<<(((r->id1>>28)&7)+1);
    size_t stride=(size_t)1<<shift;
    unsigned banks=r->id1&255,s2=(r->id1>>16)&255;
    if(!banks || banks>pages || s2>banks || bank<s2 || bank>=banks ||
        io->register_bytes<2*pages*stride)return EldenWifiSmmu4KUnsupported;
    *gr1=stride;r->context_offset=(pages+bank)*stride;
    if(r->context_offset>io->register_bytes || io->register_bytes-r->context_offset<0x7f8 ||
        *gr1+0x804+bank*4>io->register_bytes)return EldenWifiSmmu4KBadRange;
    *actual=*config;actual->id0=r->id0;actual->id2=r->id2;
    return EldenWifiSmmu4KEncodeContext(actual,image);
}
EldenWifiSmmu4KStatus EldenWifiSmmu4KProgramDisabledContext(const EldenWifiSmmu4KIo *io,unsigned bank,
    const EldenWifiSmmu4KContextConfig *config,unsigned budget,EldenWifiSmmu4KProgramResult *r)
{
    EldenWifiSmmu4KContextConfig actual;EldenWifiSmmu4KContextImage image;size_t gr1;
    EldenWifiSmmu4KStatus status=prepare(io,bank,config,budget,r,&actual,&image,&gr1);
    if(status!=EldenWifiSmmu4KSuccess)return status;
    size_t cb=(size_t)r->context_offset;uint32_t sctlr;
    if(io->read32(io->cookie,cb,&sctlr))return EldenWifiSmmu4KIoError;
    if(sctlr&1){r->enabled=1;return EldenWifiSmmu4KBusy;}
    r->must_retain_tables=1;r->phase=2;
    /* A disabled owned bank only. TCR2/TCR precede all TTBR accesses. */
    if(write32(io,cb,0,r) || io->barrier(io->cookie) ||
        write32(io,gr1+0x800+bank*4,image.cba2r,r) || write32(io,gr1+bank*4,image.cbar,r) ||
        write32(io,cb+0x10,image.tcr2,r) || write32(io,cb+0x30,image.tcr,r) ||
        write64(io,cb+0x20,image.ttbr0,r) || write64(io,cb+0x28,image.ttbr1,r) ||
        write32(io,cb+0x38,image.mair0,r) || write32(io,cb+0x3c,image.mair1,r) ||
        write32(io,cb+0x58,UINT32_MAX,r)) {status=EldenWifiSmmu4KIoError;goto failed;}
    status=sync_asid(io,cb,actual.asid,budget,r);if(status!=EldenWifiSmmu4KSuccess)goto failed;
    r->phase=3;
    if(read_image(io,gr1,cb,bank,&r->readback)) {status=EldenWifiSmmu4KIoError;goto failed;}
    r->readback_valid=1;
    /* Verify configuration while M is still zero; never enable a bad granule. */
    sctlr=r->readback.sctlr;r->readback.sctlr=image.sctlr;
    status=EldenWifiSmmu4KValidateContextReadback(&actual,&r->readback);r->readback.sctlr=sctlr;
    if(status!=EldenWifiSmmu4KSuccess || sctlr) {status=EldenWifiSmmu4KStateMismatch;goto failed;}
    r->readback_valid=0;
    if(io->barrier(io->cookie) || write32(io,cb,image.sctlr,r) || io->barrier(io->cookie)) {status=EldenWifiSmmu4KIoError;goto failed;}
    r->phase=4;
    if(read_image(io,gr1,cb,bank,&r->readback)) {status=EldenWifiSmmu4KIoError;goto failed;}
    r->readback_valid=1;r->enabled=r->readback.sctlr&1;
    if(io->read32(io->cookie,cb+0x58,&r->fault_status)) {status=EldenWifiSmmu4KIoError;goto failed;}
    status=EldenWifiSmmu4KValidateContextReadback(&actual,&r->readback);if(status!=EldenWifiSmmu4KSuccess)goto failed;
    if(r->fault_status&FSR_FAULT) {status=EldenWifiSmmu4KFault;goto failed;}
    r->phase=5;r->enabled=1;return EldenWifiSmmu4KSuccess;
failed:
    /* Even a reported failed write may have reached hardware. On uncertainty
     * retain all tables/leases; never claim safe recycling after timeout. */
    r->readback_valid=0;(void)disable_sync(io,cb,actual.asid,budget,r);
    r->phase=6;return status;
}
EldenWifiSmmu4KStatus EldenWifiSmmu4KDisableOwnedContext(const EldenWifiSmmu4KIo *io,unsigned bank,
    const EldenWifiSmmu4KContextConfig *config,unsigned budget,EldenWifiSmmu4KProgramResult *r)
{
    EldenWifiSmmu4KContextConfig actual;EldenWifiSmmu4KContextImage image;size_t gr1;
    EldenWifiSmmu4KStatus status=prepare(io,bank,config,budget,r,&actual,&image,&gr1);
    if(status!=EldenWifiSmmu4KSuccess)return status;
    size_t cb=(size_t)r->context_offset;r->must_retain_tables=1;
    if(read_image(io,gr1,cb,bank,&r->readback))return EldenWifiSmmu4KIoError;
    r->readback_valid=1;uint32_t sctlr=r->readback.sctlr;
    /* An enabled bank must match the owned image (ValidateContextReadback, with its documented read-only bits); a
     * disabled one is compared with SCTLR substituted. */
    if(sctlr)status=EldenWifiSmmu4KValidateContextReadback(&actual,&r->readback);
    else {r->readback.sctlr=image.sctlr;status=EldenWifiSmmu4KValidateContextReadback(&actual,&r->readback);r->readback.sctlr=sctlr;}
    if(status!=EldenWifiSmmu4KSuccess)return status; /* Another context: do not touch. */
    r->readback_valid=0;status=disable_sync(io,cb,actual.asid,budget,r);r->phase=status==EldenWifiSmmu4KSuccess?7:6;
    return status;
}

EldenWifiSmmu4KStatus EldenWifiSmmu4KObserveOwnedContext(const EldenWifiSmmu4KIo *io,unsigned bank,
    const EldenWifiSmmu4KContextConfig *config,EldenWifiSmmu4KProgramResult *r)
{
    EldenWifiSmmu4KContextConfig actual;EldenWifiSmmu4KContextImage image;size_t gr1;
    EldenWifiSmmu4KStatus status=prepare(io,bank,config,1,r,&actual,&image,&gr1);
    if(status!=EldenWifiSmmu4KSuccess)return status;
    if(read_image(io,gr1,(size_t)r->context_offset,bank,&r->readback))return EldenWifiSmmu4KIoError;
    r->readback_valid=1;r->enabled=r->readback.sctlr&1;
    status=EldenWifiSmmu4KValidateContextReadback(&actual,&r->readback);
    if(status!=EldenWifiSmmu4KSuccess)return status;
    if(io->read32(io->cookie,(size_t)r->context_offset+0x58,&r->fault_status) || io->barrier(io->cookie))return EldenWifiSmmu4KIoError;
    if(r->fault_status&FSR_FAULT)return EldenWifiSmmu4KFault;
    r->phase=8;return EldenWifiSmmu4KSuccess;
}

static EldenWifiSmmu4KStatus synchronize(const EldenWifiSmmu4KIo *io,unsigned bank,
    const EldenWifiSmmu4KContextConfig *config,unsigned all,unsigned budget,EldenWifiSmmu4KProgramResult *r)
{
    if(!r)return EldenWifiSmmu4KArgument;
    *r=(EldenWifiSmmu4KProgramResult){0};r->must_retain_tables=1;
    if(!budget || budget>1048576)return EldenWifiSmmu4KArgument;
    EldenWifiSmmu4KStatus status=EldenWifiSmmu4KObserveOwnedContext(io,bank,config,r);
    if(status!=EldenWifiSmmu4KSuccess)return status;
    status=sync_tlb(io,(size_t)r->context_offset,config->asid,all,budget,r);
    if(status!=EldenWifiSmmu4KSuccess)return status;
    EldenWifiSmmu4KProgramResult after;
    status=EldenWifiSmmu4KObserveOwnedContext(io,bank,config,&after);
    r->readback=after.readback;r->readback_valid=after.readback_valid;
    r->fault_status=after.fault_status;r->enabled=after.enabled;
    if(status!=EldenWifiSmmu4KSuccess)return status;
    if(r->id0!=after.id0 || r->id1!=after.id1 || r->id2!=after.id2 ||
        r->context_offset!=after.context_offset)return EldenWifiSmmu4KStateMismatch;
    r->phase=9;return EldenWifiSmmu4KSuccess;
}
EldenWifiSmmu4KStatus EldenWifiSmmu4KWriteContextTtbr0(const EldenWifiSmmu4KIo *io,uint64_t context_offset,uint64_t ttbr0,EldenWifiSmmu4KProgramResult *r)
{
    if(!r)return EldenWifiSmmu4KArgument;
    *r=(EldenWifiSmmu4KProgramResult){0};r->must_retain_tables=1;
    if(!io || !io->write64 || !io->read64 || !io->barrier || !context_offset || (ttbr0&0xfffu) ||
        context_offset>io->register_bytes || io->register_bytes-context_offset<0x7f8)return EldenWifiSmmu4KArgument;
    r->context_offset=context_offset;
    uint64_t readback=0;
    if(io->barrier(io->cookie) || write64(io,(size_t)context_offset+0x20,ttbr0,r) || io->barrier(io->cookie) ||
        io->read64(io->cookie,(size_t)context_offset+0x20,&readback))return EldenWifiSmmu4KIoError;
    if(readback!=ttbr0)return EldenWifiSmmu4KStateMismatch;
    r->phase=9;return EldenWifiSmmu4KSuccess;
}
EldenWifiSmmu4KStatus EldenWifiSmmu4KSyncContextTlb(const EldenWifiSmmu4KIo *io,uint64_t context_offset,unsigned asid,unsigned all,
    unsigned budget,EldenWifiSmmu4KProgramResult *r)
{
    if(!r)return EldenWifiSmmu4KArgument;
    *r=(EldenWifiSmmu4KProgramResult){0};r->must_retain_tables=1;
    if(!io || !io->write32 || !io->read32 || !io->barrier || !budget || budget>1048576 || !context_offset ||
        context_offset>io->register_bytes || io->register_bytes-context_offset<0x7f8)return EldenWifiSmmu4KArgument;
    r->context_offset=context_offset;
    EldenWifiSmmu4KStatus status=sync_tlb(io,(size_t)context_offset,asid,all,budget,r);
    if(status==EldenWifiSmmu4KSuccess)r->phase=9;
    return status;
}
EldenWifiSmmu4KStatus EldenWifiSmmu4KSyncContextTlbPages(const EldenWifiSmmu4KIo *io,uint64_t context_offset,unsigned asid,
    const EldenWifiSmmu4KRange *ranges,size_t count,unsigned budget,EldenWifiSmmu4KProgramResult *r)
{
    if(!r)return EldenWifiSmmu4KArgument;
    *r=(EldenWifiSmmu4KProgramResult){0};r->must_retain_tables=1;
    if(!io || !io->write32 || !io->write64 || !io->read32 || !io->barrier || !budget || budget>1048576 || !context_offset ||
        context_offset>io->register_bytes || io->register_bytes-context_offset<0x7f8 || !count || !ranges || asid>0xffff)
        return EldenWifiSmmu4KArgument;
    size_t pages=0;
    for(size_t i=0;i<count;++i) {
        if(((ranges[i].iova|ranges[i].bytes)&4095) || !ranges[i].bytes || ranges[i].bytes/4096>EldenWifiSmmu4KTlbPageLimit-pages)
            return EldenWifiSmmu4KArgument;
        pages+=(size_t)(ranges[i].bytes/4096);
    }
    r->context_offset=context_offset;r->tlb_synchronized=0;
    const size_t cb=(size_t)context_offset;
    if(io->barrier(io->cookie))return EldenWifiSmmu4KIoError;
    /* TLBIVAL (+0x620), AArch64 format: VA[55:12] in bits 43:0, the ASID in bits 63:48. Leaf entries only: the tables above the leaves
     * are fixed for the context's life. */
    for(size_t i=0;i<count;++i)for(uint64_t offset=0;offset<ranges[i].bytes;offset+=4096)
        if(write64(io,cb+0x620,(((ranges[i].iova+offset)>>12)&((UINT64_C(1)<<44)-1))|((uint64_t)asid<<48),r))return EldenWifiSmmu4KIoError;
    if(write32(io,cb+0x7f0,UINT32_MAX,r) || io->barrier(io->cookie))return EldenWifiSmmu4KIoError;
    for(unsigned i=0;i<budget;++i) {
        uint32_t status;++r->poll_reads;
        if(io->read32(io->cookie,cb+0x7f4,&status))return EldenWifiSmmu4KIoError;
        if(!(status&1)) {
            if(io->barrier(io->cookie))return EldenWifiSmmu4KIoError;
            r->tlb_synchronized=1;r->phase=9;return EldenWifiSmmu4KSuccess;
        }
    }
    return EldenWifiSmmu4KTimeout;
}
EldenWifiSmmu4KStatus EldenWifiSmmu4KSynchronizeOwnedContext(const EldenWifiSmmu4KIo *io,unsigned bank,
    const EldenWifiSmmu4KContextConfig *config,unsigned budget,EldenWifiSmmu4KProgramResult *r)
{return synchronize(io,bank,config,0,budget,r);}
EldenWifiSmmu4KStatus EldenWifiSmmu4KInvalidateAllOwnedContext(const EldenWifiSmmu4KIo *io,unsigned bank,
    const EldenWifiSmmu4KContextConfig *config,unsigned budget,EldenWifiSmmu4KProgramResult *r)
{return synchronize(io,bank,config,1,budget,r);}
