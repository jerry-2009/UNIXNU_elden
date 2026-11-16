/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include <stdint.h>
#include <stddef.h>
/* Exact Ath12kWifi5f7f5a8 nw_control_endpoint.h layout. */
struct nw_control_stats {
    uint64_t accepted,dispatched,replies,events,malformed,stale_sessions,rx_full,tx_full,send_retries;
    size_t rx_bytes,tx_bytes;unsigned rx_items,tx_items;
    uint64_t connections,disconnections,active_session;unsigned last_operation,last_status;
};
extern "C" void nw_wifi_control_stats_get(struct nw_control_stats *);
static_assert(sizeof(nw_control_stats)==128&&offsetof(nw_control_stats,last_operation)==120,"control stats ABI");
