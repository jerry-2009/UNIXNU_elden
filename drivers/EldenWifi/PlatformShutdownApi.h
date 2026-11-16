/* Owned extension to the unchanged upstream runtime ABI. Platform reset only. */
#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
int nw_wifi_platform_shutdown(void);
int elden_nw_pci_platform_shutdown(void);
uint64_t elden_wifi_platform_deadline_ms(void);
#ifdef __cplusplus
}
#endif
