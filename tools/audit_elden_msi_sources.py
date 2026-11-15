"""Record stock ITS routing and the fixed TB322FC controller MSI alternative."""
import argparse,hashlib,json,re,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REV='6f97250ead155fc3b980856323e99a4623dae73d'
STOCK='b060f1001c4907895656c967fe3b2e5f6fb4d350be65cd79e4e3f4cdff1a8a45'
sys.path.insert(0,str(ROOT/'tools/legacy-workbench'))
from fdt_memory_plan import parse_fdt

def words(raw):
    assert len(raw)%4==0
    return list(struct.unpack('>'+str(len(raw)//4)+'I',raw))

def block(text,start):
    offset=text.index(start);begin=text.index('{',offset);end=begin+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[offset:end]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['linux-repository','stock-fdt','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();assert not a.output.exists();raw=a.stock_fdt.read_bytes();assert hashlib.sha256(raw).hexdigest()==STOCK
    nodes,_=parse_fdt(raw);pci=nodes['/soc/pcie@1c00000'];mapping=words(pci['msi-map'])
    assert len(mapping)==8 and mapping[0::4]==[0,0x100] and mapping[2::4]==[0x1400,0x1401] and mapping[3::4]==[1,1]
    assert mapping[1]==mapping[5]
    matches=[(name,prop) for name,prop in nodes.items() if prop.get('phandle',prop.get('linux,phandle'))==struct.pack('>I',mapping[1])]
    assert len(matches)==1;its_path,its=matches[0];assert b'arm,gic-v3-its\0' in its['compatible'] and 'msi-controller' in its
    stock_irq=words(pci['interrupts']);names=pci['interrupt-names'].decode().rstrip('\0').split('\0')
    assert len(stock_irq)==3*len(names) and all(stock_irq[i]==0 and stock_irq[i+2]==4 for i in range(0,len(stock_irq),3))
    inputs={}
    def get(path):
        data=subprocess.check_output(['git','-C',str(a.linux_repository),'show',REV+':'+path]);inputs[path]=hashlib.sha256(data).hexdigest();return data.decode()
    dt=get('arch/arm64/boot/dts/qcom/sm8750.dtsi');node=block(dt,'pcie0: pcie@1c00000')
    assert '"qcom,pcie-sm8750"' in node and 'msi-map = <0x0 &gic_its 0x1400 0x1>' in node and '<0x100 &gic_its 0x1401 0x1>' in node
    interrupts=[int(v) for v in re.findall(r'<GIC_SPI (\d+) IRQ_TYPE_LEVEL_HIGH>',node.split('interrupts =',1)[1].split(';',1)[0])]
    names_linux=re.findall(r'"([^"]+)"',node.split('interrupt-names =',1)[1].split(';',1)[0])
    assert names_linux==['msi'+str(n) for n in range(8)]+['global'] and interrupts==list(range(141,149))+[140]
    host=get('drivers/pci/controller/dwc/pcie-designware-host.c');header=get('drivers/pci/controller/dwc/pcie-designware.h')
    selection=re.search(r'pp->use_imsi_rx\s*=\s*!\(pp->ops->msi_init\s*\|\|\s*of_property_present\(np, "msi-parent"\)\s*\|\|\s*of_property_present\(np, "msi-map"\)\);',host)
    assert selection
    init=block(host,'void dw_pcie_msi_init(')
    assert 'if (!pci_msi_enabled() || !pp->use_imsi_rx)' in init
    expected={'PCIE_MSI_ADDR_LO':0x820,'PCIE_MSI_ADDR_HI':0x824,'PCIE_MSI_INTR0_ENABLE':0x828,'PCIE_MSI_INTR0_MASK':0x82c,'PCIE_MSI_INTR0_STATUS':0x830,'MSI_REG_CTRL_BLOCK_SIZE':12,'MSI_DEF_NUM_VECTORS':32}
    for name,value in expected.items():
        actual=re.search(r'^#define\s+'+name+r'\s+(0x[0-9a-fA-F]+|\d+)\b',header,re.M);assert actual and int(actual[1],0)==value
    assert all(n in init for n in ['PCIE_MSI_INTR0_MASK','PCIE_MSI_INTR0_ENABLE','PCIE_MSI_ADDR_LO','PCIE_MSI_ADDR_HI'])
    assert 'platform_get_irq_byname_optional(pdev, msi_name)' in host and "msi_name[3] = '0' + ctrl;" in host
    result={'linux_commit':REV,'source_inputs':inputs,'stock_fdt_sha256':STOCK,
            'stock_msi_map':mapping,'stock_its_node':its_path,'stock_its_reg_cells':words(its['reg']),
            'stock_pcie_intids':dict(zip(names,[v+32 for v in stock_irq[1::3]])),
            'stock_and_linux_default_its':True,'linux_msi_map_disables_imsi_receiver':True,
            'linux_controller_msi_intids':dict(zip(names_linux,[v+32 for v in interrupts])),
            'designware_registers':expected,'controller0_vectors':32,
            'native_imsi_path_hardware_tested':False,'native_its_implemented':False,
            'scope':'Source facts only. INTID173 (SPI141) is independently described for TB322FC, but enabling local iMSI differs from the stock ITS route and needs receiver/IRQ/readback plus real device MSI evidence.'}
    a.output.mkdir(parents=True);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n');print(json.dumps(result))
if __name__=='__main__':main()
