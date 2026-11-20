/* SPDX-License-Identifier: BSD-3-Clause-Clear */
/* Two bounded raw observations. These do not request wake, reinitialize CE,
 * or read the read-clear WLAON reset-cause register. Dynamic window selection
 * is the existing raw accessor's only write. Values have no ready assertion. */
extern int elden_wifi_first_failure_physical(unsigned);
static unsigned elden_first_failure_seen;
void elden_wifi_first_failure_sample(struct ath12k_base *ab, u32 stage, int result)
{
    static const u32 offsets[] = {
        0x38, 0x48, 0x3004, 0x3008, 0x3278, 0x1b00000, 0x1e04040,
        0x1e081b0, 0x1f80000, 0x1f80004, 0x1f80008, 0x1f8000c,
        0x1f8002c, 0x1f80500, 0x1f80504, 0x1b86000, 0x1b86004,
        0x1b86008, 0x1b86010, 0x1b86400, 0x1b86404
    };
    struct ath12k_pci *pci;
    struct mhi_controller *mhi;
    unsigned bit, i;
    u32 values[21];
    if (stage != 12 && stage != 90) return;
    bit = stage == 12 ? 1U : 2U;
    if (!ab || ab != elden_umac_owner || !elden_umac_device ||
        !ab->mem || ab->mem_len < 0x100000) return;
    pci = ath12k_pci_priv(ab);
    mhi = pci ? pci->mhi_ctrl : NULL;
    if (!mhi || mhi->mhi_dev != elden_umac_device || mhi->regs != ab->mem ||
        mhi->reg_len != ab->mem_len) return;
    if (__atomic_fetch_or(&elden_first_failure_seen, bit, __ATOMIC_ACQ_REL) & bit)
        return;
    for (i = 0; i < sizeof(offsets) / sizeof(offsets[0]); i++)
        values[i] = elden_pci_read32_raw(ab, offsets[i]);
    ath12k_warn(ab, "ELDEN_FIRST_STATE stage=%u result=%d ms=%llu pm=%x state=%u ee=%u refs=%d/%u ready=%u init=%x umacrefs=%u fault=%d; raw-read-nonatomic no-wake\n",
                stage, result, (unsigned long long)jiffies_to_msecs(jiffies),
                READ_ONCE(mhi->pm_state), (unsigned)READ_ONCE(mhi->dev_state),
                (unsigned)READ_ONCE(mhi->ee), atomic_read(&mhi->dev_wake),
                READ_ONCE(mhi->mhi_dev->dev_wake), ab->wmi_ready,
                ab->wlan_init_status, elden_umac_access_refs, elden_umac_access_fault);
    for (i = 0; i < sizeof(offsets) / sizeof(offsets[0]); i += 3)
        ath12k_warn(ab, "ELDEN_FIRST_RAW stage=%u off=%x/%x/%x val=%x/%x/%x\n",
                    stage, offsets[i], offsets[i + 1], offsets[i + 2],
                    values[i], values[i + 1], values[i + 2]);
    int physical = elden_wifi_first_failure_physical(stage);
    ath12k_warn(ab, "ELDEN_FIRST_STATE stage=%u physical=%d; firmware/reset cause unproved\n",
                stage, physical);
}
