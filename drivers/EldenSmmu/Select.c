/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "Select.h"
#include "EldenTouchBoard.h"
#include <stddef.h>
static int rd(const EldenSmmuSelectIo *io,EldenSmmuSelection *s,uint32_t off,uint32_t *v){
    if((off&3)||off>=0x100000)return -22;
    int rc=io->admit(io->context);if(rc)return rc;
    s->last_offset=off;*v=UINT32_MAX;s->reads++;
    rc=io->read32(io->context,off,v);s->last_value=*v;
    if(rc)return rc;
    if(*v==UINT32_MAX)return -5;
    return io->admit(io->context);
}
static int fail(EldenSmmuSelection *s,int error){s->error=error;s->ready=0;return error;}
int elden_smmu_select_boot_domain(const EldenSmmuSelectIo *io,EldenSmmuSelection *s){
    if(!io||!io->admit||!io->read32||!s)return -22;
    *s=(EldenSmmuSelection){0};int rc;uint32_t value=0;
    s->stage=1;
    if((rc=rd(io,s,0,&s->cr0))||(rc=rd(io,s,0x20,&s->id0))||
       (rc=rd(io,s,0x24,&s->id1))||(rc=rd(io,s,0x28,&s->id2)))return fail(s,rc);
    if(s->cr0!=ELDEN_TOUCH_DMA_CR0||s->id0!=ELDEN_TOUCH_DMA_ID0||s->id1!=ELDEN_TOUCH_DMA_ID1||s->id2!=ELDEN_TOUCH_DMA_ID2)return fail(s,-95);
    if((rc=rd(io,s,0x48,&value)))return fail(s,rc);
    if(value)return fail(s,-5);
    s->stage=2;const uint32_t boot[]=ELDEN_TOUCH_DMA_ACTIVE_SMR;
    for(unsigned i=0;i<ELDEN_TOUCH_DMA_SLOTS;i++){
        uint32_t smr=0,s2cr=0;
        if((rc=rd(io,s,0x800+4*i,&smr))||(rc=rd(io,s,0xc00+4*i,&s2cr)))return fail(s,rc);
        if(smr!=(i<7?boot[i]:0)||s2cr!=(i<7?i:ELDEN_TOUCH_DMA_UNUSED_S2CR))return fail(s,-16);
    }
    s->stage=3;uint32_t cbar[ELDEN_TOUCH_DMA_BANKS],cba2r[ELDEN_TOUCH_DMA_BANKS];
    for(unsigned i=0;i<ELDEN_TOUCH_DMA_BANKS;i++){
        if((rc=rd(io,s,0x1000+4*i,&cbar[i]))||(rc=rd(io,s,0x1800+4*i,&cba2r[i])))return fail(s,rc);
        if(cbar[i]!=(i<7?0x1f000u:0)||cba2r[i]!=(i<7?1u:0))return fail(s,-16);
    }
    s->stage=4;unsigned bank=ELDEN_TOUCH_DMA_BANKS;unsigned char used[256]={0};
    for(unsigned i=0;i<ELDEN_TOUCH_DMA_BANKS;i++){
        uint32_t cb=ELDEN_TOUCH_DMA_CB0_OFFSET+4096*i,sctlr=0,fsr=0;
        if((rc=rd(io,s,cb,&sctlr))||(rc=rd(io,s,cb+0x58,&fsr)))return fail(s,rc);
        if(!i)s->cb0_sctlr=sctlr;
        if(!i&&(sctlr&1))return fail(s,-95); /* Never repurpose storage's bypass. */
        if(sctlr&1){
            if((cbar[i]>>16&3)!=1||cba2r[i]!=1)return fail(s,-95);
            if(fsr&0xc00001feu)return fail(s,-5);
            uint32_t high0=0,high1=0;
            if((rc=rd(io,s,cb+0x24,&high0))||(rc=rd(io,s,cb+0x2c,&high1)))return fail(s,rc);
            unsigned a=high0>>16,b=high1>>16;if(a<256)used[a]=1;if(b<256)used[b]=1;
        }else if(i>=7&&bank==ELDEN_TOUCH_DMA_BANKS&&!(fsr&0xc00001feu)){
            bank=i;s->selected_sctlr=sctlr;s->selected_fsr=fsr;
        }
    }
    if(bank==ELDEN_TOUCH_DMA_BANKS)return fail(s,-28);
    s->stage=5;
    for(unsigned asid=1;asid<256;asid++)if(!used[asid]){s->asid=asid;break;}
    if(!s->asid)return fail(s,-28);
    if((rc=io->admit(io->context)))return fail(s,rc);
    s->route=(EldenSmmuBootRoute){8,bank,0x80001401u,bank,0x1f300u,1};
    s->stage=6;s->ready=1;return 0;
}
