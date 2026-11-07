/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef KSHIM_STORAGE_BLOCK_H
#define KSHIM_STORAGE_BLOCK_H
#include <stddef.h>
#include <stdint.h>

enum kshim_storage_result {
    KSHIM_STORAGE_OK = 0,
    KSHIM_STORAGE_ARG = -1,
    KSHIM_STORAGE_IO = -2,
    KSHIM_STORAGE_FORMAT = -3,
    KSHIM_STORAGE_CRC = -4,
    KSHIM_STORAGE_NOT_FOUND = -5,
    KSHIM_STORAGE_CONFLICT = -6,
    KSHIM_STORAGE_RANGE = -7,
    KSHIM_STORAGE_EMPTY = -8,
    KSHIM_STORAGE_OVERFLOW = -9,
    KSHIM_STORAGE_READ_ONLY = -10
};
struct kshim_blockdev {
    void *ctx;
    uint32_t block_size;
    uint64_t block_count;
    int (*read)(void *ctx, uint64_t lba, uint32_t count, void *buffer);
    int (*write)(void *ctx, uint64_t lba, uint32_t count, const void *buffer);
    int (*flush)(void *ctx);
};
struct kshim_partition {
    uint64_t first_lba;
    uint64_t last_lba; /* inclusive */
    uint8_t uuid[16]; /* canonical RFC 4122 byte order */
};
#define KSHIM_STORAGE_SCRATCH_BYTES 8192u
/* All callbacks return zero on success. A nonzero result becomes IO. */
int kshim_block_read(const struct kshim_blockdev *, uint64_t, uint32_t, void *);
int kshim_block_write(const struct kshim_blockdev *, uint64_t, uint32_t, const void *);
int kshim_block_flush(const struct kshim_blockdev *);
uint32_t kshim_crc32(const void *, size_t);
/* Primary GPT only; at most 256 entries, power-of-two entry sizes 128..4096.
 * Checks the entire declared header and entry-array CRC, all occupied ranges,
 * and unique ARMADA_BACKUP name. Never repairs or writes GPT. */
int kshim_gpt_find_backup(const struct kshim_blockdev *, struct kshim_partition *,
                          void *scratch, size_t scratch_bytes);
#endif
