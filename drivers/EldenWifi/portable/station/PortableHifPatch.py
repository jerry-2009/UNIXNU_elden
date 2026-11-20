"""Restore the missing HIF lifetime for the real portable station path.

The original ath12k_hif_start sets PCI INIT_DONE and binds the UMAC accessor;
the portable callback skipped it to avoid starting uninitialized Linux CE
rings. Restore just that owned lifetime with the donor's real MHI wake lease,
not the unrelated Linux CE producer/interrupt registration.
"""
from pathlib import Path
import hashlib
STA=Path(__file__).resolve().parent
EXPECTED={'core.c':'14f0464637b8bc914c75b5161eddb02bbe8b8521f4d7e93c1c1d14d24e09b14c',
          'pci.c':'d1262a8a9785decd5a05a2a6ae0576e29574c4baf94404e040abde2b74aec537'}
PCI='''
/* The portable transport polls its own CE rings; it must still establish
 * the same PCI/UMAC MHI lifetime that the original HIF start owns. */
extern int elden_wifi_station_requested(void);
static struct ath12k_base *elden_portable_hif_owner;
static struct mhi_device *elden_portable_hif_wake;
int elden_wifi_portable_hif_prepare(struct ath12k_base *ab)
{
    struct ath12k_pci *pci;
    int rc;
    if (!elden_wifi_station_requested() || !ab ||
        ab->hw_rev != ATH12K_HW_PEACH_HW20 || !ab->mem || ab->mem_len < 0x100000)
        return -ENODEV;
    pci = ath12k_pci_priv(ab);
    if (!pci || !pci->mhi_ctrl || !pci->mhi_ctrl->mhi_dev ||
        pci->mhi_ctrl->regs != ab->mem || pci->mhi_ctrl->ee != MHI_EE_AMSS ||
        elden_portable_hif_owner || test_bit(ATH12K_PCI_FLAG_INIT_DONE, &pci->flags))
        return -EBUSY;
    elden_portable_hif_owner = ab;
    set_bit(ATH12K_PCI_FLAG_INIT_DONE, &pci->flags);
    rc = elden_umac_wake_get(ab);
    if (rc) return rc;
    rc = mhi_device_get_sync(pci->mhi_ctrl->mhi_dev);
    if (rc) return rc;
    elden_portable_hif_wake = pci->mhi_ctrl->mhi_dev;
    ath12k_warn(ab, "ELDEN_STATION HIF prepared=1 init-done=1 umac=1 wake-lease=1; portable CE poll\\n");
    return 0;
}
'''
RELEASE='''    if (ab == elden_portable_hif_owner && elden_portable_hif_wake) {
        mhi_device_put(elden_portable_hif_wake);
        elden_portable_hif_wake = NULL;
        ath12k_warn(ab, "ELDEN_STATION HIF wake-release=1; protocol stop before physical fence\\n");
    }
'''

def patch(name,data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED.get(name):raise ValueError('HIF exact parent changed: '+name)
    original=text=data.decode();changes=[]
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('HIF lifetime anchor changed: '+old[:85])
        text=text.replace(old,new,1);changes.append((old,new))
    if name=='core.c':
        replace('#include "StationApi.h"','#include "StationApi.h"\nextern int elden_wifi_portable_hif_prepare(struct ath12k_base *);')
        replace('    elden_portable_cpu=lx_plat->dma_alloc(4u<<20,&elden_portable_bus);',
                '    rc=elden_wifi_portable_hif_prepare(ab);if(rc)goto fail;\n'
                '    elden_portable_cpu=lx_plat->dma_alloc(4u<<20,&elden_portable_bus);')
    elif name=='pci.c':
        replace('static void elden_umac_wake_put(struct ath12k_base *ab)\n{',
                PCI+'\nstatic void elden_umac_wake_put(struct ath12k_base *ab)\n{\n'+RELEASE)
    else:raise ValueError('Unknown HIF lifetime unit')
    restored=text
    for old,new in reversed(changes):restored=restored.replace(new,old,1)
    if restored!=original:raise ValueError('Unrelated HIF code changed')
    return text.encode()
