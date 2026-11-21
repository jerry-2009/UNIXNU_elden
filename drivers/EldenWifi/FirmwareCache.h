/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    uint32_t version,run,stopping,loaded,slot,reads;
    int32_t error;
    uint64_t bytes,epoch;
} EldenWifiFirmwareStatus;
int elden_wifi_firmware_bind(const void *provider,uint64_t epoch);
int elden_wifi_firmware_get(const char *name,const uint8_t **data,size_t *bytes);
void elden_wifi_firmware_stop_begin(void);
int elden_wifi_firmware_status(EldenWifiFirmwareStatus *);
#ifdef __cplusplus
}
#endif
