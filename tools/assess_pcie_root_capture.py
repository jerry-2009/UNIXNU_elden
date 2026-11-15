"""Assess one session-bound root-only trial and its complete stock restoration."""
import argparse,hashlib,json,re
from pathlib import Path
STOCK='8b8e72dad85a65d3bf6fc2c6b2a88064d0487e4696ae578e9fd4c46a33565890'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def assess(run,audit,endpoint=False,smmu=False):
    endpoint=endpoint or smmu
    run=Path(run);audit=read(Path(audit));files=list((run/'usb').glob('*.bin'));assert len(files)==1
    raw=files[0].read_bytes();meta=read(files[0].with_suffix('.json'));text=raw.decode('ascii',errors='replace')
    assert len(raw)==meta['bytes'] and hashlib.sha256(raw).hexdigest()==meta['raw_sha256']
    assert meta['candidate_session']==audit['session'] and meta['boot_nonce']
    assert not meta['discontinuities'] and not meta['reconnections'] and meta['bound_startup_milestone_observed']
    statuses=meta['statuses'];assert statuses and all(s['session']==audit['session'] and s['boot']==meta['boot_nonce'] for s in statuses)
    assert any(s.get('fastboot')=='ready' and s.get('charge_control')=='1' for s in statuses)
    assert audit['accepted_static'] and (audit['rollback_index'],audit['footer_location'],audit['parent_boot_chain_location'])==(1738713600,0,3)
    assert audit['bluetooth_runtime']['profile']==('smmu-prefault-memory' if smmu else 'pcie-endpoint-trial' if endpoint else 'pcie-root-trial') and audit['bluetooth_runtime']['mode']==0
    stage=[int(v) for v in re.findall(r'ELDEN_PCIE stage=(\d+) ',text)];assert stage==list(range(1,12 if endpoint else 11))
    pattern=r'ELDEN_PCIE end rc=(-?\d+) state=(\d+) stage=(\d+) root=([0-9a-f]+) ep=([0-9a-f]+) link=([0-9a-f]+) last=(\d+):([0-9a-f]+)=([0-9a-f]+) writes=(\d+) phy=(\d+) gcc-held=(\d+)'
    rows=re.findall(pattern,text);assert len(rows)==1
    row=rows[0];rc,state,laststage=map(int,row[:3]);root,ep,link=map(lambda s:int(s,16),row[3:6])
    assert (rc,state,laststage,root,ep)==(0,2,11,0x011c17cb,0x110e17cb)
    assert int(row[6])==6 and int(row[7],16)==4 and not (int(row[8],16)&7)
    assert int(row[9])>0 and int(row[10])==127 and int(row[11])==0
    gen=(link>>16)&15;width=(link>>20)&63;assert 1<=gen<=3 and 1<=width<=2
    power=re.findall(r'ELDEN_PCIE_POWER result=(-?\d+) stage=(\d+) tcs=(\d+) mx=(\d+)/(\d+) cx=(\d+)/(\d+) SN4=(\d+) min=(\d+) full-on=1',text)
    assert len(power)==1;p=list(map(int,power[0]));assert p[0]==0 and p[1]==9 and p[2]<3 and p[4]>=256 and p[6]>=256 and p[7]==16383
    rails=re.findall(r'ELDEN_PCIE_POWER rail=(\d+) rc=(-?\d+) mv=(\d+) mode=([0-9a-f]+) status=([0-9a-f]+) enable=([0-9a-f]+)',text)
    assert len(rails)==2
    for i,rail in enumerate(rails):
        assert int(rail[0])==i and int(rail[1])==0 and (880 if i==0 else 1200)<=int(rail[2])<=(920 if i==0 else 1256)
        assert int(rail[3],16)&7==7 and int(rail[4],16)&128 and int(rail[5],16)&128
    required=['OS complete SHA256 accepted','SystemOS complete SHA256 accepted','ELDEN_UFS_IDLE enable-only=0 phase=2 active=1',
              'BSD root: disk5s1','ELDEN_BOOT init exec accepted','ELDEN_VDOG EARLY_ARM','ELDEN_VDOG SMP_ADOPT',
              'expected=ff online=ff work=ff timers=ff ipis=ff error=0',
              'ELDEN_RPC ACK_COMMITTED','ELDEN_UFS_IDLE stop=0 phase=4 error=0 active=0',
              'ELDEN_PCIE quiesced=1 perst-low=1 dma-enabled-by-driver=0','ELDEN_RPC RESET_AFTER_SYNC route=sdam-v7']
    positions={key:text.find(key) for key in required};assert all(v>=0 for v in positions.values())
    end=text.find('ELDEN_PCIE end ');ack=positions['ELDEN_RPC ACK_COMMITTED'];reset=positions[required[-1]]
    assert end<ack<positions[required[-3]]<positions[required[-2]]<reset
    assert 'ELDEN_UFS_IDLE row' not in text
    errors=[m.start() for m in re.finditer(r'device is not ready|request failed to start!',text)]
    assert not errors or min(errors)>reset
    supervisor=read(run/'supervisor.json');flash=read(run/'flash/result.json');restore=read(run/'restore/result.json')
    assert supervisor['complete'] and flash['success'] and restore['success']
    assert flash['full_readback_sha256']==audit['image_sha256'] and restore['full_readback_sha256']==STOCK
    assert supervisor['charging_before']==supervisor['charging_after'] and supervisor['radios_before']==supervisor['radios_after']
    assert supervisor['scan_settings_before']==supervisor['scan_settings_after']
    assert any(e['event']=='physical-fastboot-observed' for e in supervisor['events'])
    final=next(e for e in supervisor['events'] if e['event']=='stock-android-restored')
    assert final['root'] and final['green'] and final['settings_equal'] and final['radios_restored'] and final['sleep_requested']
    result={'root_trial_passed':True,'pcie_gen':gen,'lanes':width,'root_id':hex(root),'endpoint_id':hex(ep),'endpoint_command':hex(int(row[8],16)&0xffff),
            'phy_writes':127,'controller_writes':int(row[9]),'gcc_released':True,'quiesce_and_sync_return':True,'stock_full_sha_restored':True,
            'arc_requests':{'mx_index':p[3],'mx_level':p[4],'cx_index':p[5],'cx_level':p[6]},'sn4_requested':p[7],'sn4_calculated_minimum':p[8],
            'ldo_readback_mv':[int(x[2]) for x in rails],'capture_bytes':len(raw),'capture_sha256':meta['raw_sha256'],
            'reported_drop_max':max(int(s['dropped']) for s in statuses),'discontinuities':0,'reconnections':0,
            'storage_not_ready_messages_only_after_reset_marker':bool(errors),'pd_bootstrap_interrupted_by_return':any('phase=7 error=4' in e['line'] and 'restored=1' in e['line'] for e in meta['power_events']),
            'session':audit['session'],'image_sha256':audit['image_sha256'],'boot_nonce':meta['boot_nonce'],
            'scope':'PCIe root/PHY/config only; no BAR allocation, DMA, MSI, MHI, firmware, network or daily-power acceptance',
            'gate_scope':'Reported drop counters and critical lines complete; no final post-disconnect counter is available'}
    if result['reported_drop_max']:
        result['gate_scope']='Required lines present; whole stream incomplete due to reported drops; no final post-disconnect counter available'
    if endpoint:
        rows=re.findall(r'ELDEN_PCIE_EP end rc=(-?\d+) state=(\d+) stage=(\d+) chip=([0-9a-f]+) major=(\d+) minor=(\d+) command=([0-9a-f]+) mapped=(\d+) remap-restored=(\d+) confirmed=(\d+) writes=(\d+) last=(\d+):([0-9a-f]+)=([0-9a-f]+)',text)
        assert len(rows)==1;e=rows[0]
        assert tuple(map(int,e[:3]))==(0,2,8) and int(e[4])==2 and ((int(e[3],16)>>8)&15)==2
        assert ((int(e[3],16)>>4)&15)==int(e[5]) and int(e[6],16)&7==2
        assert tuple(map(int,e[7:10]))==(1,1,1) and int(e[10])>0
        assert [int(v) for v in re.findall(r'ELDEN_PCIE_EP stage=(\d+) ',text)]==list(range(1,8))
        bars=re.findall(r'ELDEN_PCIE_EP bars bar0=([0-9a-f]+)/([0-9a-f]+) bar2=([0-9a-f]+)/([0-9a-f]+) epoch=(\d+) dma=0',text)
        assert len(bars)==1 and tuple(int(v,16) for v in bars[0][:4])==(0x40400000,0x200000,0x40600000,0x8000)
        assert int(bars[0][4])>0 and end<text.find('ELDEN_PCIE_EP end ')<text.find('ELDEN_PCIE_EP bars ')<ack
        assert 'ELDEN_PCIE_EP mapped pa=40400000 bytes=200000 cache=inhibit' in text
        result.update(endpoint_trial_passed=True,chip_version=hex(int(e[3],16)),chip_major=2,chip_minor=int(e[5]),
                      endpoint_command_after_mapping=hex(int(e[6],16)),bar0=0x40400000,bar0_bytes=0x200000,
                      bar2=0x40600000,bar2_bytes=0x8000,endpoint_writes=int(e[10]),wlan_identity_confirmed=True,
                      scope='Root/BAR/Peach-major/confirmed power epoch only; no DMA/MSI/MHI/firmware/network or daily-power acceptance')
    if smmu:
        assert endpoint and audit['bluetooth_runtime']['prefault_memory']
        assert 'ELDEN_DMA_MEMORY stage=14 reason=0 rc=0 init=0 cleanup=0/0 offset=7fff000 access=1 attr=44' in text
        geometry=re.findall(r'ELDEN_DMA_MEMORY geometry data=([0-9a-f]+)/([0-9a-f]+) table=([0-9a-f]+)/([0-9a-f]+) cpu=([0-9a-f]+)/([0-9a-f]+)',text)
        assert len(geometry)==1;g=[int(v,16) for v in geometry[0]]
        assert g[1]==0x4000000 and g[3]==0x42000 and all(g[i] for i in [0,2,4,5])
        assert not g[0]&0x1fffff and not g[2]&4095
        assert g[0]+0x8200000<=1<<36 and g[2]+g[3]<=1<<36
        assert not (g[0]<g[2]+g[3] and g[2]<g[0]+0x8200000)
        pages=re.findall(r'ELDEN_DMA_MEMORY page expected=([0-9a-f]+) physical=([0-9a-f]+) span=([0-9a-f]+) par=([0-9a-f]+)',text)
        assert len(pages)==1;page=[int(v,16) for v in pages[0]]
        assert page[0]==page[1]==g[0]+0x8000000-4096 and page[2]==4096 and page[3]>>56==0x44 and not page[3]&1 and page[3]&0x0000fffffffff000==page[0]
        assert [int(v) for v in re.findall(r'ELDEN_SMMU domain-stage=(\d+) translations=0',text)]==list(range(1,8))
        context=re.findall(r'ELDEN_SMMU context phase=5 writes=13 readback=1 fault=([0-9a-f]+) cbar=1f300 cba2r=1 tcr=80802020 tcr2=([0-9a-f]+) sctlr=([0-9a-f]+)',text)
        assert len(context)==1;fsr,tcr2,sctlr=[int(v,16) for v in context[0]]
        assert not fsr&0xc00001fe and tcr2&~0x60==0x38011 and sctlr&~0x1000==0x67
        ttbr=re.findall(r'ELDEN_SMMU context ttbr=([0-9a-f]+)/([0-9a-f]+) mair=ff44/0',text)
        assert len(ttbr)==1 and int(ttbr[0][0],16)==(1<<48)|g[2] and int(ttbr[0][1],16)==1<<48
        ends=re.findall(r'ELDEN_SMMU end rc=0 stage=17 bank=7 slot=8 asid=1 translations=0 translation-mode=2 software-pages=32768 pages=66/32768 data=([0-9a-f]+) tables=([0-9a-f]+) sctlr=([0-9a-f]+) tcr2=([0-9a-f]+)',text)
        assert len(ends)==1 and [int(v,16) for v in ends[0]]==[g[0],g[2],sctlr,tcr2]
        for line in ['ELDEN_SMMU irq-request kind=0 intid=97 rc=0','ELDEN_SMMU irq-request kind=1 intid=136 rc=0',
                     'ELDEN_SMMU irq kind=0 intid=97 flags=0000a003 router=0','ELDEN_SMMU irq kind=1 intid=136 flags=0000a003 router=0',
                     'ELDEN_SMMU early-return=0 before-host-start=1','ELDEN_SMMU late status=0 ready=1 fault=0 fsr=0 stage=17',
                     'ELDEN_TOUCH_DMA attach=0 stage=5','ELDEN_TOUCH_DMA detach=0 stage=8 writes=3 poison=0','ELDEN_TOUCH_DMA memory-release=0',
                     'ELDEN_SMMU stop irq-mask=0/0 resources-retained=1 dma-started=0 fault=0']:
            assert line in text,line
        assert text.index('ELDEN_SMMU end rc=0')<text.index('ELDEN_TOUCH_DMA attach=0')<text.index('ELDEN_SMMU late status=0')<ack
        transfers=list(re.finditer(r'ELDEN_TOUCH_DMA xfer=(\d+) bytes=(\d+) error=(-?\d+) tx-in=(\d+) rx-in=(\d+)',text))
        assert transfers and all(int(t[3])==0 and int(t[2])>0 and int(t[4])==int(t[2]) and int(t[5]) in (0,int(t[2])) for t in transfers)
        assert all(text.index('ELDEN_TOUCH_DMA attach=0')<t.start()<text.index('ELDEN_TOUCH_DMA detach=0') for t in transfers)
        assert any(int(t[5])>0 for t in transfers)
        assert ack<text.index('ELDEN_SMMU stop irq-mask=0/0')<reset
        assert text.index('ELDEN_TOUCH_DMA detach=0')<text.index('ELDEN_TOUCH_DMA memory-release=0')<reset
        result.update(smmu_domain_configured=True,nc_memory_bytes=0x8000000,software_verified_pages=32768,table_pages=66,
                      data_physical=hex(g[0]),table_physical=hex(g[2]),context_fsr=hex(fsr),context_fsr_format=(fsr>>9)&3,
                      context_fault_bits=fsr&0xc00001fe,context_tcr2=hex(tcr2),context_sctlr=hex(sctlr),asid=1,bank=7,slot=8,
                      fault_irq_registration_and_masking=True,fault_injection_tested=False,touch_coexistence_start_stop=True,
                      touch_successful_transfer_records=len(transfers),
                      hardware_atos_supported=False,hardware_dma_transfers_tested=False,
                      scope='Owned NC memory, programmed/audited SMMU domain, fault IRQ registration, touch coexistence and full return; no device DMA/MSI/MHI/network acceptance')
    return result
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['run','audit','output']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--endpoint',action='store_true')
    p.add_argument('--smmu',action='store_true')
    a=p.parse_args();result=assess(a.run,a.audit,a.endpoint or a.smmu,a.smmu);a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
