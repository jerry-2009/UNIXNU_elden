/* SPDX-License-Identifier: BSD-3-Clause-Clear */
/* Optional bounded power-state contrast, on the retained wireless worker.
 * Keep the real MHI wake reference through command consumption; release before
 * ordinary stop/power-down. A failed get never owns a put. No credits/CE writes.
 */
extern int elden_wifi_mhi_hold_requested(void);
static struct mhi_device *elden_mhi_lease;
static struct ath12k_base *elden_mhi_lease_owner;
static int elden_mhi_lease_get(struct ath12k_base *ab)
{
    struct ath12k_pci *pci;
    struct mhi_device *device;
    int ret;
    if (!elden_wifi_mhi_hold_requested()) return 0;
    if (!ab || ab->hw_rev != ATH12K_HW_PEACH_HW20) return -ENODEV;
    pci = ath12k_pci_priv(ab);
    if (!pci || !pci->mhi_ctrl || !pci->mhi_ctrl->mhi_dev) return -ENODEV;
    device = pci->mhi_ctrl->mhi_dev;
    if (elden_mhi_lease)
        return elden_mhi_lease_owner == ab && elden_mhi_lease == device ? 0 : -EBUSY;
    ret = mhi_device_get_sync(device);
    if (!ret) {
        elden_mhi_lease = device;
        elden_mhi_lease_owner = ab;
    }
    ath12k_warn(ab, "ELDEN_MHI_LEASE get=%d held=%u; native bounded option\n",
                ret, elden_mhi_lease != NULL);
    return ret;
}
static void elden_mhi_lease_put(struct ath12k_base *ab)
{
    struct mhi_device *device;
    if (!elden_mhi_lease || elden_mhi_lease_owner != ab) return;
    device = elden_mhi_lease;
    elden_mhi_lease = NULL;
    elden_mhi_lease_owner = NULL;
    mhi_device_put(device);
    ath12k_warn(ab, "ELDEN_MHI_LEASE put=1 held=0\n");
}
