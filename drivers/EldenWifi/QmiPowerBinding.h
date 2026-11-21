/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
struct device;
/* The board's PCIe/MHI glue calls bind only after obtaining the real WLAN
 * power lease, using the exact ab->dev consumer. Tokens remain alive until
 * unbind succeeds. The quiesce callback drains QMI calls and unbinds within
 * its deadline before reporting DMA stopped. Busy returns -11, never spins. */
int elden_wlan_qmi_bind(struct device *consumer,const void *provider,uint64_t epoch);
int elden_wlan_qmi_unbind(struct device *consumer,const void *provider,uint64_t epoch);
#ifdef __cplusplus
}
#endif
