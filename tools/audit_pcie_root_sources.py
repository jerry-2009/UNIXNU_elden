"""Bind the root controller's register/clock contract to fixed TB322FC Linux."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];REV='6f97250ead155fc3b980856323e99a4623dae73d'
def body(text,name):
    m=re.search(r'\b'+re.escape(name)+r'(?:\[\])?\s*=\s*\{',text)
    if not m:raise ValueError('Missing declaration '+name)
    return text[m.end():].split('\n};',1)[0]
def field(text,name):
    m=re.search(r'\.'+name+r'\s*=\s*(0x[0-9a-fA-F]+|\d+)\s*,',text)
    if not m:raise ValueError('Missing field '+name)
    return int(m[1],0)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--linux-repository',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('New output required')
    inputs={}
    def get(path):
        b=subprocess.check_output(['git','-C',str(a.linux_repository),'show',REV+':'+path]);inputs[path]=hashlib.sha256(b).hexdigest();return b.decode()
    gcc=get('drivers/clk/qcom/gcc-sm8750.c');gdsc=get('drivers/clk/qcom/gdsc.c');rcg=get('drivers/clk/qcom/clk-rcg2.c')
    mux=get('drivers/clk/qcom/clk-regmap-phy-mux.c');tcsr=get('drivers/clk/qcom/tcsrcc-sm8750.c')
    pcie=get('drivers/pci/controller/dwc/pcie-qcom.c');dt=get('arch/arm64/boot/dts/qcom/sm8750.dtsi')
    source=(ROOT/'drivers/EldenPcie/Root.c').read_text(encoding='utf-8');records=[]
    names=['pcie_0_slv_axi','pcie_0_mstr_axi','pcie_0_cfg_ahb','pcie_0_aux','pcie_0_pipe','pcie_0_slv_q2a_axi',
           'cnoc_pcie_sf_axi','qmip_pcie_ahb','aggre_noc_pcie_axi','ddrss_pcie_sf_qtb','cfg_noc_pcie_anoc_ahb','pcie_0_phy_rchng']
    rows=re.findall(r'\{(0x[0-9a-f]+),(true|false),(true|false)\}',body(source,'branches'))
    assert len(rows)==len(names);votes={}
    for name,row in zip(names,rows):
        b=body(gcc,'gcc_'+name+'_clk');enable=field(b,'enable_reg');bit=int(re.search(r'\.enable_mask\s*=\s*BIT\((\d+)\)',b)[1])
        halt=field(b,'halt_reg');hwcg='.hwcg_reg' in b;skip='BRANCH_HALT_SKIP' in b
        assert (int(row[0],0),row[1]=='true',row[2]=='true')==(halt,hwcg,skip)
        if hwcg:assert field(b,'hwcg_reg')==halt and field(b,'hwcg_bit')==1
        votes[enable]=votes.get(enable,0)|(1<<bit);records.append({'name':name,'vote_reg':enable,'vote_bit':bit,'halt_reg':halt,'hwcg':hwcg,'skip':skip})
    assert votes=={0x52008:0x7f,0x52000:sum(1<<v for v in [11,12,19,20,22])}
    assert 'Vote8=0x7f,Vote0=(1u<<11)|(1u<<12)|(1u<<19)|(1u<<20)|(1u<<22)' in source
    domains=[]
    for name,address,bit,clk_wait in [('gcc_pcie_0_gdsc',0x6b004,0,15),('gcc_pcie_0_phy_gdsc',0x6c000,2,2)]:
        b=body(gcc,name);assert field(b,'gdscr')==address and field(b,'collapse_ctrl')==0x5214c
        assert int(re.search(r'\.collapse_mask\s*=\s*BIT\((\d+)\)',b)[1])==bit
        assert all(f in b for f in ['POLL_CFG_GDSCR','RETAIN_FF_ENABLE','VOTABLE'])
        assert field(b,'en_rest_wait_val')==2 and field(b,'en_few_wait_val')==2 and field(b,'clk_dis_wait_val')==clk_wait
        assert re.search(r'#define\s+GDSC_POWER_UP_COMPLETE\s+BIT\(16\)',gdsc)
        assert re.search(r'#define\s+CFG_GDSCR_OFFSET\s+0x4',gdsc)
        assert 'reg = sc->gdscr + CFG_GDSCR_OFFSET;' in gdsc
        assert f'0x{address+4:x},1u<<16,1u<<16,2000' in source
        expected=(2<<20)|(2<<16)|(clk_wait<<12)
        assert f'0x{address:x},0x00fff006,0x{expected:08x}' in source
        domains.append({'name':name,'gdscr':address,'status_register':address+4,'up_bit':16,'collapse_bit':bit,'wait_value':expected})
    assert field(body(gcc,'gcc_pcie_0_aux_clk_src'),'cmd_rcgr')==0x6b084
    assert field(body(gcc,'gcc_pcie_0_phy_rchng_clk_src'),'cmd_rcgr')==0x6b068
    assert field(body(gcc,'gcc_pcie_0_pipe_clk_src'),'reg')==0x6b080
    assert 'F(19200000, P_BI_TCXO, 1, 0, 0)' in body(gcc,'ftbl_gcc_pcie_0_aux_clk_src')
    assert 'F(100000000, P_GCC_GPLL0_OUT_EVEN, 3, 0, 0)' in body(gcc,'ftbl_gcc_pcie_0_phy_rchng_clk_src')
    assert '{ P_GCC_GPLL0_OUT_EVEN, 6 }' in body(gcc,'gcc_parent_map_0')
    assert re.search(r'#define\s+CFG_HW_CLK_CTRL_MASK\s+BIT\(20\)',rcg)
    assert 'RcgMask=0x10371f' in source and 'rcg(r,0x6b084,1)' in source and 'r->max_gen==3?0x605:1' in source
    assert re.search(r'#define\s+PHY_MUX_PHY_SRC\s+0',mux) and re.search(r'#define\s+PHY_MUX_REF_SRC\s+2',mux)
    assert field(body(tcsr,'tcsr_pcie_0_clkref_en'),'enable_reg')==0
    assert 'reg = <0x0 0x0f204008 0x0 0x3004>' in dt and 'EldenPcieTcsr,8,1,1' in source
    for key,offset in [('GCC_PCIE_0_BCR',0x6b000),('GCC_PCIE_0_PHY_BCR',0x6c01c)]:
        assert re.search(r'\['+key+r'\]\s*=\s*\{\s*0x'+f'{offset:x}'+r'\s*\}',gcc)
        assert f'reset_block(r,0x{offset:x})' in source
    parf={'PARF_PHY_CTRL':0x40,'PARF_DBI_BASE_ADDR_V2':0x350,'PARF_DBI_BASE_ADDR_V2_HI':0x354,
          'PARF_SLV_ADDR_SPACE_SIZE_V2':0x358,'PARF_SLV_ADDR_SPACE_SIZE_V2_HI':0x35c,'PARF_ATU_BASE_ADDR':0x634,
          'PARF_ATU_BASE_ADDR_HI':0x638,'PARF_DEVICE_TYPE':0x1000,'PARF_BDF_TO_SID_TABLE_N':0x2000,'PARF_BDF_TO_SID_CFG':0x2c00,
          'PARF_MHI_CLOCK_RESET_CTRL':0x174,'PARF_AXI_MSTR_WR_ADDR_HALT_V2':0x1a8,'PARF_LTSSM':0x1b0}
    for key,value in parf.items():assert re.search(r'#define\s+'+key+r'\s+0x'+f'{value:x}'+r'\b',pcie,re.I)
    assert '"qcom,pcie-sm8750", "qcom,pcie-sm8550"' in dt
    assert '.compatible = "qcom,pcie-sm8550", .data = &cfg_1_9_0' in pcie
    assert '.init = qcom_pcie_init_2_7_0' in body(pcie,'ops_1_9_0') and '.config_sid = qcom_pcie_config_sid_1_9_0' in body(pcie,'ops_1_9_0')
    facts=json.loads((ROOT/'drivers/EldenPcie/board-facts.json').read_text(encoding='utf-8'))
    assert facts['windows']['parf']==[0x1c00000,0x3000] and facts['windows']['dm_core']==[0x40000000,0xf1d]
    assert facts['windows']['iatu']==[0x40001000,0x1000] and facts['windows']['conf']==[0x40100000,0x100000]
    result={'passed':True,'linux_revision':REV,'source_inputs':inputs,'root_source_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'branches':records,'vote_masks':{hex(k):hex(v) for k,v in votes.items()},'gdsc':domains,'parf_registers':parf,
            'tcsr_physical':0xf204008,'rcg_values':{'tcxo_19_2_mhz':1,'gpll_even_100_mhz':0x605},
            'board_facts_sha256':hashlib.sha256((ROOT/'drivers/EldenPcie/board-facts.json').read_bytes()).hexdigest(),
            'scope':'Source-level register/clock contract; not native supplies/NoC admission or hardware acceptance'}
    a.output.mkdir(parents=True);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
