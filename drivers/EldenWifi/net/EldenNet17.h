/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
int elden_wifi_net_start(const uint8_t mac[6]);
void elden_wifi_net_stop_begin(void);
/* Returns busy until every accepted callback returns. Does not unload or
 * reclaim retained ifnet/services; the bounded platform reset owns them. */
int elden_wifi_net_drain(void);
void elden_wifi_net_pump(uint64_t now_ms);
/* The retained native provider checks lifetime, stop, epoch and hardware
 * admission before any OS request calls the real station interface. */
int elden_wifi_net_admit(void);
void elden_wifi_net_static_init(void);
#ifdef __cplusplus
}
#endif
