/* SPDX-License-Identifier: BSD-3-Clause-Clear */
#ifndef ELDEN_WIFI_MODE_TRACE_META_H
#define ELDEN_WIFI_MODE_TRACE_META_H
enum {
    EcfModeRequestMarker = 0x4d4f4445,
    EcfFirmwareEventMarker = 0x45564e54,
    EcfFirmwareCapsMarker = 0x43415053,
    EcfFirmwarePdevMarker = 0x50444556
};
static unsigned emt_caps, emt_pdev, emt_events;
/* Bound new metadata independently so existing CE records retain capacity. */
static int emt_claim(unsigned *counter, unsigned limit)
{
    unsigned count = __atomic_load_n(counter, __ATOMIC_RELAXED);
    while (count < limit) {
        if (__atomic_compare_exchange_n(counter, &count, count + 1, 0,
                                        __ATOMIC_RELAXED, __ATOMIC_RELAXED)) return 1;
    }
    return 0;
}
#endif
