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
    profile=audit['bluetooth_runtime']['profile'];unique=profile=='smmu-unique-memory';segmented=unique or profile=='smmu-segmented-memory';detail=segmented or profile=='smmu-memory-detail'
    assert audit['accepted_static'] and profile in ('smmu-domain-trial','smmu-memory-detail','smmu-segmented-memory','smmu-unique-memory') and audit['bluetooth_runtime']['smmu_domain']
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
    if detail:
        assert ('ELDEN_DMA_MEMORY stage=11 reason=3 rc=-71 init=-71 cleanup=1/0 offset=0 access=0 attr=44' if unique else 'ELDEN_DMA_MEMORY stage=11 reason=4 rc=-71 init=-71 cleanup=1/0 offset=0 access=0 attr=44' if segmented else 'ELDEN_DMA_MEMORY stage=6 reason=2 rc=-71 init=-71 cleanup=1/0 offset=0 access=0 attr=0') in text
        geometry=re.findall(r'ELDEN_DMA_MEMORY geometry data=([0-9a-f]+)/([0-9a-f]+) table=([0-9a-f]+)/([0-9a-f]+) cpu=([0-9a-f]+)/([0-9a-f]+)',text)
        assert len(geometry)==1;values=[int(x,16) for x in geometry[0]]
        assert all(values[i] for i in [0,2,4,5]) and values[1]==0x4000000 and values[3]==0x42000
        if not segmented:assert 'ELDEN_DMA_MEMORY page expected=0 physical=0 span=0 par=0' in text
        result.update(allocator_stage_detail_unknown=False,allocator_stage=6,allocator_reason=2,cleanup_passed=True,
                      first_data_segment_bytes=values[1],requested_data_allocation_bytes=130<<20,first_table_segment_bytes=values[3],
                      first_data_physical=hex(values[0]),first_table_physical=hex(values[2]),
                      next='Replace whole-first-segment assumption with existing full page-by-page physical/PAR proof; actual later continuity remains to be tested')
        if segmented:
            pages=re.findall(r'ELDEN_DMA_MEMORY page expected=([0-9a-f]+) physical=([0-9a-f]+) span=([0-9a-f]+) par=([0-9a-f]+)',text)
            assert len(pages)==1;pa,physical,span,par=[int(x,16) for x in pages[0]]
            assert pa==physical==values[0] and span==0x4000000
            if unique:assert par==0x80d
            else:assert not par&1 and (par&0x0000fffffffff000)==pa and par>>56==0xff
            result.update(allocator_stage=11,allocator_reason=4,whole_backing_pages_verified=True,expected_nc_attribute=0x44,observed_attribute=0xff,observed_par=hex(par),
                          next='Force a unique mapping to bypass same-task static reuse; retain NC44 and full physical/PAR requirements')
            if unique:result.update(allocator_reason=3,observed_attribute=None,unique_alias_par_fault=True,
                                   next='Use IOKit prefault for the already-wired unique mapping; retain full PA and NC44 checks')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
