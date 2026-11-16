"""Add the registered PCI shutdown path; preserve remove and failed-start cleanup."""
from PciLifecyclePatch import patch as lifecycle
from InitTracePatch import patch as initialization

PCI='''
/* Platform shutdown retains the driver and buffers until native reset. */
static int elden_shutdown_started,elden_shutdown_result=-EINPROGRESS;
int elden_nw_pci_platform_shutdown(void) {
  if (elden_shutdown_started) return elden_shutdown_result;
  if (!g_drv || !g_drv->shutdown || !pci_get_drvdata(&g_dev)) return -ENODEV;
  elden_shutdown_started=1;
  lx_log(3,"ELDEN_PCI_PLATFORM callback enter");
  g_drv->shutdown(&g_dev);
  lx_log(3,"ELDEN_PCI_PLATFORM callback returned");
  elden_shutdown_result=elden_wifi_runtime_unbind(&g_dev.dev);
  lx_log(3,"ELDEN_PCI_PLATFORM unbind=%d",elden_shutdown_result);
  return elden_shutdown_result;
}
'''
WIFI='''
/* This is Linux's platform-shutdown lifecycle, not module removal. The native
 * owner independently proves hardware reset/drain before releasing power. */
static int elden_platform_started,elden_platform_result=-EINPROGRESS;
int nw_wifi_platform_shutdown(void) {
  if (elden_platform_started) return elden_platform_result;
  if (!pci_started) return -ENODEV;
  elden_platform_started=1;
  nw_mainline_shutdown();
  nw_wifi_control_shutdown();
  elden_platform_result=elden_nw_pci_platform_shutdown();
  return elden_platform_result;
}
'''
def patch(name,data):
    if name=='nw_pci.c':base=lifecycle(data);extra=PCI
    elif name=='nw_wifi.c':base=initialization(name,data);extra=WIFI
    else:raise ValueError('Unknown platform shutdown unit')
    return b'#include "PlatformShutdownApi.h"\n'+base+extra.encode()
