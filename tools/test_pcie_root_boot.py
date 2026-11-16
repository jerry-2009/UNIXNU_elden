"""Check root diagnostic routing without changing recovery or power guards."""
import json,tomllib
import bt_runtime_boot
from battery_boot import arguments
from pcie_root_boot import menu
def main():
    q={'profile':'pcie-root-trial','mode':0,'root_trial':True}
    base=tomllib.loads(bt_runtime_boot.menu({'profile':'ufs-idle-trial'}));actual=tomllib.loads(menu(q))
    before=arguments(base['entry'][0]['args']);after=arguments(actual['entry'][0]['args'])
    removed={'ecp','elden-wcn-power','elden-frame-preview','elden-userfault-log'}
    assert {k:v for k,v in before.items() if k not in removed}=={k:v for k,v in after.items() if k not in {'elden-pcie-root','elden-wlan-power','elden-pcie-full-on'}}
    assert all(after[k]=='1' for k in ['elden-pcie-root','elden-wlan-power','elden-pcie-full-on'])
    assert all(after[k]==v for k,v in {'vdog':'3','smp-hold':'600','elden-thermal':'3','epd':'2','elden-return-fastboot':'1','elden-panic-delay':'180','elden-key-events':'1'}.items())
    assert actual['boot']==base['boot'] and actual['entry'][1:]==base['entry'][1:]
    assert len(actual['entry'][0]['args'].replace('@SESSION@','0'*16).encode())==1011
    for bad in [{},dict(q,mode=4),dict(q,root_trial=False),dict(q,profile='ufs-idle-trial')]:
        try:menu(bad)
        except ValueError:pass
        else:raise AssertionError('Invalid intent accepted')
    assert bt_runtime_boot.menu(q)==menu(q)
    ep=dict(q,profile='pcie-endpoint-trial',endpoint_trial=True)
    epmenu=tomllib.loads(bt_runtime_boot.menu(ep));ep_args=arguments(epmenu['entry'][0]['args'])
    assert ep_args.pop('epe')=='1' and ep_args==after
    assert len(epmenu['entry'][0]['args'].replace('@SESSION@','0'*16).encode())==1015
    assert epmenu['entry'][1:]==actual['entry'][1:] and epmenu['boot']==actual['boot']
    for bad in [dict(ep,mode=4),dict(ep,root_trial=False),dict(ep,endpoint_trial=False)]:
        try:menu(bad)
        except ValueError:pass
        else:raise AssertionError('Invalid endpoint intent accepted')
    smmu=dict(ep,profile='smmu-domain-trial',smmu_domain=True);smmu_menu=tomllib.loads(bt_runtime_boot.menu(smmu))
    assert len(smmu_menu['entry'][0]['args'].replace('@SESSION@','0'*16).encode())==1019
    smmu_args=arguments(smmu_menu['entry'][0]['args']);assert smmu_args.pop('esm')=='1' and smmu_args==arguments(epmenu['entry'][0]['args'])
    assert smmu_menu['entry'][1:]==actual['entry'][1:] and smmu_menu['boot']==actual['boot']
    try:menu(dict(smmu,smmu_domain=False))
    except ValueError:pass
    else:raise AssertionError('Unqualified SMMU accepted')
    detail=dict(smmu,profile='smmu-memory-detail',memory_detail=True)
    detail_menu=tomllib.loads(bt_runtime_boot.menu(detail))
    assert detail_menu['entry'][0]['args']==smmu_menu['entry'][0]['args'] and detail_menu['entry'][1:]==smmu_menu['entry'][1:]
    try:menu(dict(detail,memory_detail=False))
    except ValueError:pass
    else:raise AssertionError('Unqualified memory report accepted')
    segmented=dict(detail,profile='smmu-segmented-memory',segmented_memory=True)
    assert tomllib.loads(bt_runtime_boot.menu(segmented))['entry'][0]['args']==smmu_menu['entry'][0]['args']
    try:menu(dict(segmented,segmented_memory=False))
    except ValueError:pass
    else:raise AssertionError('Unqualified segmented allocator accepted')
    unique=dict(segmented,profile='smmu-unique-memory',unique_memory=True)
    assert tomllib.loads(bt_runtime_boot.menu(unique))['entry'][0]['args']==smmu_menu['entry'][0]['args']
    try:menu(dict(unique,unique_memory=False))
    except ValueError:pass
    else:raise AssertionError('Unqualified unique mapping accepted')
    prefault=dict(unique,profile='smmu-prefault-memory',prefault_memory=True)
    assert tomllib.loads(bt_runtime_boot.menu(prefault))['entry'][0]['args']==smmu_menu['entry'][0]['args']
    try:menu(dict(prefault,prefault_memory=False))
    except ValueError:pass
    else:raise AssertionError('Unqualified prefault mapping accepted')
    mhi=dict(prefault,profile='wifi-mhi-runtime',mhi_runtime=True)
    mhi_menu=tomllib.loads(bt_runtime_boot.menu(mhi));mhi_args=arguments(mhi_menu['entry'][0]['args'])
    assert mhi_args.pop('ewt')=='1' and mhi_args==arguments(smmu_menu['entry'][0]['args'])
    assert len(mhi_menu['entry'][0]['args'].replace('@SESSION@','0'*16).encode())==1023
    assert mhi_menu['boot']==actual['boot'] and mhi_menu['entry'][1:]==actual['entry'][1:]
    try:menu(dict(mhi,mhi_runtime=False))
    except ValueError:pass
    else:raise AssertionError('Unqualified MHI runtime accepted')
    trace=dict(mhi,profile='wifi-init-trace',runtime_init_trace=True)
    assert tomllib.loads(bt_runtime_boot.menu(trace))['entry'][0]['args']==mhi_menu['entry'][0]['args']
    try:menu(dict(trace,runtime_init_trace=False))
    except ValueError:pass
    else:raise AssertionError('Unqualified init trace accepted')
    control=dict(trace,profile='wifi-control-transport',control_transport_bound=True)
    assert tomllib.loads(bt_runtime_boot.menu(control))['entry'][0]['args']==mhi_menu['entry'][0]['args']
    try:menu(dict(control,control_transport_bound=False))
    except ValueError:pass
    else:raise AssertionError('Unqualified control transport accepted')
    print(json.dumps({'passed':True,'bytes':1011,'endpoint_bytes':1015,'smmu_bytes':1019,'mhi_bytes':1023,'all_memory_args_unchanged':True,'guards_preserved':True,'fallbacks_preserved':True,'invalid_intents_rejected':15}))
if __name__=='__main__':main()
