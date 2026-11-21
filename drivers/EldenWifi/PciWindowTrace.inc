/* SPDX-License-Identifier: BSD-3-Clause-Clear */
/* A diagnostic read uses the original HIF route, with bounded trace metadata. */
static unsigned epw_busy;
static u32 epw_requested;
static void epw_note(struct ath12k_base *ab, u32 request, u32 effective,
                     u32 window, int wake, u32 value)
{
    struct ath12k_pci *pci = ath12k_pci_priv(ab);
    u32 hardware = 0xffffffffU;
    unsigned readable = 0;
    if (__atomic_load_n(&epw_busy, __ATOMIC_ACQUIRE) != 1 || request != epw_requested)
        return;
    if (!(pci->window_reg_addr & 3) && pci->window_reg_addr < WINDOW_START) {
        hardware = ioread32(ab->mem + pci->window_reg_addr);
        readable = 1;
    }
    ath12k_warn(ab, "ELDEN_PCI_READ req=%x off=%x static=%u win=%x reg=%x cached=%x hw=%x read=%u wake=%d val=%x ce=%x dp=%x\n",
                request, effective, ab->static_window_map, window, pci->window_reg_addr,
                pci->register_window, hardware, readable, wake, value,
                pci->reg_base->ce_reg_base, pci->reg_base->umac_base);
}
u32 elden_wifi_pci_diag_read(struct ath12k_base *ab, u32 offset)
{
    u32 value;
    unsigned expected = 0;
    if (!__atomic_compare_exchange_n(&epw_busy, &expected, 2, 0,
                                      __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
        return ath12k_hif_read32(ab, offset);
    epw_requested = offset;
    __atomic_store_n(&epw_busy, 1, __ATOMIC_RELEASE);
    value = ath12k_hif_read32(ab, offset);
    __atomic_store_n(&epw_busy, 0, __ATOMIC_RELEASE);
    return value;
}
