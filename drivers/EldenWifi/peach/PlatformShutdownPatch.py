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
static uint64_t elden_platform_deadline;
uint64_t elden_wifi_platform_deadline_ms(void) {return elden_platform_started?elden_platform_deadline:0;}
int nw_wifi_platform_shutdown(void) {
  if (elden_platform_started) return elden_platform_result;
  if (!pci_started) return -ENODEV;
  elden_platform_started=1;
  nw_mainline_shutdown();
  nw_wifi_control_shutdown();
  elden_platform_deadline=lx_now_ms()+2000;
  elden_platform_result=elden_nw_pci_platform_shutdown();
  return elden_platform_result;
}
'''
POLL='''
    /* Only an explicit platform reset gets this aggregate deadline. Ordinary
     * initialization and failure recovery retain the original controller timeout. */
    u64 deadline=elden_wifi_platform_deadline_ms();
    if (deadline) {
        if (!delayus) return -EINVAL;
        u64 limit=(2000000ULL+delayus-1)/delayus+1;
        for (u64 attempt=0;;attempt++) {
            u32 observed=0;
            int status=mhi_read_reg_field(mhi_cntrl,base,offset,mask,&observed);
            if (status || observed==val) {
                lx_log(3,"ELDEN_MHI_PLATFORM poll off=%x mask=%x want=%u got=%u rc=%d",offset,mask,val,observed,status);
                return status;
            }
            u64 now=lx_now_ms();
            if (now>=deadline || attempt>=limit) {
                lx_log(3,"ELDEN_MHI_PLATFORM timeout off=%x mask=%x want=%u got=%u",offset,mask,val,observed);
                return -ETIMEDOUT;
            }
            u64 left=(deadline-now)*1000;
            fsleep((u32)(left<delayus?left:delayus));
        }
    }
'''
def patch(name,data):
    if name=='nw_pci.c':base=lifecycle(data);extra=PCI
    elif name=='nw_wifi.c':base=initialization(name,data);extra=WIFI
    elif name=='main.c':
        original=data.decode();start=original.index('int __must_check mhi_poll_reg_field(')
        at=original.index('\n{',start)+2
        text=original[:at]+POLL+original[at:]
        if text.replace(POLL,'',1)!=original:raise ValueError('Original poll was changed')
        base=text.encode();extra=''
    else:raise ValueError('Unknown platform shutdown unit')
    return b'#include "PlatformShutdownApi.h"\n'+base+extra.encode()
