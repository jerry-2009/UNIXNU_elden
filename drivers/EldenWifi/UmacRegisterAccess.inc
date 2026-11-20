/* SPDX-License-Identifier: BSD-3-Clause-Clear */
/* OEM d50b305f HAL/HIF: MHI get, reference-counted UMAC request, access,
 * final UMAC clear, MHI put. Raw accessors avoid recursive force-wake. */
extern int elden_wifi_umac_hold_requested(void);
#define ELDEN_UMAC_WAKE_OFFSET 0x3004U
#define ELDEN_UMAC_SCRATCH_OFFSET 0x01e04040U
#define ELDEN_UMAC_AWAKE 2U
#define ELDEN_UMAC_CHECKS 11U
#define ELDEN_UMAC_DELAY_US 5000U
static struct mhi_device *elden_umac_device;
static struct ath12k_base *elden_umac_owner;
static spinlock_t elden_umac_access_lock;
static unsigned elden_umac_access_refs, elden_umac_access_notes;
static int elden_umac_access_fault;
static bool elden_umac_access_enabled;

static int elden_umac_wake_get(struct ath12k_base *ab)
{
    struct ath12k_pci *pci;
    if (!elden_wifi_umac_hold_requested()) return 0;
    if (!ab || ab->hw_rev != ATH12K_HW_PEACH_HW20 || !ab->mem ||
        ab->mem_len < WINDOW_START +
            (ELDEN_UMAC_SCRATCH_OFFSET & WINDOW_RANGE_MASK) + sizeof(u32))
        return -ENODEV;
    pci = ath12k_pci_priv(ab);
    if (!pci || !pci->mhi_ctrl || !pci->mhi_ctrl->mhi_dev) return -ENODEV;
    if (elden_umac_owner) return -EBUSY;
    spin_lock_init(&elden_umac_access_lock);
    elden_umac_owner = ab;
    elden_umac_device = pci->mhi_ctrl->mhi_dev;
    elden_umac_access_enabled = true;
    ath12k_warn(ab, "ELDEN_UMAC_REG bound=1 startup-hold=0 threshold=fe0 checks=11\n");
    return 0;
}

static int elden_umac_register_begin(struct ath12k_base *ab, u32 offset, bool *taken)
{
    struct ath12k_pci *pci;
    unsigned checks = 0;
    u32 after = 0xffffffffU;
    int ret;
    *taken = false;
    if (!elden_umac_access_enabled || ab->hw_rev != ATH12K_HW_PEACH_HW20 ||
        offset < ACCESS_ALWAYS_OFF ||
        !test_bit(ATH12K_PCI_FLAG_INIT_DONE, &ath12k_pci_priv(ab)->flags))
        return 0;
    pci = ath12k_pci_priv(ab);
    if (ab != elden_umac_owner || !pci || !pci->mhi_ctrl ||
        pci->mhi_ctrl->mhi_dev != elden_umac_device || !elden_umac_device)
        return -ENODEV;
    ret = READ_ONCE(elden_umac_access_fault);
    if (ret) return ret;
    /* The original MHI runtime has its own PM locks. Never call it with the
     * UMAC lock held, and never balance a failed get with an extra put. */
    ret = mhi_device_get_sync(elden_umac_device);
    if (ret) return ret;
    spin_lock_bh(&elden_umac_access_lock);
    ret = elden_umac_access_fault;
    if (!ret && elden_umac_access_refs == ~0U) ret = -EOVERFLOW;
    if (!ret && !elden_umac_access_refs) {
        elden_pci_write32_raw(ab, ELDEN_UMAC_WAKE_OFFSET, 1);
        for (checks = 0; checks < ELDEN_UMAC_CHECKS; checks++) {
            after = elden_pci_read32_raw(ab, ELDEN_UMAC_SCRATCH_OFFSET);
            if (after == ELDEN_UMAC_AWAKE || after == 0xffffffffU) break;
            if (checks + 1 < ELDEN_UMAC_CHECKS) udelay(ELDEN_UMAC_DELAY_US);
        }
        ret = after == ELDEN_UMAC_AWAKE ? 0 :
              after == 0xffffffffU ? -EIO : -ETIMEDOUT;
        if (ret) {
            elden_pci_write32_raw(ab, ELDEN_UMAC_WAKE_OFFSET, 0);
            /* A failed hardware handshake is terminal for this binding.
             * Retain the provider, do not repeat polls on every failed read. */
            elden_umac_access_fault = ret;
        }
    }
    if (!ret) {
        elden_umac_access_refs++;
        *taken = true;
    }
    spin_unlock_bh(&elden_umac_access_lock);
    if (ret) mhi_device_put(elden_umac_device);
    if (ret || elden_umac_access_notes++ < 8)
        ath12k_warn(ab, "ELDEN_UMAC_REG begin=%d offset=%x scratch=%x checks=%u refs=%u\n",
                    ret, offset, after, checks < ELDEN_UMAC_CHECKS ? checks + 1 : checks,
                    elden_umac_access_refs);
    return ret;
}

static void elden_umac_register_end(struct ath12k_base *ab, bool taken)
{
    if (!taken) return;
    if (ab != elden_umac_owner || !elden_umac_device) {
        ath12k_warn(ab, "ELDEN_UMAC_REG release-refused owner-changed=1\n");
        return;
    }
    spin_lock_bh(&elden_umac_access_lock);
    if (!elden_umac_access_refs) {
        elden_umac_access_fault = -EPROTO;
        spin_unlock_bh(&elden_umac_access_lock);
        return;
    }
    if (!--elden_umac_access_refs)
        elden_pci_write32_raw(ab, ELDEN_UMAC_WAKE_OFFSET, 0);
    spin_unlock_bh(&elden_umac_access_lock);
    mhi_device_put(elden_umac_device);
}

static void elden_umac_wake_put(struct ath12k_base *ab)
{
    if (ab != elden_umac_owner || !elden_umac_device) return;
    if (READ_ONCE(elden_umac_access_refs)) {
        ath12k_warn(ab, "ELDEN_UMAC_REG unbind-refused refs=%u\n", elden_umac_access_refs);
        return;
    }
    ath12k_warn(ab, "ELDEN_UMAC_REG unbound=1 refs=0 fault=%d no-startup-ref=1\n",
                elden_umac_access_fault);
    elden_umac_access_enabled = false;
    elden_umac_owner = NULL;
    elden_umac_device = NULL;
}
