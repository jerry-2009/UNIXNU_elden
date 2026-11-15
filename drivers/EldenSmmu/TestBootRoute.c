/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Simulated boot resets are local to this test translation unit. */
#include "BootRoute.c"
#include "DmaRoute.h"
#include "EldenTouchBoard.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks,cases;
#define CHECK(x) do { checks++;if(!(x)){fprintf(stderr,"line%d %s\n",__LINE__,#x);abort();} } while(0)
int old_elden_touch_route_attach(EldenTouchDmaRouteOwner *,const EldenTouchRouteIo *,uint64_t,uint64_t,uint64_t,size_t);
typedef struct {uint32_t regs[0x2000/4];uint32_t cb0;unsigned writes;int held;} Model;
static Model m;
static EldenSmmuBootRoute route={8,7,0x80001401,7,0x1f300,1};
static void reset(void){
    cases++;state=EldenSmmuBootOpen;owner=NULL;intended=(EldenSmmuBootRoute){0};published=(EldenSmmuBootRoute){0};
    memset(&m,0,sizeof(m));m.cb0=0xe0;
    m.regs[0]=ELDEN_TOUCH_DMA_CR0;m.regs[0x20/4]=ELDEN_TOUCH_DMA_ID0;
    m.regs[0x24/4]=ELDEN_TOUCH_DMA_ID1;m.regs[0x28/4]=ELDEN_TOUCH_DMA_ID2;
    const uint32_t active[]=ELDEN_TOUCH_DMA_ACTIVE_SMR;
    for(unsigned i=0;i<132;i++){m.regs[(0x800+4*i)/4]=i<7?active[i]:0;m.regs[(0xc00+4*i)/4]=i<7?i:ELDEN_TOUCH_DMA_UNUSED_S2CR;}
    for(unsigned i=0;i<83;i++){m.regs[(0x1000+4*i)/4]=i<7?0x1f000:0;m.regs[(0x1800+4*i)/4]=i<7?1:0;}
}
static void install_model(void){
    m.regs[(0x800+4*route.slot)/4]=route.smr;m.regs[(0xc00+4*route.slot)/4]=route.s2cr;
    m.regs[(0x1000+4*route.bank)/4]=route.cbar;m.regs[(0x1800+4*route.bank)/4]=route.cba2r;
}
static uint32_t rd(void *p,unsigned off){
    CHECK(p==&m&&m.held);
    if(off==0x80000)return m.cb0;
    CHECK(!(off&3)&&off<0x2000);return m.regs[off/4];
}
static int wr(void *p,unsigned off,uint32_t v){
    CHECK(p==&m&&m.held&&(off==0x81c||off==0xc1c));
    CHECK(off!=0xc1c||v==0);m.regs[off/4]=v;m.writes++;return 0;
}
static int claim(void *p,uint64_t e){CHECK(p==&m&&e==37&&!m.held);m.held=1;return 0;}
static void drop(void *p,uint64_t e){CHECK(p==&m&&e==37&&m.held);m.held=0;}
static int idle(void *p){CHECK(p==&m&&m.held);return 0;}
static const EldenTouchRouteIo io={&m,rd,wr,claim,drop,idle};
static int attach(EldenTouchDmaRouteOwner *p){return elden_touch_route_attach(p,&io,37,0x180000000ULL,0x180004000ULL,16384);}
static void publish(void){CHECK(!elden_smmu_boot_route_reserve(&m,&route));CHECK(!elden_smmu_boot_route_commit(&m,&route));}
static int go,reserve_rc,seal_rc;
static void *race_reserve(void *p){while(!__atomic_load_n(&go,__ATOMIC_ACQUIRE)){}reserve_rc=elden_smmu_boot_route_reserve(p,&route);return NULL;}
static void *race_seal(void *p){(void)p;while(!__atomic_load_n(&go,__ATOMIC_ACQUIRE)){}seal_rc=elden_smmu_boot_route_seal();return NULL;}
int main(void){
    reset();install_model();EldenTouchDmaRouteOwner old={0};
    CHECK(old_elden_touch_route_attach(&old,&io,37,0x180000000ULL,0x180004000ULL,16384)==-16);
    CHECK(!old.attached&&!m.writes&&!m.held); /* actual original rejects new Wi-Fi */
    reset();EldenTouchDmaRouteOwner baseline={0};CHECK(!attach(&baseline));CHECK(!elden_touch_route_detach(&baseline,37));
    CHECK(m.cb0==0xe0&&m.writes==3&&elden_smmu_boot_route_state()==EldenSmmuBootSealedEmpty);
    CHECK(elden_smmu_boot_route_reserve(&m,&route)==-16); /* late install forbidden */
    reset();publish();install_model();uint32_t before[0x2000/4];memcpy(before,m.regs,sizeof(before));
    EldenTouchDmaRouteOwner known={0};CHECK(!attach(&known));CHECK(!elden_touch_route_observe(&known,37));
    CHECK(!elden_touch_route_detach(&known,37));before[0xc1c/4]=0;
    CHECK(!memcmp(before,m.regs,sizeof(before))&&m.cb0==0xe0&&m.writes==3);
    CHECK(elden_smmu_boot_route_commit(&m,&route)==-16&&elden_smmu_boot_route_poison(&m)==-16);
    for(unsigned test=0;test<8;test++){
        reset();install_model();if(test)publish();
        if(test==1)m.regs[(0x800+4*route.slot)/4]^=1;
        if(test==2)m.regs[(0xc00+4*route.slot)/4]^=1;
        if(test==3)m.regs[(0x1000+4*route.bank)/4]^=0x100;
        if(test==4)m.regs[(0x1800+4*route.bank)/4]=0;
        if(test==5)m.regs[(0x800+4*131)/4]=0x800000a3;
        if(test==6)m.regs[0xc00/4]=7;
        if(test==7)m.cb0|=1;
        EldenTouchDmaRouteOwner p={0};CHECK(attach(&p)==-16||p.error==-95);
        CHECK(!p.attached&&!m.writes&&!m.held);
    }
    for(unsigned test=0;test<9;test++){
        reset();EldenSmmuBootRoute bad=route;
        if(test==0)bad.slot=7;
        if(test==1)bad.slot=132;
        if(test==2)bad.bank=0;
        if(test==3)bad.bank=83;
        if(test==4)bad.smr|=0x10000;
        if(test==5)bad.s2cr=0;
        if(test==6)bad.cbar=0x1f000;
        if(test==7)bad.cba2r=0;
        if(test<8)CHECK(elden_smmu_boot_route_reserve(&m,&bad)==-22);
        else CHECK(elden_smmu_boot_route_reserve(NULL,&bad)==-22);
        CHECK(elden_smmu_boot_route_state()==EldenSmmuBootOpen);
    }
    reset();CHECK(!elden_smmu_boot_route_reserve(&m,&route));CHECK(elden_smmu_boot_route_seal()==-16);
    CHECK(elden_smmu_boot_route_commit(&route,&route)==-19);
    CHECK(!elden_smmu_boot_route_poison(&m));CHECK(elden_smmu_boot_route_seal()==-16);
    uint32_t value=0xabcd;CHECK(elden_smmu_boot_route_expected(0x820,0,&value)==-16&&value==0xabcd);
    reset();CHECK(!elden_smmu_boot_route_reserve(&m,&route));EldenSmmuBootRoute bad=route;bad.bank++;
    CHECK(elden_smmu_boot_route_commit(&m,&bad)==-71&&elden_smmu_boot_route_state()==EldenSmmuBootPoisoned);
    for(unsigned i=0;i<100;i++){
        reset();go=0;reserve_rc=seal_rc=99;pthread_t a,b;
        CHECK(!pthread_create(&a,NULL,race_reserve,&m));CHECK(!pthread_create(&b,NULL,race_seal,NULL));
        __atomic_store_n(&go,1,__ATOMIC_RELEASE);CHECK(!pthread_join(a,NULL)&&!pthread_join(b,NULL));
        CHECK((reserve_rc==0&&seal_rc==-16)||(reserve_rc==-16&&seal_rc==0));
        if(!reserve_rc){CHECK(!elden_smmu_boot_route_commit(&m,&route));CHECK(!elden_smmu_boot_route_seal());}
        CHECK(!elden_smmu_boot_route_expected(0x800+4*route.slot,0,&value));
        CHECK(value==(reserve_rc?0:route.smr));
    }
    printf("%u boot/route scenarios / %u checks passed; original rejection reproduced; MMIO modeled\n",cases,checks);
    return 0;
}
