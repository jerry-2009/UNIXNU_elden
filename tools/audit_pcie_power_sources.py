"""Check Elden PCIe power topology and the bounded stock rail observation."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from audit_pcie_root_sources import body
ROOT=Path(__file__).resolve().parents[1];REV='6f97250ead155fc3b980856323e99a4623dae73d'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--linux-repository',type=Path,required=True);p.add_argument('--stock-record',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('New output required')
    inputs={}
    def get(path):
        b=subprocess.check_output(['git','-C',str(a.linux_repository),'show',REV+':'+path]);inputs[path]=hashlib.sha256(b).hexdigest();return b.decode()
    dt=get('arch/arm64/boot/dts/qcom/sm8750-lenovo-elden.dts');icc=get('drivers/interconnect/qcom/sm8750.c')
    voter=get('drivers/interconnect/qcom/bcm-voter.c');init=get('drivers/interconnect/qcom/icc-rpmh.c')
    assert 'vdda-phy-supply = <&vreg_l1f_0p88>' in dt and 'vdda-pll-supply = <&vreg_l3g_1p2>' in dt
    for name,low,high in [('vreg_l1f_0p88',880000,920000),('vreg_l3g_1p2',1200000,1256000)]:
        b=dt.split(name+':',1)[1].split('};',1)[0]
        assert f'regulator-min-microvolt = <{low}>' in b and f'regulator-max-microvolt = <{high}>' in b
    assert '&qns_pcie_mem_noc' in body(icc,'bcm_sn4') and re.search(r'\.buswidth\s*=\s*8',body(icc,'qns_pcie_mem_noc'))
    assert re.search(r'\.channels\s*=\s*1',body(icc,'qns_pcie_mem_noc'))
    assert '.enable_mask = BIT(0)' in body(icc,'bcm_sh1') and '&qnm_pcie' in body(icc,'bcm_sh1')
    assert 'if (num && num < base)' in voter and 'do_div(num, base)' in voter and 'bcm->vote_scale = 1000' in init
    captured=(a.stock_record/'capture.txt').read_bytes();text=captured.decode();result=json.loads((a.stock_record/'result.json').read_text())
    assert result['complete'] and result['returncode']==0 and hashlib.sha256(captured).hexdigest()==result['capture_sha256']
    readings={}
    for chip,address,value in re.findall(r'READ (0-0[56]) (0xc[13][0-9a-f]{2}) [0-9a-f]+: ([0-9a-f]{2})',text):readings[(chip,int(address,16))]=int(value,16)
    rails=[]
    for chip,page,name,voltage in [('0-05',0xc100,'ldof1',880),('0-06',0xc300,'ldog3',1200)]:
        v={off:readings[(chip,page+off)] for off in [4,5,8,0x40,0x41,0x45,0x46]}
        assert v[4]==4 and v[5]==0xad and (v[8]&0x80) and v[0x45]==7 and v[0x46]==0x80
        assert v[0x40]+(v[0x41]<<8)==voltage
        before=re.search(r'BEGIN '+chip+r' address=(\S+) count=(\d+)',text).groups()
        after=re.search(r'END '+chip+r' address=(\S+) count=(\d+)',text).groups();assert before==after
        rails.append({'resource':name,'ppid':(int(chip[-2:],16)<<8)|(page>>8),'mv':voltage,'type':v[4],'subtype':v[5],'mode':v[0x45],'status':v[8],'enable':v[0x46],'cursor_restored':True})
    source=(ROOT/'drivers/EldenPcie/Power.c').read_text(encoding='utf-8')
    assert 'Sm8750RpmhArcTop' in source and 'plan.sn4_applied=0x3fff' in source and 'Sm8750BcmCommand(1,1,0,1)' in source
    assert not any('"'+n+'"' in source for n in ['MC0','ACV','gfx.lvl','SH0'])
    report={'passed':True,'revision':REV,'source_inputs':inputs,'stock_rails':rails,'stock_capture_sha256':result['capture_sha256'],
            'sn4_buswidth':8,'sn4_channels':1,'sh1_enable_mask':1,'hardware_votes_tested':False,
            'policy':'Explicit diagnostic only: ARC table top, SN4 saturated, SH1 enabled; retain until platform reset, no daily/energy acceptance',
            'power_source_sha256':hashlib.sha256(source.encode()).hexdigest()}
    a.output.mkdir(parents=True);(a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
