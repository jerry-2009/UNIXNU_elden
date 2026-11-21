/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    uint32_t slot,bank,smr,s2cr,cbar,cba2r;
} EldenSmmuBootRoute;
enum {EldenSmmuBootOpen,EldenSmmuBootPreparing,EldenSmmuBootReady,
      EldenSmmuBootSealedEmpty,EldenSmmuBootSealedReady,EldenSmmuBootPoisoned};
/* One early provider, before UFS/Data publication permits touch DMA startup.
 * Reserve AFTER real baseline/ownership preflight and BEFORE the first SMMU
 * write. The registry is bookkeeping, not MMIO/lease/table/fault-handler proof.
 * The provider must own its bank/tables and keep WLAN physically quiesced. */
int elden_smmu_boot_route_reserve(const void *provider,const EldenSmmuBootRoute *);
/* observed must contain actual post-program register reads; caller must also
 * verify the context/table/translation state, not copy the intended values.
 * Failed programming/readback must poison; no retry or late replacement. */
int elden_smmu_boot_route_commit(const void *provider,const EldenSmmuBootRoute *observed);
int elden_smmu_boot_route_poison(const void *provider);
/* Called before the first touch snapshot. Empty/ready seal permanently. An
 * in-progress provider refuses: startup ordering must ensure it is terminal.
 * The published mapping then stays unchanged, including through stopping,
 * until platform reset; no DMA/power claim follows from registry membership. */
int elden_smmu_boot_route_seal(void);
int elden_smmu_boot_route_expected(uint32_t offset,uint32_t baseline,uint32_t *expected);
unsigned elden_smmu_boot_route_state(void);
#ifdef __cplusplus
}
#endif
