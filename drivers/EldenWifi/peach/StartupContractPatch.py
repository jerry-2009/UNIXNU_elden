"""Report the parsed firmware init result and existing MHI wake operations.

The transformation is observation only. It preserves every original call and
write; no wake, ring, firmware, credit, timeout or power behavior is changed.
"""
import hashlib

EXPECTED = {
    "core.c": "7c25574bd98e89313b62c6abe2a0ef1b059455beaea7d0013b9b66065578d531",
    "pci.c": "d50605c5a03a0c5b2b8b949a2ebc02c3329cd7e683746f47d8765eeb38acb84c",
}

INIT_REPORT = r'''
static void elden_wifi_init_contract(struct ath12k_base *ab, int wait_rc)
{
    if (!ab || ab->hw_rev != ATH12K_HW_PEACH_HW20) return;
    u32 status = ab->wlan_init_status;
    ath12k_warn(ab, "ELDEN_FW_INIT wait=%d ready=%u status=%x reason=%u module=%u preferred=%u radios=%u physical-pdevs=%u; parsed-fields-only\n",
        wait_rc, ab->wmi_ready, status, status & 0xffffU, status >> 16,
        ab->wmi_ab.preferred_hw_mode, ab->num_radios, ab->fw_pdev_count);
}
'''


def patch(name, data):
    if hashlib.sha256(data).hexdigest() != EXPECTED.get(name):
        raise ValueError("Exact startup-contract parent changed: " + name)
    original = text = data.decode()
    changes = []

    def replace(before, after):
        nonlocal text
        if text.count(before) != 1:
            raise ValueError("Startup-contract anchor changed: " + before[:90])
        text = text.replace(before, after, 1)
        changes.append((before, after))

    if name == "core.c":
        marker = '#include "Ce3Timeline.inc"'
        replace(marker, marker + "\n" + INIT_REPORT)
        marker = "\telden_ce3_timeline(ab,6, ret);"
        replace(marker, marker + "\n\telden_wifi_init_contract(ab, ret);")
    else:
        marker = "    off=(u32)(at-base);"
        replace(marker, marker + r'''
    /* Existing MHI wake doorbell writes, including the high word, share the
     * original MMIO callback. Record only the actual owned controller pair. */
    struct ath12k_pci *pci = ath12k_pci_priv(ab);
    struct mhi_controller *mhi = pci ? pci->mhi_ctrl : NULL;
    unsigned long db = mhi ? (unsigned long)mhi->wake_db : 0;
    bool wake_db = mhi && mhi->regs == ab->mem &&
        mhi->reg_len == ab->mem_len && mhi->mhi_dev == elden_umac_device &&
        db >= base && ab->mem_len >= 8 && db - base <= ab->mem_len - 8 &&
        (at == db || at == db + 4);
''')
        marker = "       off!=0x86000U&&off!=0x86004U&&off!=0x86008U&&off!=0x86010U)return;"
        replace(marker, marker.replace(")return;", "&&!wake_db)return;"))
        marker = "    if(off>=0x86000U&&(window&0x3fU)!=0x37U)return;"
        replace(marker, marker.replace("if(off>=", "if(!wake_db&&off>="))
        marker = "static void elden_pci_state_read(struct ath12k_base *ab,u32 requested,u32 observed)"
        replace(marker, r'''
static u64 elden_wifi_bar_par(unsigned long address)
{
#ifdef ELDEN_STARTUP_HOST_TEST
    return elden_wifi_host_par(address);
#else
    u64 daif, saved, result;
    __asm__ volatile("mrs %0,daif\n\tmsr daifset,#2\n\tmrs %1,par_el1\n\tat s1e1r,%3\n\tisb\n\tmrs %2,par_el1\n\tmsr par_el1,%1\n\tmsr daif,%0"
        :"=&r"(daif),"=&r"(saved),"=&r"(result):"r"(address):"memory");
    return result;
#endif
}
''' + marker)
        marker = "    if(observed!=1U)elden_pci_state_dump(ab);"
        replace(marker, r'''
    ath12k_warn(ab,"ELDEN_MHI_WAKE sample=%u request=%x wake-set=%u refs=%d/%u db-off=%llx pm=%x state=%u ee=%u; software-state-and-existing-writes\n",
        elden_pci_state.states, observed, READ_ONCE(mhi->wake_set),
        atomic_read(&mhi->dev_wake), READ_ONCE(mhi->mhi_dev->dev_wake),
        (unsigned long long)(db>=base&&db-base<ab->mem_len?db-base:~0UL),
        READ_ONCE(mhi->pm_state), (unsigned)READ_ONCE(mhi->dev_state),
        (unsigned)READ_ONCE(mhi->ee));
    if(observed!=1U&&!elden_pci_state.dumped)
        ath12k_warn(ab,"ELDEN_BAR_MAP par-base=%llx par-wake=%llx par-ce3=%llx; CPU-translation-only\n",
            (unsigned long long)elden_wifi_bar_par(base),
            (unsigned long long)elden_wifi_bar_par(base+0x3004U),
            (unsigned long long)elden_wifi_bar_par(base+0x86000U));
''' + marker)
    restored = text
    for before, after in reversed(changes):
        if restored.count(after) != 1:
            raise ValueError("Startup-contract observation is not reversible")
        restored = restored.replace(after, before, 1)
    if restored != original:
        raise ValueError("Startup-contract changed original operations")
    return text.encode()
