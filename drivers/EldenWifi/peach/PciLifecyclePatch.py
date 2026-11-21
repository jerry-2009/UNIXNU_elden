"""Bind the actual Linux device and enable BM only through the native owner."""
from PciMsiPatch import patch as msi_patch
def patch(data):
    text=msi_patch(data).decode()
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('PCI lifecycle anchor changed: '+old[:80])
        text=text.replace(old,new,1)
    replace('const struct nw_board *nw_board;', '''extern int elden_wifi_runtime_bind(void *consumer);
extern int elden_wifi_runtime_unbind(void *consumer);
extern int elden_wifi_runtime_enable_master(void);
const struct nw_board *nw_board;''')
    replace('  for (unsigned i = 0; i < n; i++) {',
            '  if ((rc = elden_wifi_runtime_enable_master())) goto fail;\n  for (unsigned i = 0; i < n; i++) {')
    replace('  { u32 sub = 0; if (!nw_board->cfg_read(0x2c, 4, &sub)) { g_dev.subsystem_vendor = sub & 0xffff; g_dev.subsystem_device = sub >> 16; } }',
            '  { u32 sub = 0; int rc = nw_board->cfg_read(0x2c, 4, &sub); if (rc) { g_drv = 0; return rc; } g_dev.subsystem_vendor = sub & 0xffff; g_dev.subsystem_device = sub >> 16; }')
    replace('  { u32 ctl = 0; if (!nw_board->cfg_read(0x80000008, 2, &ctl)) { nw_board->cfg_write(0x80000008, 2, ctl & ~0x7000u); nw_board->cfg_read(0x80000008, 2, &sub_ctl_after); lx_log(6, "pci: device control %04x -> %04x", ctl, sub_ctl_after); } }', '''  { u32 ctl = 0; int rc = nw_board->cfg_read(0x80000008, 2, &ctl);
    if (!rc) rc = nw_board->cfg_write(0x80000008, 2, ctl & ~0x7000u);
    if (!rc) rc = nw_board->cfg_read(0x80000008, 2, &sub_ctl_after);
    if (!rc && sub_ctl_after != (ctl & ~0x7000u)) rc = -EIO;
    if (rc) { g_drv = 0; return rc; }
    lx_log(6, "pci: device control %04x -> %04x", ctl, sub_ctl_after); }''')
    replace('''  for (const struct pci_device_id *id = drv->id_table; id && id->vendor; id++)
    if (id->device == g_dev.device) return drv->probe(&g_dev, id);
  return -ENODEV; }''','''  for (const struct pci_device_id *id = drv->id_table; id && id->vendor; id++) {
    if (id->device != g_dev.device) continue;
    int rc = elden_wifi_runtime_bind(&g_dev.dev);
    if (rc) { g_drv = 0; return rc; }
    rc = drv->probe(&g_dev, id);
    if (rc) {
      int release = elden_wifi_runtime_unbind(&g_dev.dev);
      if (release) lx_log(3, "pci: consumer unbind after failed probe: %d", release);
      g_drv = 0;
    }
    return rc;
  }
  g_drv = 0; return -ENODEV; }''')
    replace('''void pci_unregister_driver(struct pci_driver *drv) { if (g_drv == drv) { drv->remove(&g_dev); g_drv = 0; } }''','''void pci_unregister_driver(struct pci_driver *drv) {
  if (g_drv != drv) return;
  drv->remove(&g_dev);
  int rc = elden_wifi_runtime_unbind(&g_dev.dev);
  if (rc) lx_log(3, "pci: consumer unbind after remove: %d", rc);
  g_drv = 0;
}''')
    return text.encode()
