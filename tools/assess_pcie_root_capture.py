"""Assess one session-bound root-only trial and its complete stock restoration."""
import argparse,hashlib,json,re
from pathlib import Path
STOCK='8b8e72dad85a65d3bf6fc2c6b2a88064d0487e4696ae578e9fd4c46a33565890'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def assess(run,audit):
    run=Path(run);audit=read(Path(audit));files=list((run/'usb').glob('*.bin'));assert len(files)==1
    raw=files[0].read_bytes();meta=read(files[0].with_suffix('.json'));text=raw.decode('ascii',errors='replace')
    assert len(raw)==meta['bytes'] and hashlib.sha256(raw).hexdigest()==meta['raw_sha256']
    assert meta['candidate_session']==audit['session'] and meta['boot_nonce']
    assert not meta['discontinuities'] and not meta['reconnections'] and meta['bound_startup_milestone_observed']
    statuses=meta['statuses'];assert statuses and all(s['session']==audit['session'] and s['boot']==meta['boot_nonce'] for s in statuses)
    assert any(s.get('fastboot')=='ready' and s.get('charge_control')=='1' for s in statuses)
    assert audit['accepted_static'] and (audit['rollback_index'],audit['footer_location'],audit['parent_boot_chain_location'])==(1738713600,0,3)
    assert audit['bluetooth_runtime']['profile']=='pcie-root-trial' and audit['bluetooth_runtime']['mode']==0
    stage=[int(v) for v in re.findall(r'ELDEN_PCIE stage=(\d+) ',text)];assert stage==list(range(1,11))
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
    return {'root_trial_passed':True,'pcie_gen':gen,'lanes':width,'root_id':hex(root),'endpoint_id':hex(ep),'endpoint_command':hex(int(row[8],16)&0xffff),
            'phy_writes':127,'controller_writes':int(row[9]),'gcc_released':True,'quiesce_and_sync_return':True,'stock_full_sha_restored':True,
            'arc_requests':{'mx_index':p[3],'mx_level':p[4],'cx_index':p[5],'cx_level':p[6]},'sn4_requested':p[7],'sn4_calculated_minimum':p[8],
            'ldo_readback_mv':[int(x[2]) for x in rails],'capture_bytes':len(raw),'capture_sha256':meta['raw_sha256'],
            'reported_drop_max':max(int(s['dropped']) for s in statuses),'discontinuities':0,'reconnections':0,
            'storage_not_ready_messages_only_after_reset_marker':bool(errors),'pd_bootstrap_interrupted_by_return':any('phase=7 error=4' in e['line'] and 'restored=1' in e['line'] for e in meta['power_events']),
            'session':audit['session'],'image_sha256':audit['image_sha256'],'boot_nonce':meta['boot_nonce'],
            'scope':'PCIe root/PHY/config only; no BAR allocation, DMA, MSI, MHI, firmware, network or daily-power acceptance',
            'gate_scope':'Reported drop counters and critical lines complete; no final post-disconnect counter is available'}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['run','audit','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();result=assess(a.run,a.audit);a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
