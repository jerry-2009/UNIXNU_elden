/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Elden extension to the fixed donor 802.1X wire. No key/PMK crosses this ACK.
 * The kernel starts association only after preparation on the current socket
 * session and generation. Completion is neither association nor authorization.
 */
#ifndef ELDEN_WIFI_PROFILE_READY_H
#define ELDEN_WIFI_PROFILE_READY_H
#include <stdint.h>
#define ELDEN_WIFI_PROFILE_READY 21u
#define ELDEN_WIFI_PROFILE_READY_VERSION 1u
struct elden_wifi_profile_ready {
    uint32_t generation;
    int32_t status;
} __attribute__((packed));
#endif
