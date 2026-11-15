/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include <stdint.h>
enum EldenPdObservation {EldenPdUnavailable=0,EldenPdPending=1,EldenPdReady=2,
    EldenPdFailed=3,EldenPdDisabled=4,EldenPdExpired=5};
static inline uint64_t elden_pd_observation_pack(unsigned state,uint32_t epoch,uint64_t now_ms){
    if(state>EldenPdDisabled||!epoch||epoch>0x1fffffffu)return 0;
    return ((uint64_t)(uint32_t)now_ms<<32)|((uint64_t)epoch<<3)|state;
}
static inline unsigned elden_pd_observation_read(uint64_t value,uint32_t epoch,uint64_t now_ms){
    unsigned state=(unsigned)value&7;
    if(!value||!epoch||epoch>0x1fffffffu||((value>>3)&0x1fffffffu)!=epoch||state>EldenPdDisabled)return EldenPdUnavailable;
    if((state==EldenPdReady||state==EldenPdPending)&&(uint32_t)((uint32_t)now_ms-(uint32_t)(value>>32))>3000u)return EldenPdExpired;
    return state;
}
