"""Replay the current kern_exec command with the qualified Wi-Fi service assets.

Builds one core object only. A separate full link/boot audit is required.
"""
import argparse, hashlib, importlib.util, json, re, subprocess, sys
from pathlib import Path
from replay_xnu_objects import global_symbols, sections
ROOT = Path(__file__).resolve().parents[1]
CORE = '3d8e2c993eb5a4056ab96b9b97120cde4699c97090de1dcaf5710c7101d0aa30'
RUNTIME = '4a00bd6d29b6ee5c2c111605664d0fadc3335ba4e2e730ec213c78d96ed5ddbd'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
def write(p, value): p.write_text(json.dumps(value, indent=2)+'\n')
def exports(p): return {k for k,v in global_symbols(p).items() if v[0]&0x0e}

def main():
    if sys.flags.optimize: raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['core-build','clean-build','service-assets','llvm','output']:
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--owner-launch',action='store_true',help='Exact signed-helper rule for the observed category6 RAM-overlay launch failure')
    a=p.parse_args(); core=a.core_build.resolve(); assets=a.service_assets.resolve(); out=a.output.resolve()
    row=read(core/'result.json')['objects']['kern_exec']
    old=core/'kern_exec.o'; assert sha(old)==row['sha256']==CORE
    report=read(assets/'result.json')
    assert report['prepared'] and report['old_jobs_unchanged']==561 and report['jobs']==562
    assert report['new_trust_entries']==2 and report['signatures_verified'] and report['host_xpc_passed']
    assert not report['credentials_included']
    for name,key in [('EldenWifiServiceAssets.h','header_sha256'),('launchd.plist','cache_sha256'),
        ('launchd.plist.sig','signature_sha256'),('runtime.trustcache','trust_sha256'),
        ('unixnu-wpa_supplicant','helper_sha256'),('wpa_supplicant.conf','config_sha256')]:
        assert sha(assets/name)==report[key],name
    assert sha(ROOT/'tools/build_wifi_service_assets.py')==report['source_sha256']
    spec=importlib.util.spec_from_file_location('wifi_service_source',ROOT/'drivers/EldenWifi/ServiceRuntimeSource.py')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    out.mkdir(parents=True,exist_ok=False)
    rt=out/'EldenBtRuntime.inc'; rt.write_bytes(mod.source())
    header=out/'EldenBtLaunchCache.h'; header.write_bytes(mod.cache_header())
    cmd=list(row['command']); ov=read(Path(cmd[cmd.index('-ivfsoverlay')+1])); assert ov['fallthrough'] is False
    inherited={}; changes=[]; additions={}; replaced_runtime=0; replaced_header=0;owner_common=None
    if a.owner_launch:
        spec=importlib.util.spec_from_file_location('wifi_owner_source',ROOT/'drivers/EldenWifi/OwnerLaunchSource.py')
        owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
    for item in ov['roots']:
        f=Path(item['external-contents']); inherited[str(f)]=sha(f)
        if a.owner_launch and item['name'].endswith('/EldenIconCpuCommon.inc'):
            owner_common=out/'EldenIconCpuCommon.inc';data=owner.common(f.read_bytes())
            if owner_common.exists():assert owner_common.read_bytes()==data
            else:owner_common.write_bytes(data)
            item['external-contents']=str(owner_common);changes.append(item['name'])
        if item['name'].endswith('/EldenBtRuntime.inc'):
            assert sha(f)==RUNTIME
            item['external-contents']=str(rt); changes.append(item['name']); replaced_runtime+=1
        if item['name'].endswith('/EldenBtLaunchCache.h'):
            assert 'elden_bt_launch_cache' in f.read_text()
            item['external-contents']=str(header); changes.append(item['name']); replaced_header+=1
            virtual=str(Path(item['name']).parent/'EldenWifiServiceAssets.h')
            additions[virtual]={'type':'file','name':virtual,'external-contents':str(assets/'EldenWifiServiceAssets.h')}
    assert replaced_runtime and replaced_header
    assert bool(owner_common)==a.owner_launch
    # Include lookup also uses the physical directory of the replacement.
    virtual=str(out/'EldenWifiServiceAssets.h')
    additions[virtual]={'type':'file','name':virtual,'external-contents':str(assets/'EldenWifiServiceAssets.h')}
    ov['roots']+=list(additions.values())
    vfs=out/'kern_exec.overlay.json';write(vfs,ov);cmd[cmd.index('-ivfsoverlay')+1]=str(vfs)
    obj=out/'kern_exec.o';cmd[cmd.index('-o')+1]=str(obj)
    r=subprocess.run(cmd,cwd=a.clean_build/'units/working/kern_exec',capture_output=True)
    (out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    assert exports(obj)==exports(old)|{'_elden_wifi_assets_ready'}
    assert not any(k.endswith('/__mod_init_func') for k in sections(obj))
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'kern_exec.asm').write_text(asm)
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    for name,h in inherited.items(): assert sha(Path(name))==h,name
    sources=['tools/build_wifi_service_core.py','tools/build_wifi_service_assets.py',
        'drivers/EldenWifi/ServiceRuntimeSource.py','drivers/EldenWifi/ServiceRuntime.inc',
        'drivers/EldenBluetooth/runtime/LaunchCacheSource.py','drivers/EldenBluetooth/runtime/LaunchCache.inc',
        'drivers/EldenBluetooth/runtime/Runtime.inc']
    if a.owner_launch:sources+=['drivers/EldenWifi/OwnerLaunchSource.py','drivers/EldenBluetooth/runtime/OwnerLaunch.inc']
    result={'compiled':True,'object_sha256':sha(obj),'base_object_sha256':CORE,'command':cmd,
        'runtime_sha256':sha(rt),'changed_bindings':changes,'inherited_sources':inherited,
        'source_inputs':{name:sha(ROOT/name) for name in sources},'assets':report,
        'new_export':'_elden_wifi_assets_ready','scalar':True,'warnings':r.stderr.count(b'warning:'),
        'owner_launch_required':a.owner_launch,'owner_common_sha256':sha(owner_common) if owner_common else None,
        'full_kernel_linked':False,'hardware_tested':False}
    write(out/'result.json',result);print(json.dumps({k:result[k] for k in ['compiled','object_sha256','warnings']}))
if __name__=='__main__':main()
