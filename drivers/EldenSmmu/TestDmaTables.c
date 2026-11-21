/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "DmaTables.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks,cases;
#define CHECK(x) do {checks++;if(!(x)){fprintf(stderr,"line%d %s\n",__LINE__,#x);abort();}} while(0)
int main(void){
    uint64_t *pool=aligned_alloc(4096,EldenWifiTablePages*4096);CHECK(pool);
    for(unsigned size=2;size<=128;size*=2){
        EldenWifiDmaTables t={0};cases++;
        CHECK(!elden_wifi_dma_tables_build(&t,0x4c017e84,0x5111,0x900200000ULL,0x980000000ULL,pool,size<<20));
        CHECK(t.ready&&t.config.output_bits==36&&t.result.table_pages==2+size/2&&t.result.leaf_pages==(size<<8));
        EldenWifiSmmu4KContextImage image={0};CHECK(!elden_wifi_dma_context_image(&t,7,&image));
        CHECK(image.tcr==0x80802020&&image.cbar==0x1f300&&image.tcr2==0x38011);
        EldenWifiSmmu4KTableAuditResult audit={0};CHECK(!elden_wifi_dma_tables_audit(&t,&audit)&&audit.complete);
        uint64_t saved=pool[512+128];pool[512+128]=3;
        CHECK(elden_wifi_dma_tables_audit(&t,&audit)!=0);pool[512+128]=saved;
        CHECK(!elden_wifi_dma_tables_audit(&t,&audit));
        CHECK(elden_wifi_dma_tables_build(&t,0x4c017e84,0x5111,0x900200000ULL,0x980000000ULL,pool,size<<20)==-22);
    }
    for(unsigned fault=0;fault<7;fault++){
        cases++;EldenWifiDmaTables t={0};uint32_t id0=0x4c017e84,id2=0x5111;uint64_t pa=0x900200000ULL,tpa=0x980000000ULL;size_t n=EldenWifiDmaBytes;
        if(fault==0)id0=0;
        if(fault==1)id2=0x511f;
        if(fault==2)id2=0x5000;
        if(fault==3)pa=1ULL<<36;
        if(fault==4)tpa=pa;
        if(fault==5)n++;
        if(fault==6)pa++;
        CHECK(elden_wifi_dma_tables_build(&t,id0,id2,pa,tpa,pool,n)!=0&&!t.ready);
    }
    free(pool);printf("%u table scenarios / %u checks passed; full128MiB build and physical-graph walk included\n",cases,checks);return 0;
}
