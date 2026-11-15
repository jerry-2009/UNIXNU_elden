/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "DmaTables.h"
static unsigned width(unsigned code){
    static const unsigned widths[]={32,36,40,42,44,48};return code<6?widths[code]:0;
}
static int error(EldenWifiSmmu4KStatus s){return s?-(100+(int)s):0;}
unsigned elden_wifi_dma_output_bits(uint32_t id0,uint32_t id2){
    unsigned input=width((id2>>8)&15),output=width((id2>>4)&15),intermediate=width(id2&15);
    if(!(id0&(1u<<30))||!(id2&(1u<<12))||input<32||!output||!intermediate)return 0;
    return intermediate<output?intermediate:output;
}
int elden_wifi_dma_tables_audit(EldenWifiDmaTables *t,EldenWifiSmmu4KTableAuditResult *out){
    if(!t||!out||!t->attempted||!t->result.table_pages)return -22;
    EldenWifiSmmu4KAuditRegion region={&t->range,1,EldenWifiTablePages,EldenWifiTablePages*512,t->visited,sizeof(t->visited)};
    return error(EldenWifiSmmu4KAuditTables(&t->io,&t->config,&t->result,&region,t->result.root_physical,out));
}
int elden_wifi_dma_tables_build(EldenWifiDmaTables *t,uint32_t id0,uint32_t id2,
    uint64_t data_pa,uint64_t table_pa,uint64_t *mapping,size_t bytes){
    if(!t||t->attempted||!mapping||((uintptr_t)mapping&4095)||!data_pa||!table_pa||
       (data_pa&0x1fffff)||(table_pa&4095)||!bytes||bytes>EldenWifiDmaBytes||(bytes&0x1fffff))return -22;
    t->attempted=1;t->id0=id0;t->id2=id2;
    unsigned output=elden_wifi_dma_output_bits(id0,id2);if(!output)return -95;
    t->config=(EldenWifiSmmu4KConfig){32,output,table_pa,bytes/4096};
    t->range=(EldenWifiSmmu4KRange){EldenWifiDmaIova,data_pa,bytes,EldenWifiSmmu4KRead|EldenWifiSmmu4KWrite,0,3};
    int rc=error(EldenWifiSmmu4KBuild(&t->config,&t->range,1,mapping,EldenWifiTablePages,&t->result));if(rc)return rc;
    if(t->result.table_pages!=2+bytes/(2u<<20)||t->result.leaf_pages!=bytes/4096)return -71;
    t->memory.count=1;t->memory.pools[0]=(EldenWifiSmmu4KTableMapping){mapping,table_pa,EldenWifiTablePages};
    rc=error(EldenWifiSmmu4KBindTableMemory(&t->memory,&t->io));if(rc)return rc;
    EldenWifiSmmu4KTableAuditResult audit={0};rc=elden_wifi_dma_tables_audit(t,&audit);
    if(!rc&&audit.complete)t->ready=1;
    return rc?rc:t->ready?0:-71;
}
int elden_wifi_dma_context_image(EldenWifiDmaTables *t,unsigned asid,EldenWifiSmmu4KContextImage *out){
    if(!t||!t->ready||!out||!asid||asid>255)return -22;
    EldenWifiSmmu4KTableAuditResult audit={0};int rc=elden_wifi_dma_tables_audit(t,&audit);if(rc)return rc;
    EldenWifiSmmu4KContextConfig config={&t->config,0,&t->result,0,t->id0,t->id2,asid,0,0,0,0};
    return error(EldenWifiSmmu4KEncodeContext(&config,out));
}
