/* SPDX-License-Identifier: GPL-2.0-only */
int pci_alloc_irq_vectors(struct pci_dev *d, unsigned int min, unsigned int max, unsigned int flags) {
  if (!d || !nw_board || !nw_board->cfg_read || !nw_board->cfg_write || !nw_board->msi_target || !min || min > max)
    return -EINVAL;
  if (!(flags & PCI_IRQ_MSI)) return -ENOSPC;
  if (d->nvec || d->msi_enabled) return -EBUSY;
  unsigned raw_cap = nw_board->msi_cap;
  if (raw_cap < 0x40 || raw_cap > 0xfc || (raw_cap & 3) || nw_board->irq_base < 0 || nw_board->irq_base > 0x7fffffe0) return -EINVAL;
  int cap = (int)raw_cap;
  u32 old_ctl = 0, ctl = 0, check = 0, lo = 0, hi = 0, data = 0, old_mask = 0;
  int rc = nw_board->cfg_read(cap, 4, &old_ctl);
  if (rc) return rc;
  if ((old_ctl & 0xff) != 5 || ((old_ctl >> 17) & 7) > 5) return -EINVAL;
  if (old_ctl & (1u << 16)) return -EBUSY;
  unsigned limit = 1u << ((old_ctl >> 17) & 7), n = 1, mme = 0;
  if (limit > max) limit = max;
  if (limit > 32) limit = 32;
  while (n <= limit / 2) { n <<= 1; ++mme; }
  if (n < min) return -ENOSPC;
  unsigned char wide = (unsigned char)((old_ctl >> 23) & 1);
  int masked = (old_ctl >> 24) & 1;
  int data_off = cap + (wide ? 12 : 8), mask_off = data_off + 4;
  if (data_off > 0xfc || (masked && mask_off > 0xfc)) return -EINVAL;
  rc = nw_board->msi_target(&lo, &hi, &data);
  if (rc) return rc;
  if ((!lo && !hi) || (lo & 3) || (!wide && hi) || data > 0xffffu - (n - 1) || (data & (n - 1))) return -ERANGE;
  if (masked && (rc = nw_board->cfg_read(mask_off, 4, &old_mask))) return rc;
  /* Nothing is published until the actual endpoint configuration reads back.
   * The board receiver/IRQ and DMA lifetime must already be owned. */
  if ((rc = nw_board->cfg_write(cap + 4, 4, lo))) goto fail;
  if (wide && (rc = nw_board->cfg_write(cap + 8, 4, hi))) goto fail;
  if ((rc = nw_board->cfg_write(data_off, 2, data))) goto fail;
  u32 wanted_mask = old_mask & ~(n == 32 ? ~0u : (1u << n) - 1);
  if (masked && (rc = nw_board->cfg_write(mask_off, 4, wanted_mask))) goto fail;
  ctl = (old_ctl & ~0x00710000u) | (mme << 20) | (1u << 16);
  if ((rc = nw_board->cfg_write(cap, 4, ctl))) goto fail;
  if ((rc = nw_board->cfg_read(cap, 4, &check))) goto fail;
  if (check != ctl) { rc = -EIO; goto fail; }
  if ((rc = nw_board->cfg_read(cap + 4, 4, &check))) goto fail;
  if (check != lo) { rc = -EIO; goto fail; }
  if (wide) {
    if ((rc = nw_board->cfg_read(cap + 8, 4, &check))) goto fail;
    if (check != hi) { rc = -EIO; goto fail; }
  }
  if ((rc = nw_board->cfg_read(data_off, 2, &check))) goto fail;
  if (check != data) { rc = -EIO; goto fail; }
  if (masked) {
    if ((rc = nw_board->cfg_read(mask_off, 4, &check))) goto fail;
    if (check != wanted_mask) { rc = -EIO; goto fail; }
  }
  for (unsigned i = 0; i < n; i++) {
    g_msi[i].msg.address_lo = lo; g_msi[i].msg.address_hi = hi; g_msi[i].msg.data = data + i;
    g_msi[i].pci.msi_attrib.is_64 = wide;
  }
  d->nvec = n; d->msi_enabled = 1; d->irq = (u32)nw_board->irq_base; return (int)n;
fail:
  /* Best-effort disable is not a restoration/drain claim. The nonzero error
   * must reach the board worker, which retains resources and verifies reset. */
  (void)nw_board->cfg_write(cap, 4, old_ctl & ~(1u << 16));
  return rc;
}
void pci_free_irq_vectors(struct pci_dev *d) {
  if (!d || !d->msi_enabled) return;
  if (!nw_board || !nw_board->cfg_read || !nw_board->cfg_write || nw_board->msi_cap < 0x40 || nw_board->msi_cap > 0xfc || (nw_board->msi_cap & 3)) {
    lx_log(3, "pci: MSI disable failed: %d; retained until board reset", -EINVAL); return;
  }
  int cap = (int)nw_board->msi_cap;
  u32 ctl = 0, check = 0; int rc = nw_board->cfg_read(cap, 4, &ctl);
  if (!rc && (ctl & 0xff) != 5) rc = -EIO;
  if (!rc) rc = nw_board->cfg_write(cap, 4, ctl & ~(1u << 16));
  if (!rc) rc = nw_board->cfg_read(cap, 4, &check);
  if (!rc && check != (ctl & ~(1u << 16))) rc = -EIO;
  if (rc) { lx_log(3, "pci: MSI disable failed: %d; retained until board reset", rc); return; }
  d->nvec = 0; d->msi_enabled = 0;
}
