/* SPDX-License-Identifier: BSD-3-Clause-Clear */
/* Control metadata only. Included in the exact CE production unit. */
#include "Ce3FlowTrace.h"
#include "CreditTrace.h"
#define ECF_LIMIT 64U
struct ecf_record {
    unsigned ready, kind;
    u64 ms, a, b, c, d, e, credit, reports;
};
static struct ecf_record ecf_records[ECF_LIMIT];
static unsigned ecf_count, ecf_dropped, ecf_dumped;
static void ecf_drop(void)
{
    unsigned count = __atomic_load_n(&ecf_dropped, __ATOMIC_RELAXED);
    while (count != (unsigned)-1 &&
           !__atomic_compare_exchange_n(&ecf_dropped, &count, count + 1, 0,
                                        __ATOMIC_RELAXED, __ATOMIC_RELAXED)) { }
}
void elden_wifi_ce3_flow_note(struct ath12k_base *ab, unsigned kind,
                            unsigned long long a, unsigned long long b,
                            unsigned long long c, unsigned long long d,
                            unsigned long long e)
{
    unsigned index;
    struct ecf_record *record;
    if (!ab || kind < EcfWmiRequest || kind > EcfCeReject ||
        __atomic_load_n(&ecf_dumped, __ATOMIC_ACQUIRE)) return;
    index = __atomic_load_n(&ecf_count, __ATOMIC_RELAXED);
    for (;;) {
        if (index >= ECF_LIMIT) { ecf_drop(); return; }
        if (__atomic_compare_exchange_n(&ecf_count, &index, index + 1, 0,
                                        __ATOMIC_RELAXED, __ATOMIC_RELAXED)) break;
    }
    record = &ecf_records[index];
    record->ms = READ_ONCE(jiffies);
    record->kind = kind;
    record->a = a; record->b = b; record->c = c; record->d = d; record->e = e;
    record->credit = __atomic_load_n(&elden_wifi_credit_trace[ect_ep(2, EctCurrent)],
                                     __ATOMIC_RELAXED);
    record->reports = __atomic_load_n(&elden_wifi_credit_trace[ect_ep(2, EctReport)],
                                      __ATOMIC_RELAXED);
    __atomic_store_n(&record->ready, 1, __ATOMIC_RELEASE);
}
void elden_wifi_ce3_flow_dump(struct ath12k_base *ab)
{
    unsigned count, emitted = 0;
    if (!ab || __atomic_exchange_n(&ecf_dumped, 1, __ATOMIC_ACQ_REL)) return;
    count = __atomic_load_n(&ecf_count, __ATOMIC_ACQUIRE);
    if (count > ECF_LIMIT) count = ECF_LIMIT;
    for (unsigned i = 0; i < count; i++) {
        const struct ecf_record *record = &ecf_records[i];
        if (!__atomic_load_n(&record->ready, __ATOMIC_ACQUIRE)) continue;
        ath12k_warn(ab, "ELDEN_CE3_FLOW seq=%u ms=%llu kind=%u a=%llx b=%llx c=%llx d=%llx e=%llx credit=%llx reports=%llx\n",
                    i, (unsigned long long)record->ms, record->kind,
                    (unsigned long long)record->a, (unsigned long long)record->b,
                    (unsigned long long)record->c, (unsigned long long)record->d,
                    (unsigned long long)record->e, (unsigned long long)record->credit,
                    (unsigned long long)record->reports);
        emitted++;
    }
    ath12k_warn(ab, "ELDEN_CE3_FLOW_END claimed=%u emitted=%u dropped=%u; pointer/credit observations are not atomic together\n",
                count, emitted, __atomic_load_n(&ecf_dropped, __ATOMIC_RELAXED));
}
