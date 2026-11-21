/* SPDX-License-Identifier: BSD-3-Clause-Clear */
/* Peach's OEM force-wake has two independent steps: MHI M0, then UMAC.
 * This explicit, bounded trial holds both until the original PCI stop. The
 * address/status contract is verified against the loaded TB322FC module.
 */
extern int elden_wifi_umac_hold_requested(void);
#define ELDEN_UMAC_WAKE_OFFSET 0x3004U
#define ELDEN_UMAC_SCRATCH_OFFSET 0x01e04040U
#define ELDEN_UMAC_AWAKE 2U
#define ELDEN_UMAC_CHECKS 11U
#define ELDEN_UMAC_DELAY_US 5000U
static struct mhi_device *elden_umac_device;
static struct ath12k_base *elden_umac_owner;
static int elden_umac_wake_get(struct ath12k_base *ab)
{
    struct ath12k_pci *pci;
    struct mhi_device *device;
    u32 before, after = 0xffffffffU;
    unsigned checks;
    int ret;
    if (!elden_wifi_umac_hold_requested()) return 0;
    if (!ab || ab->hw_rev != ATH12K_HW_PEACH_HW20 || !ab->mem ||
        ab->mem_len < WINDOW_START +
            (ELDEN_UMAC_SCRATCH_OFFSET & WINDOW_RANGE_MASK) + sizeof(u32))
        return -ENODEV;
    pci = ath12k_pci_priv(ab);
    if (!pci || !pci->mhi_ctrl || !pci->mhi_ctrl->mhi_dev) return -ENODEV;
    device = pci->mhi_ctrl->mhi_dev;
    if (elden_umac_device)
        return elden_umac_owner == ab && elden_umac_device == device ? 0 : -EBUSY;
    ret = mhi_device_get_sync(device);
    if (ret) {
        ath12k_warn(ab, "ELDEN_UMAC_WAKE mhi-get=%d held=0\n", ret);
        return ret;
    }
    /* Existing PCI accessors perform the normal dynamic-window selection.
     * The MHI reference alone does not establish UMAC readiness. */
    before = ath12k_pci_read32(ab, ELDEN_UMAC_SCRATCH_OFFSET);
    ath12k_pci_write32(ab, ELDEN_UMAC_WAKE_OFFSET, 1);
    for (checks = 0; checks < ELDEN_UMAC_CHECKS; checks++) {
        after = ath12k_pci_read32(ab, ELDEN_UMAC_SCRATCH_OFFSET);
        if (after == ELDEN_UMAC_AWAKE || after == 0xffffffffU) break;
        if (checks + 1 < ELDEN_UMAC_CHECKS) udelay(ELDEN_UMAC_DELAY_US);
    }
    ret = after == ELDEN_UMAC_AWAKE ? 0 :
        after == 0xffffffffU ? -EIO : -ETIMEDOUT;
    if (!ret) {
        elden_umac_device = device;
        elden_umac_owner = ab;
    } else {
        /* Undo only this trial's request before dropping its real reference. */
        ath12k_pci_write32(ab, ELDEN_UMAC_WAKE_OFFSET, 0);
        mhi_device_put(device);
    }
    ath12k_warn(ab, "ELDEN_UMAC_WAKE get=%d held=%u before=%x after=%x checks=%u\n",
                ret, elden_umac_device != NULL, before, after,
                checks < ELDEN_UMAC_CHECKS ? checks + 1 : ELDEN_UMAC_CHECKS);
    return ret;
}
static void elden_umac_wake_put(struct ath12k_base *ab)
{
    struct mhi_device *device;
    if (!elden_umac_device || elden_umac_owner != ab) return;
    device = elden_umac_device;
    elden_umac_device = NULL;
    elden_umac_owner = NULL;
    ath12k_pci_write32(ab, ELDEN_UMAC_WAKE_OFFSET, 0);
    mhi_device_put(device);
    ath12k_warn(ab, "ELDEN_UMAC_WAKE put=1 held=0\n");
}
