// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
#include <stdint.h>
// Fresh, read-only validation of inherited SMMUv2 identity DMA. No table walks
// or register writes. Fail closed instead of changing a foreign context bank.
struct EldenUfsIdentity {
  const char *error;
  uint32_t id1, id2, slot, bank, smr, s2cr, cbar, cba2r, sctlr;
};
template <typename Read>
static EldenUfsIdentity eldenUfsIdentity(uint16_t sid, uint64_t dma, uint64_t bytes, Read read)
{
  EldenUfsIdentity p = { "SMMU identity not proven", 0, 0, 0, 0, 0, 0, 0, 0, 0 };
  const uint32_t cr0 = read(0), id0 = read(0x20);
  p.id1 = read(0x24); p.id2 = read(0x28);
  const uint32_t streams = id0 & 255, banks = p.id1 & 255;
  const uint32_t stage2 = (p.id1 >> 16) & 255;
  const uint32_t pages = 1U << (((p.id1 >> 28) & 7) + 1);
  if ((cr0 & 9) || (id0 & 0x48000000U) != 0x48000000U || !(p.id2 & 0x1000) ||
      (p.id1 & 0x80000000U) || !streams || streams > 255 || !banks ||
      banks > pages || stage2 > banks || pages*8192U > 0x100000U) return p;
  const uint32_t widths[] = { 32, 36, 40, 42, 44, 48 };
  const unsigned ias = p.id2 & 15, oas = (p.id2 >> 4) & 15;
  if (ias > 5 || oas > 5 || !dma || !bytes || dma+bytes < dma ||
      dma+bytes > (1ULL << widths[ias]) || dma+bytes > (1ULL << widths[oas])) return p;
  unsigned matches = 0;
  for (unsigned i = 0; i < streams; ++i) {
    const uint32_t smr = read(0x800+4*i);
    if (!(smr & 0x80000000U)) continue;
    const uint32_t mask = (smr >> 16) & 0x7fff;
    if (((smr ^ sid) & 0xffff & ~mask) != 0) continue;
    ++matches; p.slot = i; p.smr = smr;
  }
  if (matches != 1 || (p.smr & 0xffff) != sid || ((p.smr >> 16) & 0x7fff)) return p;
  p.s2cr = read(0xc00+4*p.slot);
  const unsigned type = (p.s2cr >> 16) & 3;
  if (type == 1) { p.error = nullptr; return p; }
  if (type != 0) return p;
  p.bank = p.s2cr & 255;
  if (p.bank >= banks || p.bank < stage2) return p;
  p.cbar = read(0x1000+4*p.bank);
  p.cba2r = read(0x1800+4*p.bank);
  p.sctlr = read((pages+p.bank)*4096);
  if (((p.cbar >> 16) & 3) != 1 || !(p.cba2r & 1) || (p.sctlr & 1)) return p;
  p.error = nullptr;
  return p;
}
