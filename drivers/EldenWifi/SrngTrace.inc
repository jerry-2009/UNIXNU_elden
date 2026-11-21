/* SPDX-License-Identifier: BSD-3-Clause-Clear */
/* Included only in the hash-bound common HAL unit. No producer/credit writes. */
#include "wifi7/hal.h"
#include "SrngTrace.h"
#if defined(ELDEN_SRNG_PCI_WINDOW) && ELDEN_SRNG_PCI_WINDOW
#define ESN_READ(ab,off) elden_wifi_pci_diag_read((ab),(off))
#else
#define ESN_READ(ab,off) ath12k_hif_read32((ab),(off))
#endif
struct esn_record { u64 enter, exit, timer, hp, offset; };
static struct esn_record esn_records[HAL_SRNG_RING_ID_MAX];
static unsigned esn_captured;
static void esn_enter(struct ath12k_base *ab, struct hal_srng *srng)
{
    unsigned id = srng->ring_id;
    if (id >= HAL_SRNG_RING_ID_MAX) return;
    __atomic_store_n(&esn_records[id].hp, srng->u.src_ring.hp, __ATOMIC_RELAXED);
    __atomic_store_n(&esn_records[id].offset,
                     (unsigned long)srng->u.src_ring.hp_addr - (unsigned long)ab->mem,
                     __ATOMIC_RELAXED);
    __atomic_add_fetch(&esn_records[id].enter, 1, __ATOMIC_RELAXED);
}
static void esn_exit(struct hal_srng *srng)
{
    if (srng->ring_id < HAL_SRNG_RING_ID_MAX)
        __atomic_add_fetch(&esn_records[srng->ring_id].exit, 1, __ATOMIC_RELAXED);
}
static void esn_timer(struct hal_srng *srng)
{
    if (srng->ring_id < HAL_SRNG_RING_ID_MAX)
        __atomic_add_fetch(&esn_records[srng->ring_id].timer, 1, __ATOMIC_RELAXED);
}
void elden_wifi_srng_first_wmi(struct ath12k_base *ab)
{
    struct hal_srng *srng;
    struct esn_record *counts;
    unsigned id, n;
    int config_count;
    u32 direct, shadow, hw_hp, hw_tp, target = 0xffffffffU;
    int index = -1;
    if (!ab) return;
    if (__atomic_exchange_n(&esn_captured, 1, __ATOMIC_ACQ_REL)) return;
    if (!ab->mem || !ab->hw_params || ab->hw_params->ce_count <= 3 ||
        !ab->ce.ce_pipe[3].src_ring) {
        ath12k_warn(ab, "ELDEN_SRNG refused ce3 source unavailable\n");
        return;
    }
    id = ab->ce.ce_pipe[3].src_ring->hal_ring_id;
    if (id >= HAL_SRNG_RING_ID_MAX) {
        ath12k_warn(ab, "ELDEN_SRNG refused ring id %u\n", id);
        return;
    }
    srng = &ab->hal.srng_list[id];
    config_count = ab->hal.num_shadow_reg_configured;
    if (!srng->initialized || srng->ring_dir != HAL_SRNG_DIR_SRC ||
        (srng->flags & HAL_SRNG_FLAGS_LMAC_RING) || !srng->ring_size ||
        config_count < 0 || config_count > HAL_SHADOW_NUM_REGS_MAX || !srng->u.src_ring.hp_addr || !srng->u.src_ring.tp_addr ||
        (unsigned long)srng->u.src_ring.hp_addr < (unsigned long)ab->mem ||
        (unsigned long)srng->u.src_ring.hp_addr - (unsigned long)ab->mem > 0xffffffffUL) {
        ath12k_warn(ab, "ELDEN_SRNG refused ce3 geometry/context\n");
        return;
    }
    n = (unsigned)config_count;
    direct = srng->hwreg_base[HAL_SRNG_REG_GRP_R2];
    shadow = (u32)((unsigned long)srng->u.src_ring.hp_addr - (unsigned long)ab->mem);
    if ((direct & 3) || direct > 0xffffffffU - HAL_OFFSET_FROM_HP_TO_TP) {
        ath12k_warn(ab, "ELDEN_SRNG refused direct register range\n");
        return;
    }
    for (unsigned i = 0; i < n; i++) {
        if (HAL_SHADOW_REG(i) == shadow) {
            index = (int)i; target = ab->hal.shadow_reg_addr[i]; break;
        }
    }
    counts = &esn_records[id];
    /* Read the documented real HP/TP only. Shadow registers may be write-only;
     * their last software notification is observed above, never read here.
     * HIF may perform its existing window selection/wakeup for these accesses. */
    hw_hp = ESN_READ(ab, direct);
    hw_tp = ESN_READ(ab, direct + HAL_OFFSET_FROM_HP_TO_TP);
    ath12k_warn(ab, "ELDEN_SRNG CFG ce=3 id=%u flags=%x shadow=%u idx=%d off=%x target=%x direct=%x maps=%u\n",
                id, srng->flags, ab->hw_params->supports_shadow_regs,
                index, shadow, target, direct, n);
    ath12k_warn(ab, "ELDEN_SRNG HP sw=%u last=%llu enter=%llu exit=%llu timer=%llu lastoff=%llx hw=%x/%x dma-tp=%u\n",
                srng->u.src_ring.hp,
                (unsigned long long)__atomic_load_n(&counts->hp, __ATOMIC_RELAXED),
                (unsigned long long)__atomic_load_n(&counts->enter, __ATOMIC_RELAXED),
                (unsigned long long)__atomic_load_n(&counts->exit, __ATOMIC_RELAXED),
                (unsigned long long)__atomic_load_n(&counts->timer, __ATOMIC_RELAXED),
                (unsigned long long)__atomic_load_n(&counts->offset, __ATOMIC_RELAXED),
                hw_hp, hw_tp, READ_ONCE(*srng->u.src_ring.tp_addr));
}
