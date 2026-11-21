/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include "ChargePoll.h"
/* Radio execution is distinct from permission to change charger policy.
 * Raw12 is the OEM Cool state observed with stock Android at18--20C; do not
 * substitute a newer Linux enum (which inserted Undervoltage). No SET here. */
static inline bool elden_wifi_battery_snapshot_safe(const EldenChargeRawSnapshot *r,
    uint64_t age_ms,uint32_t expected_epoch)
{
    if(!r||!r->epoch||!r->cycle||r->cycle<4||age_ms>=10000||
       (expected_epoch&&r->epoch!=expected_epoch)||
       r->valid!=((UINT64_C(1)<<EldenChargeFieldCount)-1))return false;
    uint32_t health=r->value[EldenChargeHealth].raw;
    int64_t t=r->value[EldenChargeTemperature].signed_value;
    uint32_t v=r->value[EldenChargeVoltage].raw,soc=r->value[EldenChargeCapacity].raw;
    if(r->value[EldenChargePresent].raw!=1||r->value[EldenChargeUsbOnline].raw!=1||
       r->value[EldenChargeInputSuspended].raw!=0||v<3800000||v>4500000||
       soc<4000||soc>10000||t<1000||t>3500||(health!=1&&health!=12)||
       (health==12&&t>2200))return false;
    for(unsigned i=0;i<2;i++){
        uint32_t fg_v=r->value[i?EldenChargeFg2Voltage:EldenChargeFg1Voltage].raw;
        uint32_t fg_soc=r->value[i?EldenChargeFg2Soc:EldenChargeFg1Soc].raw;
        int64_t fg_t=r->value[i?EldenChargeFg2Temperature:EldenChargeFg1Temperature].signed_value;
        if(fg_v<3800000||fg_v>4500000||(fg_v>v?fg_v-v:v-fg_v)>200000||
           fg_soc<40||fg_soc>100||(fg_soc*100>soc?fg_soc*100-soc:soc-fg_soc*100)>200||
           fg_t<100||fg_t>350||(fg_t*10>t?fg_t*10-t:t-fg_t*10)>500)return false;
    }
    return true;
}
