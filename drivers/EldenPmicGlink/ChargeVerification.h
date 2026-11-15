/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include "ChargePolicy.h"

/* Match the telemetry publisher's ten-second freshness boundary. */
static inline bool elden_charge_verify_fresh(uint64_t age_ms,uint32_t epoch,uint32_t policy_epoch,
                                           bool telemetry_good,bool complete){
    return age_ms<10000&&epoch&&epoch==policy_epoch&&telemetry_good&&complete;
}
static inline bool elden_charge_verify_waiting(const EldenChargePolicy *s){
    return s->up&&(s->phase==EldenPolicyWaitWindow||s->phase==EldenPolicyWaitEnable);
}
/* No I/O or retry: a missing verification becomes an explicit failed result. */
static inline void elden_charge_verify_tick(EldenChargePolicy *s,uint64_t now_ms,bool telemetry_failed,uint64_t *deadline){
    if(!elden_charge_verify_waiting(s)){*deadline=0;return;}
    if(telemetry_failed){*deadline=0;elden_charge_policy_timeout(s);return;}
    if(!*deadline){*deadline=now_ms>UINT64_MAX-30000?UINT64_MAX:now_ms+30000;return;}
    if(now_ms>=*deadline){*deadline=0;elden_charge_policy_timeout(s);}
}
static inline bool elden_charge_verify_available(const EldenChargePolicy *s,bool allowed){
    return allowed&&s->up&&s->original_saved&&s->phase!=EldenPolicyOff&&s->phase!=EldenPolicyReadWindow&&
        s->phase!=EldenPolicyReadEu&&s->phase!=EldenPolicyFailed;
}
