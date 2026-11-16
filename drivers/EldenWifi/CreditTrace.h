/* SPDX-License-Identifier: BSD-3-Clause-Clear */
#pragma once
#include <stdint.h>
enum {
 EctAlloc,EctFlow,EctCurrent,EctTxAttempt,EctTxOk,EctNoCredit,EctTxFail,
 EctRx,EctTrailer,EctReport,EctAdded,EctTxInfo,EctTxCtrl,EctRxInfo,EctRxCtrl,
 EctCallback,EctCreditSize,EctUlPipe,EctDlPipe,EctService,EctEpStride
};
enum {EctCeIrq,EctCeOff,EctCeEnter,EctCeExit,EctCeStride};
enum {EctCeBase=16*EctEpStride,EctOtherBase=EctCeBase+16*EctCeStride,
 EctWmiCmd=EctOtherBase,EctWmiCalls,EctWmiOk,EctWmiResult,EctDevFlags,EctWords};
#ifdef __cplusplus
extern "C" {
#endif
extern volatile uint64_t elden_wifi_credit_trace[EctWords];
static inline unsigned ect_ep(unsigned eid,unsigned field){return eid<16&&field<EctEpStride?eid*EctEpStride+field:EctWords;}
static inline unsigned ect_ce(unsigned ce,unsigned field){return ce<16&&field<EctCeStride?EctCeBase+ce*EctCeStride+field:EctWords;}
static inline void ect_set(unsigned index,uint64_t value){if(index<EctWords)__atomic_store_n(&elden_wifi_credit_trace[index],value,__ATOMIC_RELAXED);}
static inline void ect_add(unsigned index,uint64_t value){if(index<EctWords)__atomic_fetch_add(&elden_wifi_credit_trace[index],value,__ATOMIC_RELAXED);}
#ifdef __cplusplus
}
#endif
