/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include "WcnPower.h"
#ifdef __cplusplus
extern "C" {
#endif

enum { EldenWcnBluetooth = 0, EldenWcnWlan = 1, EldenWcnConsumers = 2 };
enum { EldenWcnLeaseOff, EldenWcnLeaseOn };

/* One zero-initialized, platform-lifetime owner. Install io and wlan_set before
 * publishing; never copy/reinitialize it or run the legacy owner alongside it.
 * Callbacks must return real errors and setters must verify physical readback.
 * Native device/epoch binding and hardware mappings belong to its adapter. */
typedef struct {
    EldenWcnPower supply;
    int (*wlan_set)(void *, bool);
    uint64_t epoch[EldenWcnConsumers];
    unsigned state[EldenWcnConsumers];
    EldenWcnPdcVote cpr[EldenWcnConsumers][4];
    unsigned busy;
    bool prepared, held;
} EldenWcnSharedPower;

typedef struct {
    uint64_t epoch[EldenWcnConsumers];
    unsigned state[EldenWcnConsumers];
    unsigned qmp_messages, rail_votes;
    bool prepared, held, baseline_votes_retained;
    int error;
} EldenWcnSharedSnapshot;

/* Calls serialize complete transactions. Contention/reentry returns -11 with
 * no I/O; there is no spin/sleep lock and no implicit retry. Epochs strictly
 * increase per consumer. Unknown live boot consumers are never reset/adopted.
 * A partial/uncertain transaction is terminal Held until platform reset. */
int elden_wcn_shared_acquire(EldenWcnSharedPower *, unsigned consumer, uint64_t epoch);
int elden_wcn_shared_stop(EldenWcnSharedPower *, unsigned consumer, uint64_t epoch);
int elden_wcn_shared_cpr(EldenWcnSharedPower *, unsigned consumer, uint64_t epoch,
                       const EldenWcnPmuParam *, size_t);
int elden_wcn_shared_snapshot(EldenWcnSharedPower *, EldenWcnSharedSnapshot *);
#ifdef __cplusplus
}
#endif
