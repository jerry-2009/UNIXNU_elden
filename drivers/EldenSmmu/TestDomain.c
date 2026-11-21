/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "Domain.h"
#include "BootRoute.c" /* Test-only modeled platform reset of registry state. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks,cases;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"line%d %s\n",__LINE__,#x);abort();}}while(0)
typedef struct {
    uint32_t regs[0x100000/4];uint64_t *pool,clock;EldenWifiDmaTables tables;EldenSmmuSelection selection;
    unsigned writes,ats,fail_write,wrong_at,deny_at;uint32_t fail_read;int fault;
} Model;
static Model m;
enum {CB=0x87000,SMR=0x820,S2CR=0xc20};
static int admit(void *p){CHECK(p==&m);return m.deny_at&&m.ats>=m.deny_at?-11:0;}
static int rd32(void *p,size_t off,uint32_t *v){
    CHECK(p==&m&&off<sizeof(m.regs)&&!(off&3));m.clock++;
    if(off==m.fail_read)return -5;
    if(off==CB+0x7f4&&m.fault==1){*v=1;return 0;}
    if(off==CB+0x8f0&&m.fault==2){*v=1;return 0;}
    if(off==SMR&&m.fault==5&&m.ats==65536){*v=0x80001234;return 0;}
    if(off==0x101c&&m.fault==8&&m.regs[SMR/4]){*v=0;return 0;}
    *v=m.regs[off/4];return 0;
}
static int rd64(void *p,size_t off,uint64_t *v){
    CHECK(p==&m&&off<sizeof(m.regs)-4&&!(off&7));m.clock++;
    if(off==CB+0x50&&m.fault==3)m.clock+=1000;
    *v=(uint64_t)m.regs[off/4]|((uint64_t)m.regs[off/4+1]<<32);return 0;
}
static int wr32(void *p,size_t off,uint32_t v){
    CHECK(p==&m);m.clock++;m.writes++;
    CHECK(off==0x101c||off==0x181c||off==CB||off==CB+0x10||off==CB+0x30||off==CB+0x38||off==CB+0x3c||off==CB+0x58||off==CB+0x610||off==CB+0x618||off==CB+0x7f0||off==SMR||off==S2CR);
    if(m.fail_write==m.writes)return -5;
    if(m.fault==4&&off==CB+0x30)return 0;
    if(off==CB+0x58)m.regs[off/4]&=~v;else m.regs[off/4]=v;
    if(m.fault==6&&off==S2CR)return -5; /* applied error */
    if(m.fault==7&&off==SMR)return -5;
    return 0;
}
static uint64_t walk(uint64_t va,int write){
    const uint64_t mask=0x0000fffffffff000ULL,base=0x980000000ULL;
    uint64_t table=((uint64_t)m.regs[(CB+0x24)/4]<<32|m.regs[(CB+0x20)/4])&mask;
    for(unsigned level=1;level<=3;level++){
        if(table<base||table-base>=EldenWifiTablePages*4096)return 1;
        unsigned slot=(unsigned)(va>>(39-9*level))&511;
        uint64_t d=m.pool[(table-base)/8+slot];if((d&3)!=3)return 1;
        if(level==3){if(!(d&64)||(write&&(d&128)))return 1;return (d&mask)|(va&4095);}
        table=d&mask;
    }
    return 1;
}
static int wr64(void *p,size_t off,uint64_t v){
    CHECK(p==&m&&(off==CB+0x20||off==CB+0x28||off==CB+0x810||off==CB+0x818));m.clock++;m.writes++;
    if(m.fail_write==m.writes)return -5;
    if(off==CB+0x810||off==CB+0x818){
        m.ats++;uint64_t par=walk(v,off==CB+0x818);if(m.wrong_at==m.ats)par+=4096;
        m.regs[(CB+0x50)/4]=(uint32_t)par;m.regs[(CB+0x54)/4]=(uint32_t)(par>>32);
        if(m.fault==9&&m.ats==65536)m.pool[512+127]=3;
    }else{m.regs[off/4]=(uint32_t)v;m.regs[off/4+1]=(uint32_t)(v>>32);}
    return 0;
}
static int barrier(void *p){CHECK(p==&m);return 0;}
static uint64_t now(void *p){CHECK(p==&m);return m.clock;}
static void delay(void *p,unsigned us){CHECK(p==&m);m.clock+=us;}
static void reset(void){
    cases++;uint64_t *pool=m.pool;memset(&m,0,sizeof(m));m.pool=pool;m.fail_read=UINT32_MAX;
    state=EldenSmmuBootOpen;owner=NULL;intended=(EldenSmmuBootRoute){0};published=(EldenSmmuBootRoute){0};
    m.regs[0]=0x230406;m.regs[0x20/4]=0x4c017e84;m.regs[0x24/4]=0x60000053;m.regs[0x28/4]=0x5111;m.regs[S2CR/4]=0x0300006e;
    m.selection=(EldenSmmuSelection){.route={8,7,0x80001401,7,0x1f300,1},.id0=0x4c017e84,.id1=0x60000053,.id2=0x5111,.cr0=0x230406,.asid=1,.ready=1};
    /* Most fault cases exercise the architectural ATOS-capable variant. The
     * actual TB322FC ATOSNS case is separately asserted without any ATS write. */
    m.selection.id0&=~(1u<<26);m.regs[0x20/4]=m.selection.id0;
    CHECK(!elden_wifi_dma_tables_build(&m.tables,m.selection.id0,m.selection.id2,0x900200000ULL,0x980000000ULL,m.pool,EldenWifiDmaBytes));
}
static int run(EldenSmmuDomain *d){
    EldenSmmuDomainOps ops={&m,admit,now,delay,NULL,{&m,0x100000,rd32,rd64,wr32,wr64,barrier}};
    return elden_smmu_domain_start(d,&ops,&m.selection,&m.tables);
}
int main(void){
    m.pool=aligned_alloc(4096,EldenWifiTablePages*4096);CHECK(m.pool);
    reset();EldenSmmuDomain d={0};CHECK(!run(&d));CHECK(d.ready&&d.stage==7&&d.translations==65536&&d.route_writes==2);
    CHECK(d.translation_mode==1);
    CHECK(m.regs[SMR/4]==0x80001401&&m.regs[S2CR/4]==7&&elden_smmu_boot_route_state()==EldenSmmuBootReady);
    CHECK(run(&d)==-16);
    for(unsigned fault=1;fault<=9;fault++){
        reset();memset(&d,0,sizeof(d));m.fault=(int)fault;CHECK(run(&d)!=0&&!d.ready);
        CHECK(elden_smmu_boot_route_state()==EldenSmmuBootPoisoned);
    }
    for(unsigned failure=1;failure<=10;failure++){
        reset();memset(&d,0,sizeof(d));m.fail_write=failure;CHECK(run(&d)!=0&&!d.ready);
        CHECK(elden_smmu_boot_route_state()==EldenSmmuBootPoisoned);
    }
    reset();memset(&d,0,sizeof(d));m.fail_read=0x20;CHECK(run(&d)==-5&&!d.reserved&&!m.writes);
    reset();memset(&d,0,sizeof(d));m.wrong_at=8193;CHECK(run(&d)==-71&&!d.ready&&d.translations==8192);
    reset();memset(&d,0,sizeof(d));m.deny_at=2;CHECK(run(&d)==-11&&!d.ready&&d.translations==1);
    reset();memset(&d,0,sizeof(d));m.regs[S2CR/4]=0;CHECK(run(&d)==-71&&!d.reserved&&!m.writes);
    reset();memset(&d,0,sizeof(d));m.selection.id0|=1u<<26;m.tables.id0=m.selection.id0;m.regs[0x20/4]=m.selection.id0;
    CHECK(!run(&d)&&d.ready&&d.translation_mode==2&&!d.translations&&!m.ats&&d.software_pages==32768);
    free(m.pool);printf("%u domain scenarios / %u checks; actual programmer/walker/ATOS model, no physical MMIO\n",cases,checks);return 0;
}
