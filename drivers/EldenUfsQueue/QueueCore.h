// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
#include <stdint.h>

// Implements ShengUfs's bitmap + FIFO handoff with terminal stop/quarantine and
// generation-checked leases. The native adapter must hold ONE pool mutex around
// every operation, including issue -> doorbell publication. IRQs never take it.
enum EldenUfsPoolResult : uint32_t {
    EldenUfsGranted, EldenUfsQueued, EldenUfsStopped, EldenUfsInvalid,
    EldenUfsDmaOwned, EldenUfsStale, EldenUfsNotComplete
};
enum EldenUfsSlotState : uint32_t { EldenUfsFree, EldenUfsLeased, EldenUfsIssued, EldenUfsDone, EldenUfsQuarantined };
struct EldenUfsPool;
struct EldenUfsLease { const EldenUfsPool *pool; uint64_t generation; uint32_t slot,entry; };
struct EldenUfsWaiter {
    EldenUfsWaiter *next;
    EldenUfsPool *owner;
    EldenUfsLease lease;
    uint32_t state; // 0 fresh, 1 queued, 2 granted, 3 withdrawn
    EldenUfsPoolResult result;
};
struct EldenUfsPoolSlot { uint64_t generation; uint32_t entry; EldenUfsSlotState state; };
struct EldenUfsPool {
    uint32_t initialized,count,freeMask,issuedMask,busy,peak,queued;
    bool closed,failed;
    uint64_t generation;
    EldenUfsWaiter *head,*tail;
    EldenUfsPoolSlot slots[32];
};
extern "C" {
// A pool starts zero-initialized and cannot be reopened. entryStride=1 for an
// independent uncached request list; stride=2 for isolated cached cache lines.
EldenUfsPoolResult elden_ufs_pool_init(EldenUfsPool*,uint32_t slots,uint32_t entries,uint32_t entryStride);
EldenUfsPoolResult elden_ufs_pool_take(EldenUfsPool*,EldenUfsLease*);
EldenUfsPoolResult elden_ufs_pool_enqueue(EldenUfsPool*,EldenUfsWaiter*);
// If a timeout races a grant, cancel returns Granted and the caller owns lease.
EldenUfsPoolResult elden_ufs_pool_cancel(EldenUfsPool*,EldenUfsWaiter*);
EldenUfsPoolResult elden_ufs_pool_issue(EldenUfsPool*,const EldenUfsLease*);
EldenUfsPoolResult elden_ufs_pool_complete(EldenUfsPool*,const EldenUfsLease*,uint32_t doorbell,uint32_t ocs,uint32_t interruptStatus);
EldenUfsPoolResult elden_ufs_pool_release(EldenUfsPool*,const EldenUfsLease*);
// Stop wakes/removes waiters but does not manufacture command completion. With
// uncertain DMA, issued leases become quarantined and may NEVER be released.
void elden_ufs_pool_stop(EldenUfsPool*,bool uncertainDma);
}
