"""Rebuild PMIC cache and shared WCN admission over qualified retained inputs."""
import argparse,hashlib,json,re,subprocess,sys,os
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi'))
import BatteryAdmissionSource as source


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def symbols(p,d):return {n for n,v in global_symbols(p).items() if bool(v[0]&0x0e)==d}


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('pmic-build','wcn-build','clean-build','parent-build','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--sideband-pins',action='store_true',help='Exact board SW_CTRL18/19 and HOST_SOL202 before WLAN enable')
    p.add_argument('--board-state',action='store_true',help='Read existing physical WCN rail/pin state at qualified runtime boundaries')
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);pmic=a.pmic_build.resolve();wcn=a.wcn_build.resolve();parent=a.parent_build.resolve()
    pr=read(pmic/'result.json');wr=read(wcn/'result.json');kr=read(parent/'result.json');proofs={};wcn_source=source.wcn()
    if a.sideband_pins:
        from SidebandSource import source as sideband_source
        wcn_source=sideband_source(a.board_state)
    elif a.board_state:raise ValueError('Board state requires qualified sideband maps')
    for unit,folder,report,derived in [('PmicClient',pmic,pr['native_objects']['PmicClient'],source.client()),('WcnPowerNative',wcn,wr,wcn_source)]:
        objname=unit+'.o';old=folder/objname
        if sha(old)!=report['object_sha256']:raise ValueError('Retained consumer object changed')
        for n,h in report.get('source_inputs',{}).items():
            if sha(ROOT/n)!=h:raise ValueError('Retained consumer source changed: '+n)
        path=out/(unit+'.cpp');path.write_bytes(derived);overlay=read(folder/(unit+'.overlay.json' if unit=='PmicClient' else 'overlay.json'))
        if overlay.get('fallthrough') is not False:raise ValueError('Strict consumer overlay required')
        changed=[];inherited={};aliases=set();directories=set()
        for item in overlay['roots']:
            oldpath=Path(item['external-contents']);inherited[str(oldpath)]=sha(oldpath)
            if oldpath.name==unit+'.cpp':
                if sha(oldpath)!=report['source_sha256']:raise ValueError('Retained source hash changed')
                item['external-contents']=str(path);changed.append(item['name']);directories.add(str(Path(item['name']).parent))
            aliases.add(item['name'])
        if not changed:raise ValueError('Consumer source not bound')
        if unit=='PmicClient':
            for directory in directories:
                alias=str(Path(directory)/'BatteryAdmission.h')
                if alias in aliases:raise ValueError('Battery API alias collision')
                overlay['roots'].append(dict(type='file',name=alias,**{'external-contents':str(ROOT/'drivers/EldenWifi/BatteryAdmission.h')}))
        if unit=='WcnPowerNative' and a.sideband_pins:
            for directory in directories:
                alias=str(Path(directory)/'SidebandPins.h')
                if alias in aliases:raise ValueError('Sideband API alias collision')
                overlay['roots'].append(dict(type='file',name=alias,**{'external-contents':str(ROOT/'drivers/EldenWifi/SidebandPins.h')}))
        vfs=out/(unit+'.overlay.json');vfs.write_text(json.dumps(overlay,indent=2)+'\n')
        cmd=list(report['command']);cmd[cmd.index('-ivfsoverlay')+1]=str(vfs);target=out/objname;cmd[cmd.index('-o')+1]=str(target)
        cwd=report.get('cwd',str(a.clean_build/'units/working/WcnPowerNative'))
        r=subprocess.run(cmd,cwd=cwd,capture_output=True);(out/(unit+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        adds={'_elden_wifi_battery_ready','_elden_wifi_battery_available'} if unit=='PmicClient' else set()
        if unit=='WcnPowerNative' and a.board_state:adds.add('_elden_wifi_board_state')
        if symbols(target,True)!=symbols(old,True)|adds:raise ValueError('Consumer export delta changed')
        refs=symbols(target,False);allowed=symbols(parent/'native.macho',True)|{'_elden_wifi_battery_ready','_elden_wifi_battery_available'}
        if refs-allowed:raise ValueError('Unresolved consumer imports: '+str(refs-allowed))
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',target],text=True);(out/(unit+'.asm')).write_text(asm)
        if any(n.endswith('/__mod_init_func') for n in sections(target)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('Consumer initializer/SIMD')
        for n,h in inherited.items():
            if sha(Path(n))!=h:raise ValueError('Retained consumer input changed')
        proofs[unit]=dict(compiled=True,source_sha256=sha(path),object_sha256=sha(target),parent_object_sha256=sha(old),command=cmd,
            overlay_sha256=sha(vfs),inherited_inputs=inherited,warnings=r.stderr.count(b'warning:'),changed_aliases=changed)
    links=read(parent/'link-command.json');oldar,=[Path(v.split(',')[-1]) for v in links if v.endswith('/libEldenPmicClient.a')]
    if sha(oldar)!=kr.get('retained_inputs',{}).get(str(oldar),sha(oldar)):raise ValueError('PMIC archive changed')
    folder=out/'pmic';folder.mkdir();names=[n for n in subprocess.check_output(['ar','t',oldar],text=True).splitlines() if not n.startswith('__.SYMDEF')]
    if len(names)!=len(set(names)) or names.count('PmicClient.o')!=1:raise ValueError('Ambiguous PMIC archive')
    retained={}
    for name in names:
        data=subprocess.check_output(['ar','p',oldar,name]);retained[name]=hashlib.sha256(data).hexdigest()
        if name=='PmicClient.o':
            if retained[name]!=proofs['PmicClient']['parent_object_sha256']:raise ValueError('Loaded PMIC parent differs')
            data=(out/'PmicClient.o').read_bytes()
        (folder/name).write_bytes(data)
    archive=folder/'libEldenPmicClient.a';subprocess.run(['ar','rcs',str(archive),*names],cwd=folder,env=dict(os.environ,ZERO_AR_DATE='1'),check=True)
    own=['tools/build_wifi_battery_admission.py','tools/test_wifi_battery_admission.py',
         'drivers/EldenWifi/BatteryAdmissionSource.py','drivers/EldenWifi/BatteryAdmission.h','drivers/EldenWifi/BatteryAdmission.inc',
         'drivers/EldenPmicGlink/PdStartupSource.py',
         'drivers/EldenPcie/MhiRuntimeSource.py','drivers/EldenSmmu/EarlySource.py',
         'drivers/EldenPcie/NativeHookSource.py','drivers/EldenPcie/PowerNativeSource.py',
         'drivers/EldenWifi/SharedNativeSource.py','drivers/EldenWifi/WlanPowerNative.inc',
         'drivers/EldenWifi/WlanPowerExports.inc','drivers/EldenWifi/WlanPower.h',
         'drivers/EldenWifi/WlanGpio.h','drivers/EldenBluetooth/WcnSharedPower.h',
         'drivers/EldenBluetooth/WcnSharedPower.inc','drivers/EldenBluetooth/WcnPower.c',
         'soc/sm8750/include/EldenWifiResources.h']
    if a.sideband_pins:own+=['tools/test_wifi_sideband_pins.py','drivers/EldenWifi/SidebandSource.py','drivers/EldenWifi/SidebandPins.h']
    if a.board_state:own+=['drivers/EldenWifi/BoardState.inc','tools/test_wifi_board_state.py']
    proof=dict(compiled=True,wifi_battery_runtime_trial=True,shared_owner=True,shared_owner_alias='ewt',shared_owner_mode=4,
        radio_only_no_charger_set=True,chemistry_two_gauges_epoch_age_checked=True,
        controls_and_charger_permission_unchanged=True,pmic_archive=str(archive),pmic_archive_sha256=sha(archive),parent_pmic_archive=str(oldar),
        parent_pmic_archive_sha256=sha(oldar),pmic_retained_members=retained,consumers=proofs,
        source_inputs={n:sha(ROOT/n) for n in own},hardware_tested=False)
    proof.update(sideband_pins_trial=a.sideband_pins,sideband_gpio_indices=[18,19,202] if a.sideband_pins else [],sideband_cold_before_votes=a.sideband_pins,sideband_unknown_state_retained=a.sideband_pins)
    proof.update(board_state_trial=a.board_state,board_state_no_device_controls=a.board_state,board_state_gpio_indices=[16,18,19,202] if a.board_state else [],board_state_rails=6 if a.board_state else 0)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({k:proof[k] for k in ['compiled','wifi_battery_runtime_trial','pmic_archive_sha256','hardware_tested']}))


if __name__=='__main__':main()
