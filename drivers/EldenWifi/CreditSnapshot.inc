/* SPDX-License-Identifier: BSD-3-Clause-Clear */
#include "CreditTrace.h"
/* Same wireless worker writes counters and takes this first-failure copy. */
static uint64_t credit_copy[EctWords];
static void runtime_credit_snapshot(){
    for(unsigned i=0;i<EctWords;i++)credit_copy[i]=__atomic_load_n(&elden_wifi_credit_trace[i],__ATOMIC_RELAXED);
    log("\nELDEN_CREDIT WMI cmd=%llu calls=%llu ok=%llu result=%lld devflags=%llx\n",(unsigned long long)credit_copy[EctWmiCmd],
        (unsigned long long)credit_copy[EctWmiCalls],(unsigned long long)credit_copy[EctWmiOk],(long long)credit_copy[EctWmiResult],(unsigned long long)credit_copy[EctDevFlags]);
    for(unsigned e=0;e<16;e++){
        uint64_t *s=credit_copy+e*EctEpStride;if(!s[EctTxAttempt]&&!s[EctRx]&&!s[EctAlloc])continue;
        log("\nELDEN_CREDIT CFG ep=%u alloc=%llu flow=%llu current=%lld size=%llu ul=%llu dl=%llu service=%llx\n",e,
            (unsigned long long)s[EctAlloc],(unsigned long long)s[EctFlow],(long long)s[EctCurrent],(unsigned long long)s[EctCreditSize],
            (unsigned long long)s[EctUlPipe],(unsigned long long)s[EctDlPipe],(unsigned long long)s[EctService]);
        log("\nELDEN_CREDIT TX ep=%u ok=%llu attempts=%llu shortage=%llu errors=%llu header=%llx/%llx\n",e,
            (unsigned long long)s[EctTxOk],(unsigned long long)s[EctTxAttempt],(unsigned long long)s[EctNoCredit],(unsigned long long)s[EctTxFail],
            (unsigned long long)s[EctTxInfo],(unsigned long long)s[EctTxCtrl]);
        log("\nELDEN_CREDIT RX ep=%u frames=%llu trailers=%llu reports=%llu added=%llu cb=%llu header=%llx/%llx\n",e,
            (unsigned long long)s[EctRx],(unsigned long long)s[EctTrailer],(unsigned long long)s[EctReport],(unsigned long long)s[EctAdded],(unsigned long long)s[EctCallback],
            (unsigned long long)s[EctRxInfo],(unsigned long long)s[EctRxCtrl]);
    }
    for(unsigned c=0;c<16;c++){
        uint64_t *s=credit_copy+EctCeBase+c*EctCeStride;if(!s[EctCeIrq]&&!s[EctCeEnter])continue;
        log("\nELDEN_CREDIT CE=%u irq=%llu flag-off=%llu enter=%llu exit=%llu\n",c,(unsigned long long)s[EctCeIrq],
            (unsigned long long)s[EctCeOff],(unsigned long long)s[EctCeEnter],(unsigned long long)s[EctCeExit]);
    }
}
