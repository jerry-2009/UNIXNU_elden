/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "BootRoute.h"
#include <stddef.h>
static unsigned state;
static const void *owner;
static EldenSmmuBootRoute intended,published;

static int same(const EldenSmmuBootRoute *a,const EldenSmmuBootRoute *b){
    return a->slot==b->slot&&a->bank==b->bank&&a->smr==b->smr&&a->s2cr==b->s2cr&&a->cbar==b->cbar&&a->cba2r==b->cba2r;
}
static int valid(const EldenSmmuBootRoute *r){
    /* TB322FC has132 slots/83 banks. Preserve boot slots0..6, touch slot7 and
     * boot banks0..6 (especially inherited bypass CB0). Exact Wi-Fi SID only;
     * no masks, EXIDS, privilege override or other consumer is accepted. */
    return r&&r->slot>=8&&r->slot<132&&r->bank>=7&&r->bank<83&&
        r->smr==0x80001401u&&r->s2cr==r->bank&&r->cbar==0x0001f300u&&r->cba2r==1;
}
unsigned elden_smmu_boot_route_state(void){return __atomic_load_n(&state,__ATOMIC_ACQUIRE);}
int elden_smmu_boot_route_reserve(const void *provider,const EldenSmmuBootRoute *plan){
    if(!provider||!valid(plan))return -22;
    unsigned expected=EldenSmmuBootOpen;
    if(!__atomic_compare_exchange_n(&state,&expected,EldenSmmuBootPreparing,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return -16;
    owner=provider;intended=*plan;return 0;
}
int elden_smmu_boot_route_commit(const void *provider,const EldenSmmuBootRoute *observed){
    if(elden_smmu_boot_route_state()!=EldenSmmuBootPreparing)return -16;
    /* Only the serialized early provider may commit/poison. Other threads use
     * seal/expected; they never read owner or these mutable records. */
    if(!provider||provider!=owner)return -19;
    if(!valid(observed)||!same(&intended,observed)){
        __atomic_store_n(&state,EldenSmmuBootPoisoned,__ATOMIC_RELEASE);return -71;
    }
    published=*observed;__atomic_store_n(&state,EldenSmmuBootReady,__ATOMIC_RELEASE);return 0;
}
int elden_smmu_boot_route_poison(const void *provider){
    if(elden_smmu_boot_route_state()!=EldenSmmuBootPreparing)return -16;
    if(!provider||provider!=owner)return -19;
    __atomic_store_n(&state,EldenSmmuBootPoisoned,__ATOMIC_RELEASE);return 0;
}
int elden_smmu_boot_route_seal(void){
    for(unsigned i=0;i<2;i++){
        unsigned current=elden_smmu_boot_route_state(),next;
        if(current==EldenSmmuBootSealedEmpty||current==EldenSmmuBootSealedReady)return 0;
        if(current==EldenSmmuBootOpen)next=EldenSmmuBootSealedEmpty;
        else if(current==EldenSmmuBootReady)next=EldenSmmuBootSealedReady;
        else return -16;
        if(__atomic_compare_exchange_n(&state,&current,next,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return 0;
    }
    return -16;
}
int elden_smmu_boot_route_expected(uint32_t offset,uint32_t baseline,uint32_t *expected){
    if(!expected)return -22;
    unsigned current=elden_smmu_boot_route_state();
    if(current!=EldenSmmuBootSealedEmpty&&current!=EldenSmmuBootSealedReady)return -16;
    uint32_t value=baseline;
    if(current==EldenSmmuBootSealedReady){
        if(offset==0x800+4*published.slot)value=published.smr;
        else if(offset==0xc00+4*published.slot)value=published.s2cr;
        else if(offset==0x1000+4*published.bank)value=published.cbar;
        else if(offset==0x1800+4*published.bank)value=published.cba2r;
    }
    *expected=value;return 0;
}
