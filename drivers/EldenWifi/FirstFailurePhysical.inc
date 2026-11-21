/* SPDX-License-Identifier: GPL-2.0-only */
/* Read only mappings owned by the current PCIe worker. The table is derived
 * from TB322FC6f97250e/Root.c and the existing MSI/endpoint setup. */
extern "C" int elden_wifi_first_failure_physical(unsigned stage){
    Context *c=runtime_context;
    if((stage!=12&&stage!=90)||!c||c!=__atomic_load_n(&active,__ATOMIC_ACQUIRE)||
       !c->runtime_entered||c->runtime_returned||c->transport_cleanup||
       __atomic_load_n(&stop_requested,__ATOMIC_ACQUIRE)||ml_at_interrupt_context())return -19;
    int rc=transport_admit(c,false);if(rc)return rc;
    const uint64_t epoch=c->wlan_epoch;
    if(!epoch||epoch!=c->root.epoch||!c->config.ready||c->config.pcie_cap<0x40||
       c->config.pcie_cap>0xc4||!c->endpoint_confirmed||!c->bar0_map.va)return -19;
    static unsigned seen;
    unsigned bit=stage==12?1u:2u;
    if(__atomic_fetch_or(&seen,bit,__ATOMIC_ACQ_REL)&bit)return -114;
    struct Row{unsigned map;uint32_t offset;};
    /* map7 refers to the already mapped GPIO102/103 window. A dynamic PCIE
     * capability offset is resolved only from the captured owned config. */
    static const Row rows[]={
      {EldenPcieConfig,0},{EldenPcieConfig,4},{EldenPcieConfig,0x10},
      {EldenPcieConfig,0x14},{EldenPcieConfig,0x18},{EldenPcieConfig,0x1c},
      {EldenPcieConfig,0xffff0008u},{EldenPcieConfig,0xffff0010u},
      {EldenPcieDbi,0x728},{EldenPcieDbi,0x72c},
      {EldenPcieDbi,0x828},{EldenPcieDbi,0x82c},{EldenPcieDbi,0x830},
      {EldenPcieAtu,0x200},{EldenPcieAtu,0x204},{EldenPcieAtu,0x208},
      {EldenPcieAtu,0x20c},{EldenPcieAtu,0x210},{EldenPcieAtu,0x214},{EldenPcieAtu,0x218},
      {EldenPcieGcc,0x6b000},{EldenPcieGcc,0x6c01c},
      {EldenPcieGcc,0x6b004},{EldenPcieGcc,0x6b008},
      {EldenPcieGcc,0x6c000},{EldenPcieGcc,0x6c004},
      {EldenPcieGcc,0x52000},{EldenPcieGcc,0x52008},{EldenPcieGcc,0x5214c},
      {EldenPcieGcc,0x6b068},{EldenPcieGcc,0x6b06c},{EldenPcieGcc,0x6b080},
      {EldenPcieGcc,0x6b084},{EldenPcieGcc,0x6b088},
      {EldenPcieGcc,0x6b020},{EldenPcieGcc,0x6b040},{EldenPcieGcc,0x6b044},
      {EldenPcieGcc,0x6b01c},{EldenPcieGcc,0x10058},{EldenPcieGcc,0x6b018},
      {EldenPcieGcc,0x10050},{EldenPcieGcc,0x6b064},{EldenPcieTcsr,8},
      {7,0},{7,4},{7,0x1000},{7,0x1004}
    };
    int first=0;unsigned good=0;
    const uint64_t before=now(nullptr);
    for(unsigned i=0;i<sizeof(rows)/sizeof(rows[0]);i++){
        uint32_t off=rows[i].offset,value=UINT32_MAX;
        if((off&0xffff0000u)==0xffff0000u)off=c->config.pcie_cap+(off&0xffffu);
        int error=rows[i].map==7?c->pin_map.read(off,&value):c->maps[rows[i].map].read(off,&value);
        if(!error&&value==UINT32_MAX)error=-5;
        if(error&&!first)first=error;if(!error)good++;
        log("\nELDEN_FIRST_PHYS stage=%u map=%u off=%x rc=%d value=%x\n",
            stage,rows[i].map,off,error,value);
    }
    rc=transport_admit(c,false);
    if((epoch!=c->wlan_epoch||epoch!=c->root.epoch)&&!rc)rc=-11;
    if(rc&&!first)first=rc;
    log("\nELDEN_FIRST_PHYS_END stage=%u rc=%d reads=%u good=%u epoch=%llu us=%llu irq=%u pending=%x; sampled-values-not-atomic\n",
        stage,first,(unsigned)(sizeof(rows)/sizeof(rows[0])),good,
        (unsigned long long)epoch,(unsigned long long)(now(nullptr)-before),
        __atomic_load_n(&c->msi.irq_count,__ATOMIC_RELAXED),
        __atomic_load_n(&c->msi.pending,__ATOMIC_RELAXED));
    return first;
}
