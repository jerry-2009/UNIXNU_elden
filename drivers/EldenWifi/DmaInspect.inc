/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Included in the exact native wireless worker. No memory/table writes. */
static uint64_t elden_dma_inspect_par(uintptr_t address,bool write){
    uint64_t daif,saved,result;
    if(write)__asm__ volatile("mrs %0,daif\n\tmsr daifset,#2\n\tmrs %1,par_el1\n\tat s1e1w,%3\n\tisb\n\tmrs %2,par_el1\n\tmsr par_el1,%1\n\tmsr daif,%0"
        :"=&r"(daif),"=&r"(saved),"=&r"(result):"r"(address):"memory");
    else __asm__ volatile("mrs %0,daif\n\tmsr daifset,#2\n\tmrs %1,par_el1\n\tat s1e1r,%3\n\tisb\n\tmrs %2,par_el1\n\tmsr par_el1,%1\n\tmsr daif,%0"
        :"=&r"(daif),"=&r"(saved),"=&r"(result):"r"(address):"memory");
    return result;
}
extern "C" int elden_wifi_dma_inspect(const void *cpu,uint64_t bus,uint32_t bytes,EldenWifiDmaInspect *out){
    if(!out)return -22;*out={};
    Context *c=runtime_context;
    if(!cpu||!bytes||bytes>4096||bus<0x10000000ULL||bus-0x10000000ULL>=128ULL*1024*1024||
       bytes>128ULL*1024*1024-(bus-0x10000000ULL)||!c||
       !c->runtime_prepared||!c->runtime_entered||c->runtime_returned||c->transport_cleanup||
       __atomic_load_n(&stop_requested,__ATOMIC_ACQUIRE)||ml_at_interrupt_context()||
       current_thread()!=c->runtime_thread)return -22;
    int rc=transport_admit(c,false);if(rc)return rc;
    EldenWifiSmmuStatus smmu={};rc=elden_wifi_smmu_status(&smmu);if(rc)return rc;
    out->smmu_ready=smmu.ready;out->smmu_fault=smmu.fault_claimed;
    EldenWifiDmaStatus dma={};rc=elden_wifi_dma_status(&dma);if(rc)return rc;
    out->dma_error=(uint32_t)dma.first_error;out->live=dma.live;
    if(!smmu.ready||smmu.fault_claimed||dma.run!=2||dma.stopping||dma.first_error||dma.epoch!=c->wlan_epoch)return -19;
    uint64_t mapped=elden_wifi_dma_map(const_cast<void *>(cpu),bytes,1);
    out->mapped_bus=mapped;if(mapped!=bus)return -71;
    uintptr_t address=(uintptr_t)cpu;
    out->par_read=elden_dma_inspect_par(address,false);out->par_write=elden_dma_inspect_par(address,true);
    if((out->par_read|out->par_write)&1)return -14;
    out->physical=(out->par_read&0x0000fffffffff000ULL)|(address&4095);
    out->expected_physical=smmu.data_physical+(bus-0x10000000ULL);
    if(out->physical!=out->expected_physical||
       (out->par_write&0x0000fffffffff000ULL)!=(out->par_read&0x0000fffffffff000ULL)||
       (out->par_read>>56)!=0x44||(out->par_write>>56)!=0x44)return -71;
    return transport_admit(c,false);
}
