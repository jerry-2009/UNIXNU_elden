/* SPDX-License-Identifier: GPL-2.0-only */
static int endpoint_map(void *p,uint64_t address,uint32_t bytes){
    Context *c=static_cast<Context *>(p);const EldenPcieEndpoint &e=c->endpoint;
    if(!c->endpoint_requested||e.stage!=EldenEndpointMap||e.epoch!=c->wlan_epoch||
       !e.bars[0].present||address!=e.bars[0].address||bytes!=e.bars[0].bytes||
       address<0x40300000||address>=0x44000000||!bytes||bytes>0x44000000-address||
       (address&0xfff)||(bytes&0xfff))return -22;
    int rc=admit(c,e.epoch);if(rc)return rc;
    trace(c,EldenPcieWindowCount,0);
    if(!c->bar0_map.map(address,bytes))return -12;
    log("\nELDEN_PCIE_EP mapped pa=%llx bytes=%x cache=inhibit\n",(unsigned long long)address,bytes);
    return admit(c,e.epoch);
}
static int endpoint_read(void *p,uint32_t off,uint32_t *value){
    Context *c=static_cast<Context *>(p);int rc=admit(c,c->endpoint.epoch);if(rc)return rc;
    trace(c,EldenPcieWindowCount,off);
    return c->bar0_map.read(off,value);
}
static int endpoint_write(void *p,uint32_t off,uint32_t value){
    Context *c=static_cast<Context *>(p);
    /* This identity-only native adapter may write just Peach's remap control. */
    if(off!=0x3278)return -22;
    int rc=admit(c,c->endpoint.epoch);if(rc)return rc;
    trace(c,EldenPcieWindowCount,off);
    return c->bar0_map.write(off,value);
}
static void endpoint_run(Context *c){
    c->endpoint.root=&c->root;c->endpoint.io={c,endpoint_map,endpoint_read,endpoint_write};
    int rc=elden_pcie_endpoint_identify(&c->endpoint);
    if(!rc)rc=admit(c,c->endpoint.epoch);
    if(!rc)rc=elden_wlan_power_confirm_endpoint(c,c->endpoint.epoch,c->root.endpoint_id,(c->endpoint.chip_version>>8)&15);
    if(!rc)rc=elden_wlan_power_ready(c,c->endpoint.epoch);
    if(!rc)rc=admit(c,c->endpoint.epoch);
    c->endpoint_result=rc;c->endpoint_confirmed=!rc;
}
static void endpoint_capture(Context *c){
    endpoint_terminal.version=1;
    if(!c||!c->endpoint_requested)return;
    const EldenPcieEndpoint &e=c->endpoint;auto &s=endpoint_terminal;
    s.requested=1;s.state=e.state;s.stage=e.stage;s.error=c->endpoint_result;
    s.chip_version=e.chip_version;s.major=(e.chip_version>>8)&15;s.minor=(e.chip_version>>4)&15;
    s.command=e.command;s.writes=e.writes;s.mapped=e.mapped;s.remap_restored=e.remap_restored;
    s.confirmed=c->endpoint_confirmed;s.last_window=e.last_window;s.last_offset=e.last_offset;s.last_value=e.last_value;
    s.epoch=e.epoch;s.bar0=e.bars[0].address;s.bar0_bytes=e.bars[0].bytes;s.bar2=e.bars[2].address;s.bar2_bytes=e.bars[2].bytes;
    log("\nELDEN_PCIE_EP end rc=%d state=%u stage=%u chip=%08x major=%u minor=%u command=%04x mapped=%u remap-restored=%u confirmed=%u writes=%u last=%u:%08x=%08x\n",
        s.error,s.state,s.stage,s.chip_version,s.major,s.minor,s.command,s.mapped,s.remap_restored,s.confirmed,s.writes,s.last_window,s.last_offset,s.last_value);
    log("\nELDEN_PCIE_EP bars bar0=%llx/%llx bar2=%llx/%llx epoch=%llu dma=0\n",
        (unsigned long long)s.bar0,(unsigned long long)s.bar0_bytes,(unsigned long long)s.bar2,(unsigned long long)s.bar2_bytes,(unsigned long long)s.epoch);
}
