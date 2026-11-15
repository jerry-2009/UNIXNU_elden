"""Verify the bounded v159 allocation refusal, preserved drivers and stock return."""
import argparse,hashlib,json,re
from pathlib import Path
STOCK='8b8e72dad85a65d3bf6fc2c6b2a88064d0487e4696ae578e9fd4c46a33565890'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['run','audit','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();audit=read(a.audit);files=list((a.run/'usb').glob('*.bin'));assert len(files)==1
    raw=files[0].read_bytes();meta=read(files[0].with_suffix('.json'));text=raw.decode('ascii',errors='replace')
    assert len(raw)==meta['bytes'] and hashlib.sha256(raw).hexdigest()==meta['raw_sha256']
    assert meta['candidate_session']==audit['session'] and meta['bound_startup_milestone_observed'] and not meta['discontinuities'] and not meta['reconnections']
    assert audit['accepted_static'] and audit['bluetooth_runtime']['profile']=='smmu-domain-trial' and audit['bluetooth_runtime']['smmu_domain']
    assert (audit['rollback_index'],audit['footer_location'],audit['parent_boot_chain_location'])==(1738713600,0,3)
    statuses=meta['statuses'];assert statuses and all(s['session']==audit['session'] and s['boot']==meta['boot_nonce'] for s in statuses)
    assert [int(n) for n in re.findall(r'ELDEN_SMMU read-context bank=(\d+) ',text)]==list(range(83))
    selection=re.findall(r'ELDEN_SMMU selection rc=0 stage=6 last=d2058:0 reads=(\d+) bank=(\d+) asid=(\d+) cb0=([0-9a-f]+)',text)
    assert len(selection)==1 and tuple(map(int,selection[0][:3]))==(601,7,1)
    cb0=int(selection[0][3],16);assert not cb0&1
    failed='ELDEN_SMMU end rc=-71 stage=3 bank=7 slot=8 asid=1 translations=0 translation-mode=0 software-pages=0 pages=0/0 data=0 tables=0 sctlr=0 tcr2=0'
    assert failed in text and 'ELDEN_SMMU domain-stage=' not in text and 'ELDEN_SMMU irq kind=' not in text
    assert 'ELDEN_SMMU early-return=-71 before-host-start=1' in text
    assert 'ELDEN_SMMU late status=0 ready=0 fault=0 fsr=0 stage=3' in text
    assert re.search(r'ELDEN_PCIE end rc=-11 state=4 stage=2 .* writes=0 phy=0 gcc-held=0',text)
    needed=['OS complete SHA256 accepted','SystemOS complete SHA256 accepted','BSD root: disk5s1','ELDEN_BOOT init exec accepted',
            'expected=ff online=ff work=ff timers=ff ipis=ff error=0',
            'ELDEN_TOUCH_DMA attach=0 stage=5','ELDEN_TOUCH_DMA detach=0 stage=8 writes=3 poison=0','ELDEN_TOUCH_DMA memory-release=0',
            'ELDEN_UFS_IDLE stop=0 phase=4 error=0 active=0','ELDEN_SMMU stop irq-mask=0/0 resources-retained=1 dma-started=0 fault=0',
            'ELDEN_RPC ACK_COMMITTED','ELDEN_RPC RESET_AFTER_SYNC route=sdam-v7']
    assert all(s in text for s in needed)
    assert f'ELDEN_TOUCH_DMA cb0-sctlr={cb0:08x} captured=1 preserved=1' in text
    assert text.index(failed)<text.index('ELDEN_RPC ACK_COMMITTED')<text.index('ELDEN_RPC RESET_AFTER_SYNC')
    run=read(a.run/'supervisor.json');flash=read(a.run/'flash/result.json');restore=read(a.run/'restore/result.json')
    assert run['complete'] and flash['success'] and restore['success']
    assert flash['full_readback_sha256']==audit['image_sha256'] and restore['full_readback_sha256']==STOCK
    for key in ['charging','radios','scan_settings']:assert run[key+'_before']==run[key+'_after']
    assert any(e['event']=='physical-fastboot-observed' for e in run['events'])
    restored=next(e for e in run['events'] if e['event']=='stock-android-restored')
    assert all(restored[k] for k in ['root','green','settings_equal','radios_restored','sleep_requested'])
    result={'selection_passed':True,'selection_reads':601,'bank':7,'slot':8,'asid':1,'cb0_sctlr':hex(cb0),
            'allocator_result':-71,'allocator_stage_detail_unknown':True,'smmu_configured':False,'fault_irqs_registered':False,
            'pcie_power_refused_on_missing_domain':True,'touch_dma_start_stop_passed':True,'real_finger_tested':False,'all_eight_cpu_admission':True,
            'sync_and_full_stock_restore_passed':True,'original_settings_restored':True,'capture_bytes':len(raw),'capture_sha256':meta['raw_sha256'],
            'reported_drop_max':max(int(s['dropped']) for s in statuses),'session':audit['session'],'image_sha256':audit['image_sha256'],
            'scope':'Read-only SMMU selection and guarded refusal/recovery; no mapped Wi-Fi domain, IRQ/DMA/MHI/network acceptance',
            'next':'Expose exact allocation/physical-segment/PAR failure before changing a gate or retrying hardware'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
