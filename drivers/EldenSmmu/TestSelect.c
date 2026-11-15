/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "Select.h"
#include "EldenTouchBoard.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks,cases;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"line%d %s\n",__LINE__,#x);abort();}}while(0)
typedef struct {uint32_t r[0x100000/4];unsigned calls,fail_at;} Model;
static Model m;
static int step(void){return ++m.calls==m.fail_at?-5:0;}
static int admit(void *p){CHECK(p==&m);return step();}
static int read32(void *p,uint32_t off,uint32_t *v){CHECK(p==&m&&!(off&3)&&off<sizeof(m.r));int rc=step();if(rc)return rc;*v=m.r[off/4];return 0;}
static EldenSmmuSelectIo io={&m,admit,read32};
static void reset(void){
    cases++;memset(&m,0,sizeof(m));m.r[0]=ELDEN_TOUCH_DMA_CR0;m.r[0x20/4]=ELDEN_TOUCH_DMA_ID0;
    m.r[0x24/4]=ELDEN_TOUCH_DMA_ID1;m.r[0x28/4]=ELDEN_TOUCH_DMA_ID2;m.r[0x80000/4]=0xe0;
    const uint32_t active[]=ELDEN_TOUCH_DMA_ACTIVE_SMR;
    for(unsigned i=0;i<132;i++){m.r[(0x800+4*i)/4]=i<7?active[i]:0;m.r[(0xc00+4*i)/4]=i<7?i:ELDEN_TOUCH_DMA_UNUSED_S2CR;}
    for(unsigned i=0;i<83;i++){m.r[(0x1000+4*i)/4]=i<7?0x1f000:0;m.r[(0x1800+4*i)/4]=i<7?1:0;}
}
int main(void){
    EldenSmmuSelection s;reset();CHECK(!elden_smmu_select_boot_domain(&io,&s));
    CHECK(s.ready&&s.route.slot==8&&s.route.bank==7&&s.asid==1&&s.cb0_sctlr==0xe0);
    unsigned calls=m.calls;uint32_t original[0x100000/4];memcpy(original,m.r,sizeof(original));
    CHECK(!elden_smmu_select_boot_domain(&io,&s)&&!memcmp(original,m.r,sizeof(original)));
    for(unsigned i=1;i<=calls;i++){reset();m.fail_at=i;CHECK(elden_smmu_select_boot_domain(&io,&s)==-5&&!s.ready);}
    reset();m.r[(0x81000)/4]=1;m.r[(0x81000+0x24)/4]=1u<<16;m.r[(0x81000+0x2c)/4]=2u<<16;
    CHECK(!elden_smmu_select_boot_domain(&io,&s)&&s.asid==3);
    reset();m.r[(0x87000+0x58)/4]=2;CHECK(!elden_smmu_select_boot_domain(&io,&s)&&s.route.bank==8);
    for(unsigned i=0;i<8;i++){
        reset();
        if(i==0)m.r[0x20/4]^=1;
        if(i==1)m.r[0x48/4]=1;
        if(i==2)m.r[(0x800+131*4)/4]=0x80001401;
        if(i==3)m.r[(0x1000+80*4)/4]=0x1f300;
        if(i==4)m.r[0x80000/4]|=1;
        if(i==5)m.r[0x87000/4]=1;
        if(i==6)m.r[0x87000/4]=UINT32_MAX;
        if(i==7)for(unsigned b=7;b<83;b++)m.r[(0x80000+4096*b+0x58)/4]=2;
        CHECK(elden_smmu_select_boot_domain(&io,&s)!=0&&!s.ready);
    }
    printf("%u selection scenarios / %u checks; all MMIO/admission failures modeled; no writes\n",cases,checks);return 0;
}
