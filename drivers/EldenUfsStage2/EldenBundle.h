/* SPDX-License-Identifier: GPL-3.0-only */
#pragma once
#include "Core/storage_block.h"
#define ELDEN_SLOT_HEADER_BYTES 4096
#define ELDEN_SLOT_DATA_OFFSET 1048576ULL
#define ELDEN_BUNDLE_MAX_BYTES (256ULL*1048576)
struct elden_bundle {
    uint64_t generation, bytes, span, offset;
    uint32_t slot;
    uint8_t sha256[32];
};
int elden_bundle_header(const uint8_t *header,uint64_t partition_bytes,
                        unsigned slot,struct elden_bundle *out);
void elden_bundle_sha256(const void *buffer,size_t bytes,uint8_t digest[32]);
int elden_bundle_verify(const struct elden_bundle *bundle,const void *buffer,size_t bytes);
enum elden_bundle_result {
    ELDEN_BUNDLE_OK=0, ELDEN_BUNDLE_ARGUMENT=-1, ELDEN_BUNDLE_NOT_FOUND=-2,
    ELDEN_BUNDLE_AMBIGUOUS=-3, ELDEN_BUNDLE_MEMORY=-4, ELDEN_BUNDLE_IO=-5,
    ELDEN_BUNDLE_DIGEST=-6
};
struct elden_bundle_reader {
    void *context;
    int (*read)(void *context,uint64_t offset,size_t bytes,void *buffer);
    void *(*allocate)(void *context,size_t bytes);
    void (*free)(void *context,void *buffer);
};
int elden_bundle_load(const struct elden_bundle_reader *reader,uint64_t partition_bytes,
                      int previous,struct elden_bundle *selected,void **buffer);
