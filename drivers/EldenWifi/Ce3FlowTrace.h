/* SPDX-License-Identifier: BSD-3-Clause-Clear */
#ifndef ELDEN_WIFI_CE3_FLOW_TRACE_H
#define ELDEN_WIFI_CE3_FLOW_TRACE_H
struct ath12k_base;
enum {
    EcfWmiRequest = 1,
    EcfWmiResult,
    EcfPdevSelector,
    EcfCePost,
    EcfCeReap,
    EcfCeEmpty,
    EcfCeReject
};
void elden_wifi_ce3_flow_note(struct ath12k_base *, unsigned,
                            unsigned long long, unsigned long long,
                            unsigned long long, unsigned long long,
                            unsigned long long);
void elden_wifi_ce3_flow_dump(struct ath12k_base *);
#endif
