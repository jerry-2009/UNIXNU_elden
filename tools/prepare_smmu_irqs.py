"""Extract the retained TB322FC SMMU interrupt map; no hardware accesses."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/legacy-workbench'))
from fdt_memory_plan import parse_fdt
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stock-fdt',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    raw=a.stock_fdt.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    assert digest=='b060f1001c4907895656c967fe3b2e5f6fb4d350be65cd79e4e3f4cdff1a8a45'
    nodes,_=parse_fdt(raw);node=nodes['/soc/apps-smmu@15000000']
    assert node['compatible']==b'qcom,qsmmu-v500\0' and node['#global-interrupts']==struct.pack('>I',1)
    values=[struct.unpack('>III',node['interrupts'][i:i+12]) for i in range(0,len(node['interrupts']),12)]
    assert len(values)==113 and all(t==0 and flag==4 for t,n,flag in values)
    ints=[n+32 for t,n,f in values];assert len(set(ints))==len(ints)
    facts={'source_sha256':digest,'node':'/soc/apps-smmu@15000000','global_interrupt_count':1,'global_intid':ints[0],
           'context_intids':ints[1:84],'unused_dt_context_intids':ints[84:],'level_high':True,'hardware_banks_from_id1':83}
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'Irqs.json').write_text(json.dumps(facts,indent=2)+'\n',encoding='utf-8',newline='\n')
    text='/* SPDX-License-Identifier: BSD-2-Clause-Patent */\n/* Stock TB322FC '+digest+'; DT SPI numbers +32. */\n#pragma once\n'
    text+='enum {EldenSmmuGlobalIntid='+str(ints[0])+'};\nstatic const unsigned elden_smmu_context_intids[83]={\n'
    for i in range(0,83,12):text+='    '+','.join(str(n) for n in ints[1:84][i:i+12])+',\n'
    text+='};\n';(a.output/'Irqs.h').write_text(text,encoding='utf-8',newline='\n')
    print(json.dumps(facts))
if __name__=='__main__':main()
