"""Check MMU-500 ATOSNS handling against the fixed TB322FC Linux source."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];REV='6f97250ead155fc3b980856323e99a4623dae73d'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--linux-repository',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    inputs={}
    def read(name):
        b=subprocess.check_output(['git','-C',str(a.linux_repository),'show',REV+':'+name]);inputs[name]=hashlib.sha256(b).hexdigest();return b.decode()
    h=read('drivers/iommu/arm/arm-smmu/arm-smmu.h');c=read('drivers/iommu/arm/arm-smmu/arm-smmu.c')
    assert '#define ARM_SMMU_ID0_ATOSNS\t\tBIT(26)' in h
    assert '!(id & ARM_SMMU_ID0_ATOSNS)' in c and 'return ops->iova_to_phys(ops, iova);' in c
    domain=(ROOT/'drivers/EldenSmmu/Domain.c').read_text(encoding='utf-8');native=(ROOT/'drivers/EldenSmmu/Native.cpp').read_text(encoding='utf-8')
    assert 'if(s->id0&(1u<<26))' in domain and 'd->translation_mode=2;' in domain
    assert '(c->selection.id0&(1u<<26)))return -95;' in native
    result={'passed':True,'revision':REV,'inputs':inputs,'known_id0':0x4c017e84,'atos_supported':False,
            'fallback':'Linux page-table walk; Elden independently audits the full physical table graph and observes the context',
            'hardware_dma_verified':False,'scope':'Source/known-capability audit; actual selected IDs must still be read in native preflight'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
