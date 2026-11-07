/* SPDX-License-Identifier: GPL-3.0-only */
#pragma once
#include "Core/storage_ufs.h"

enum elden_ufs_state { ELDEN_UFS_CLOSED, ELDEN_UFS_OPENING, ELDEN_UFS_READY,
                       ELDEN_UFS_FAILED, ELDEN_UFS_QUARANTINED };
struct elden_ufs_backend {
    struct kshim_ufs_ops io;
    /* Zero only when the current CPU mapping and current inherited SMMU
     * route admit this entire DMA span. Called before claim and every submit. */
    int (*admit_dma)(void *ctx, uint64_t physical, size_t bytes);
};
struct elden_ufs_session {
    struct elden_ufs_backend backend;
    struct kshim_ufs_host host;
    struct kshim_ufs_lun lun;
    struct kshim_partition partition;
    enum elden_ufs_state state;
    unsigned stage, blocked_commands;
    int result;
    bool busy;
    uint8_t scratch[KSHIM_STORAGE_SCRATCH_BYTES];
};
/* Zero-initialize once. Every failed open/read must be followed by close.
 * No caller may free the arena or hand off unless can_handoff returns true.
 * A quarantined session requires an external controller reset/new boot. */
int elden_ufs_open(struct elden_ufs_session *, const struct elden_ufs_backend *,
                   void *arena, size_t bytes, uint64_t physical);
int elden_ufs_read(struct elden_ufs_session *, uint64_t offset, size_t bytes, void *output);
int elden_ufs_close(struct elden_ufs_session *);
bool elden_ufs_can_handoff(const struct elden_ufs_session *);
uint64_t elden_ufs_partition_bytes(const struct elden_ufs_session *);
