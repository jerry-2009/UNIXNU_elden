/* SPDX-License-Identifier: GPL-3.0-only */
#include "storage_block.h"

static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
           (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static uint64_t get64(const uint8_t *p)
{
    return get32(p) | (uint64_t)get32(p + 4) << 32;
}
static void put64(uint8_t *p, uint64_t v)
{
    for (unsigned i = 0; i < 8; ++i) p[i] = (uint8_t)(v >> (8 * i));
}
static int zero(const uint8_t *p, size_t n)
{
    while (n--) if (*p++) return 0;
    return 1;
}
static int same(const uint8_t *a, const uint8_t *b, size_t n)
{
    while (n--) if (*a++ != *b++) return 0;
    return 1;
}
static int device_valid(const struct kshim_blockdev *d)
{
    return d && (d->block_size == 512 || d->block_size == 4096) && d->block_count;
}
static int request_valid(const struct kshim_blockdev *d, uint64_t lba,
                         uint32_t count, const void *buffer)
{
    if (!device_valid(d) || !buffer || !count) return KSHIM_STORAGE_ARG;
    if (lba >= d->block_count || count > d->block_count - lba)
        return KSHIM_STORAGE_RANGE;
    if ((uint64_t)count * d->block_size > SIZE_MAX) return KSHIM_STORAGE_RANGE;
    return KSHIM_STORAGE_OK;
}
int kshim_block_read(const struct kshim_blockdev *d, uint64_t lba,
                     uint32_t count, void *buffer)
{
    int rc = request_valid(d, lba, count, buffer);
    if (rc) return rc;
    if (!d->read) return KSHIM_STORAGE_ARG;
    return d->read(d->ctx, lba, count, buffer) ? KSHIM_STORAGE_IO : KSHIM_STORAGE_OK;
}
int kshim_block_write(const struct kshim_blockdev *d, uint64_t lba,
                      uint32_t count, const void *buffer)
{
    int rc = request_valid(d, lba, count, buffer);
    if (rc) return rc;
    if (!d->write) return KSHIM_STORAGE_READ_ONLY;
    return d->write(d->ctx, lba, count, buffer) ? KSHIM_STORAGE_IO : KSHIM_STORAGE_OK;
}
int kshim_block_flush(const struct kshim_blockdev *d)
{
    if (!device_valid(d)) return KSHIM_STORAGE_ARG;
    if (!d->flush) return KSHIM_STORAGE_READ_ONLY;
    return d->flush(d->ctx) ? KSHIM_STORAGE_IO : KSHIM_STORAGE_OK;
}
static uint32_t crc_update(uint32_t crc, const uint8_t *data, size_t size)
{
    static const uint32_t nibble[16] = {
        0x00000000, 0x1db71064, 0x3b6e20c8, 0x26d930ac,
        0x76dc4190, 0x6b6b51f4, 0x4db26158, 0x5005713c,
        0xedb88320, 0xf00f9344, 0xd6d6a3e8, 0xcb61b38c,
        0x9b64c2b0, 0x86d3d2d4, 0xa00ae278, 0xbdbdf21c
    };
    while (size--) {
        crc ^= *data++;
        crc = (crc >> 4) ^ nibble[crc & 15];
        crc = (crc >> 4) ^ nibble[crc & 15];
    }
    return crc;
}
uint32_t kshim_crc32(const void *data, size_t size)
{
    return ~crc_update(UINT32_MAX, data, size);
}
static int backup_name(const uint8_t *entry)
{
    static const uint8_t name[] = "ARMADA_BACKUP";
    for (size_t i = 0; i < 36; ++i) {
        uint8_t want = i < sizeof(name) - 1 ? name[i] : 0;
        if (entry[56 + 2 * i] != want || entry[57 + 2 * i]) return 0;
    }
    return 1;
}
static void canonical_uuid(uint8_t *dst, const uint8_t *src)
{
    dst[0] = src[3]; dst[1] = src[2]; dst[2] = src[1]; dst[3] = src[0];
    dst[4] = src[5]; dst[5] = src[4]; dst[6] = src[7]; dst[7] = src[6];
    for (unsigned i = 8; i < 16; ++i) dst[i] = src[i];
}
int kshim_gpt_find_backup(const struct kshim_blockdev *d,
                          struct kshim_partition *out,
                          void *scratch, size_t scratch_bytes)
{
    uint8_t *block = scratch;
    if (!device_valid(d) || !out || !block ||
        scratch_bytes < KSHIM_STORAGE_SCRATCH_BYTES) return KSHIM_STORAGE_ARG;
    if (d->block_count < 6) return KSHIM_STORAGE_RANGE;
    int rc = kshim_block_read(d, 1, 1, block);
    if (rc) return rc;
    if (!same(block, (const uint8_t *)"EFI PART", 8) ||
        get32(block + 8) != 0x00010000 || get32(block + 20))
        return KSHIM_STORAGE_FORMAT;
    uint32_t header_bytes = get32(block + 12);
    if (header_bytes < 92 || header_bytes > d->block_size) return KSHIM_STORAGE_FORMAT;
    uint32_t stored_crc = get32(block + 16);
    for (unsigned i = 16; i < 20; ++i) block[i] = 0;
    if (kshim_crc32(block, header_bytes) != stored_crc) return KSHIM_STORAGE_CRC;
    uint64_t first = get64(block + 40), last = get64(block + 48);
    uint64_t table_lba = get64(block + 72);
    uint32_t count = get32(block + 80), entry_bytes = get32(block + 84);
    uint32_t table_crc = get32(block + 88);
    if (get64(block + 24) != 1 || get64(block + 32) != d->block_count - 1 ||
        zero(block + 56, 16) || !count || count > 256 ||
        entry_bytes < 128 || entry_bytes > 4096 || (entry_bytes & (entry_bytes - 1)))
        return KSHIM_STORAGE_FORMAT;
    uint64_t table_bytes = (uint64_t)count * entry_bytes;
    uint64_t blocks = (table_bytes + d->block_size - 1) / d->block_size;
    if (first < 2 || first > last || last >= d->block_count - 1 ||
        table_lba < 2 || table_lba >= first || blocks > first - table_lba ||
        blocks >= d->block_count - 1 || last >= d->block_count - 1 - blocks)
        return KSHIM_STORAGE_RANGE;
    /* Each prior occupied partition uses 16 bytes in caller scratch, so
     * overlap validation needs neither allocation nor a large stack frame. */
    uint8_t *ranges = block + 4096;
    uint32_t used = 0, matches = 0, crc = UINT32_MAX;
    struct kshim_partition found = {0};
    for (uint64_t offset = 0; offset < table_bytes; offset += d->block_size) {
        rc = kshim_block_read(d, table_lba + offset / d->block_size, 1, block);
        if (rc) return rc;
        size_t take = table_bytes - offset < d->block_size ?
                      (size_t)(table_bytes - offset) : d->block_size;
        crc = crc_update(crc, block, take);
        for (size_t pos = 0; pos < take; pos += 128) {
            if ((offset + pos) % entry_bytes) continue;
            const uint8_t *e = block + pos;
            if (zero(e, 16)) continue;
            if (zero(e + 16, 16)) return KSHIM_STORAGE_FORMAT;
            uint64_t start = get64(e + 32), end = get64(e + 40);
            if (start < first || end > last || start > end) return KSHIM_STORAGE_RANGE;
            for (uint32_t j = 0; j < used; ++j) {
                uint64_t prior_start = get64(ranges + 16 * j);
                uint64_t prior_end = get64(ranges + 16 * j + 8);
                if (start <= prior_end && prior_start <= end) return KSHIM_STORAGE_RANGE;
            }
            put64(ranges + 16 * used, start);
            put64(ranges + 16 * used + 8, end);
            ++used;
            if (backup_name(e)) {
                if (++matches > 1) return KSHIM_STORAGE_CONFLICT;
                found.first_lba = start; found.last_lba = end;
                canonical_uuid(found.uuid, e + 16);
            }
        }
    }
    if (~crc != table_crc) return KSHIM_STORAGE_CRC;
    if (!matches) return KSHIM_STORAGE_NOT_FOUND;
    *out = found;
    return KSHIM_STORAGE_OK;
}
