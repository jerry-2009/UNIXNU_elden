/* SPDX-License-Identifier: BSD-3-Clause-Clear */
#ifndef ELDEN_SRNG_TRACE_H
#define ELDEN_SRNG_TRACE_H
struct ath12k_base;
void elden_wifi_srng_first_wmi(struct ath12k_base *ab);
unsigned int elden_wifi_pci_diag_read(struct ath12k_base *ab, unsigned int offset);
#endif
