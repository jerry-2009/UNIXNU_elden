/* SPDX-License-Identifier: BSD-3-Clause-Clear */
#pragma once
#include <stdint.h>
struct ath12k_base;
#ifdef __cplusplus
extern "C" {
#endif
void elden_ce3_timeline(struct ath12k_base *,uint32_t stage,int32_t result);
#ifdef __cplusplus
}
#endif
