/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "Domain.h"
static int failed(EldenSmmuDomain *d,const EldenSmmuDomainOps *ops,int error){
    d->error=error;d->ready=0;
    if(d->reserved)(void)elden_smmu_boot_route_poison(ops->context);
    return error;
}
static void stage(EldenSmmuDomain *d,const EldenSmmuDomainOps *o,unsigned n){d->stage=n;if(o->progress)o->progress(o->context,n,d->translations);}
static int admit(const EldenSmmuDomainOps *o){return o->admit(o->context);}
static int expected32(const EldenSmmuDomainOps *o,size_t at,uint32_t want){
    uint32_t value=UINT32_MAX;int rc=admit(o);if(rc)return rc;
    rc=o->io.read32(o->io.cookie,at,&value);return rc?rc:value!=want?-71:0;
}
static int put32(EldenSmmuDomain *d,const EldenSmmuDomainOps *o,size_t at,uint32_t value){
    int rc=admit(o);if(rc)return rc;d->route_writes++;
    rc=o->io.write32(o->io.cookie,at,value);if(rc)return rc;
    rc=o->io.barrier(o->io.cookie);return rc?rc:expected32(o,at,value);
}
static int translate_all(EldenSmmuDomain *d,const EldenSmmuDomainOps *o,const EldenWifiDmaTables *t){
    size_t cb=0x80000+4096*d->selection.route.bank;
    for(uint64_t off=0;off<t->range.bytes;off+=4096)for(unsigned write=0;write<2;write++){
        d->last_iova=t->range.iova+off;
        int rc=admit(o);if(rc)return rc;
        uint64_t began=o->now_us(o->context);
        /* ATS1UR/UW: verify the unprivileged RW permissions used by PCIe. */
        if((rc=o->io.write64(o->io.cookie,cb+(write?0x818:0x810),d->last_iova))||
           (rc=o->io.barrier(o->io.cookie)))return rc;
        unsigned complete=0;
        for(unsigned n=0;n<1000;n++){
            uint64_t now=o->now_us(o->context);if(now<began||now-began>=1000)return -110;
            uint32_t busy=UINT32_MAX;
            if((rc=admit(o))||(rc=o->io.read32(o->io.cookie,cb+0x8f0,&busy)))return rc;
            if(busy==UINT32_MAX)return -5;
            if(!(busy&1)){complete=1;break;}
            o->delay_us(o->context,1);
        }
        if(!complete)return -110;
        if((rc=o->io.read64(o->io.cookie,cb+0x50,&d->last_par)))return rc;
        uint64_t ended=o->now_us(o->context);if(ended<began||ended-began>=1000)return -110;
        if((d->last_par&1)||(d->last_par&0x0000fffffffff000ULL)!=t->range.physical+off)return -71;
        if((rc=admit(o)))return rc;
        d->translations++;if(o->progress&&!(d->translations%8192))o->progress(o->context,d->stage,d->translations);
    }
    return 0;
}
int elden_smmu_domain_start(EldenSmmuDomain *d,const EldenSmmuDomainOps *o,
    const EldenSmmuSelection *s,const EldenWifiDmaTables *t){
    if(!d||!o||!s||!t||!o->context||!o->admit||!o->now_us||!o->delay_us||
       !o->io.read32||!o->io.read64||!o->io.write32||!o->io.write64||!o->io.barrier||
       !s->ready||!t->ready||t->id0!=s->id0||t->id2!=s->id2||t->range.iova!=EldenWifiDmaIova||t->range.bytes!=EldenWifiDmaBytes||
       !s->asid||s->asid>255||s->route.slot!=8||s->route.bank<7||s->route.bank>=83)return -22;
    if(d->attempted)return -16;
    d->attempted=1;d->selection=*s;stage(d,o,1);int rc=admit(o);if(rc)return failed(d,o,rc);
    if((rc=expected32(o,0,s->cr0))||(rc=expected32(o,0x20,s->id0))||
       (rc=expected32(o,0x24,s->id1))||(rc=expected32(o,0x28,s->id2))||
       (rc=expected32(o,0x48,0))||(rc=expected32(o,0x800+4*s->route.slot,0))||
       (rc=expected32(o,0xc00+4*s->route.slot,0x0300006e)))return failed(d,o,rc);
    d->config=(EldenWifiSmmu4KContextConfig){&t->config,0,&t->result,0,s->id0,s->id2,s->asid,0,0,0,0};
    EldenWifiSmmu4KAuditRegion region={&t->range,1,EldenWifiTablePages,EldenWifiTablePages*512,d->visited,sizeof(d->visited)};
    EldenWifiSmmu4KAuditConfig audit={t->io,&region,0};
    EldenWifiSmmu4KStatus status=EldenWifiSmmu4KAuditDeclaredContext(&d->config,&audit,&d->audit);
    if(status)return failed(d,o,-100-(int)status);
    rc=elden_smmu_boot_route_reserve(o->context,&s->route);if(rc)return failed(d,o,rc);d->reserved=1;
    stage(d,o,2);
    status=EldenWifiSmmu4KProgramDisabledContext(&o->io,s->route.bank,&d->config,1000,&d->program);
    if(status)return failed(d,o,-100-(int)status);
    stage(d,o,3);status=EldenWifiSmmu4KObserveAuditedContext(&o->io,s->route.bank,&d->config,&audit,&d->audit);
    if(status)return failed(d,o,-100-(int)status);
    stage(d,o,4);
    if(s->id0&(1u<<26)){
        /* ARM_SMMU_ID0_ATOSNS means NOT supported. Linux uses the page-table
         * walk in this case. The complete graph was independently audited;
         * no hardware-translation or DMA success is invented. */
        d->translation_mode=2;
    }else{
        d->translation_mode=1;if((rc=translate_all(d,o,t)))return failed(d,o,rc);
    }
    stage(d,o,5);status=EldenWifiSmmu4KObserveAuditedContext(&o->io,s->route.bank,&d->config,&audit,&d->audit);
    if(status)return failed(d,o,-100-(int)status);
    if(!d->audit.complete||d->audit.lower.leaf_pages!=t->range.bytes/4096)return failed(d,o,-71);
    d->software_pages=(uint32_t)d->audit.lower.leaf_pages;
    if((rc=expected32(o,0x48,0))||(rc=expected32(o,0x800+4*s->route.slot,0))||
       (rc=expected32(o,0xc00+4*s->route.slot,0x0300006e)))return failed(d,o,rc);
    stage(d,o,6);
    if((rc=put32(d,o,0xc00+4*s->route.slot,s->route.s2cr))||
       (rc=put32(d,o,0x800+4*s->route.slot,s->route.smr)))return failed(d,o,rc);
    EldenSmmuBootRoute observed=s->route;
    if((rc=o->io.read32(o->io.cookie,0x800+4*s->route.slot,&observed.smr))||
       (rc=o->io.read32(o->io.cookie,0xc00+4*s->route.slot,&observed.s2cr))||
       (rc=o->io.read32(o->io.cookie,0x1000+4*s->route.bank,&observed.cbar))||
       (rc=o->io.read32(o->io.cookie,0x1800+4*s->route.bank,&observed.cba2r))||(rc=admit(o)))return failed(d,o,rc);
    rc=elden_smmu_boot_route_commit(o->context,&observed);if(rc)return failed(d,o,rc);
    d->ready=1;stage(d,o,7);return 0;
}
