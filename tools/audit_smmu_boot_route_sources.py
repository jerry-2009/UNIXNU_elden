"""Bind coexistence and DMA prerequisites to fixed upstream and stock facts."""
import argparse,hashlib,json,re,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LINUX='6f97250ead155fc3b980856323e99a4623dae73d'
SMMU='83969cd874503e65997ff7639f7dcf3d0a92cd17'
SHENG='24aab96163799cb1db083d94539a5eefc07e0475'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['linux-repository','smmu-repository','sheng-repository','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--stock-fdt',type=Path);a=p.parse_args();inputs={}
    def source(repo,rev,path):
        data=subprocess.check_output(['git','-C',str(repo),'show',rev+':'+path]);inputs[rev+':'+path]=hashlib.sha256(data).hexdigest();return data.decode()
    context=source(a.smmu_repository,SMMU,'ArmSmmu4KContext.c')
    assert 'v.cbar=0x1f300;' in context and 'v.cba2r=1;' in context
    streams=source(a.smmu_repository,SMMU,'ArmSmmu4KStreams.c')
    assert 'unsigned slots=r->id0&255;' in streams and 'slot<slots' in streams
    pci=source(a.linux_repository,LINUX,'drivers/net/wireless/ath/ath12k/pci.c')
    assert re.search(r'#define\s+ATH12K_PCI_DMA_MASK\s+36',pci)
    assert 'dma_set_mask_and_coherent(&pdev->dev, ab_pci->dma_mask)' in pci
    qcom=source(a.linux_repository,LINUX,'drivers/iommu/arm/arm-smmu/arm-smmu-qcom.c')
    assert 'Firmware with quirky S2CR handling will ignore FAULT' in qcom
    assert 'Firmware with quirky S2CR handling will substitute' in qcom
    sheng=source(a.sheng_repository,SHENG,'package/WifiProbe.cpp')
    assert 'native_ufs_extra_va' in sheng and 'gArena.iova = native_ufs_extra_iova;' in sheng
    assert 'constexpr uint32_t kMsiAddrLo = 0x820, kMsiAddrHi = 0x824' in sheng
    own=(ROOT/'drivers/EldenSmmu/BootRoute.c').read_text(encoding='utf-8')
    assert 'r->cbar==0x0001f300u' in own and 'r->slot>=8&&r->slot<132' in own and 'r->bank>=7&&r->bank<83' in own
    board=(ROOT/'package/EldenTouchBoard.h').read_text(encoding='utf-8')
    for name,value in [('SLOTS','132u'),('BANKS','83u'),('SLOT','7u'),('BANK','0u'),('ID2','0x00005111u')]:
        assert re.search(r'#define\s+ELDEN_TOUCH_DMA_'+name+r'\s+'+value+r'\b',board)
    legacy=(ROOT/'drivers/EldenNvt36536/DmaRoute.c').read_text(encoding='utf-8')
    assert 'i<7?active[i]:0' in legacy and 'i<7?0x1f000u:0' in legacy
    stock=None
    if a.stock_fdt:
        data=a.stock_fdt.read_bytes()
        assert hashlib.sha256(data).hexdigest()=='b060f1001c4907895656c967fe3b2e5f6fb4d350be65cd79e4e3f4cdff1a8a45'
        sys.path.insert(0,str(ROOT/'tools/legacy-workbench'));from fdt_memory_plan import parse_fdt
        nodes,_=parse_fdt(data);matches=[(path,value) for path,value in nodes.items() if path.endswith('@15000000')]
        assert len(matches)==1;path,props=matches[0]
        raw=props['interrupts'];assert len(raw)%12==0
        interrupts=[struct.unpack('>III',raw[i:i+12]) for i in range(0,len(raw),12)]
        reg=list(struct.unpack('>'+str(len(props['reg'])//4)+'I',props['reg']))
        stock={'node':path,'reg_cells':reg,'interrupt_count':len(interrupts),'first_interrupts':interrupts[:10],
               'source_fdt_sha256':hashlib.sha256(data).hexdigest()}
    result={'passed':True,'inputs':inputs,'stock':stock,'historical_touch_slots':132,'historical_touch_banks':83,
            'historical_id2':0x5111,'decoded_historical_input_output_upper_bits':[36,36,36],
            'linux_pci_streaming_and_coherent_mask_bits':36,'new_context_cbar':0x1f300,'inherited_cb0_cbar':0x1f000,
            'scope':'Source/retained stock facts only; no new SMMU read, ownership, table or hardware verification',
            'remaining':['Native early allocator/context/ASID/fault-handler preflight before UFS/Data publication',
                         'Only then reserve/program/read back/commit immutable Wi-Fi route before touch seals',
                         'Qualify owned data/table pages, translations and DMA drain before MSI/MHI']}
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
