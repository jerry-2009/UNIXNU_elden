// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
#include <stdint.h>
struct EldenUfsPrdtEntry { uint64_t address;uint32_t bytes;uint32_t reserved; };
struct EldenUfsPrdtPlan { uint32_t count,bytes;EldenUfsPrdtEntry entries[64]; };
using EldenUfsPageAddress=uint64_t(*)(void*,uint64_t pageOffset);
extern "C" {
// Only after existing eldenUfsIdentity succeeds: tighten to ALL three SMMU
// widths and host addressing. Unknown widths refuse; never reprogram SMMU.
uint64_t elden_ufs_dma_limit(uint32_t idr2,bool host64,bool identityVerified);
// The native caller MUST retain/pin a driver-owned allocation until completion;
// this planner alone does not pin pages or establish device ownership. The page
// callback reports physical addresses without consulting an IOVA mapper.
// Failure leaves output unchanged; fallback copies may then use an owned slot.
bool elden_ufs_prdt_build(uintptr_t alignedVirtual,uint64_t bytes,uint64_t allocationBytes,
                          uint64_t dmaLimit,EldenUfsPageAddress,void*,EldenUfsPrdtPlan*);
}
