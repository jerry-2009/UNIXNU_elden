"""Compose complete station/data/802.1X on the hardware-accepted portable scan."""
import argparse,hashlib,json,io,os,subprocess,sys,tarfile
from pathlib import Path
from replay_xnu_objects import global_symbols
from link_v91_kernel import native_identity,verify_original_executables
from audit_entry_relocation import entry
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def defs(p):return {n for n,v in global_symbols(Path(p)).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(Path(p)).items() if not v[0]&0x0e}
def write(p,r):Path(p).write_text(json.dumps(r,indent=2)+'\n')
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['parent-build','runtime-build','native-build','core-build','assets','clean-build','original-kernelcache','output']:
        p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();parent,out=a.parent_build.resolve(),a.output.resolve();prior=read(parent/'result.json');runtime=read(a.runtime_build/'result.json');worker=read(a.native_build/'result.json');core=read(a.core_build/'result.json');assets=read(a.assets/'result.json')
    from wifi_station import qualify_runtime,qualify_native
    qualify_runtime(runtime);qualify_native(worker,a.native_build)
    original=runtime['base'] if runtime.get('station_hif') else runtime
    if original['scan_parent']!=prior['portable_scan_runtime'] or core['base']!=prior['core'] or worker['base']!=prior['network_worker'] or core['assets']!=assets:
        raise ValueError('Station actual component parents differ')
    for name in ['native','kernel']:
        if sha(parent/(name+'.macho'))!=prior[name+'_sha256']:raise ValueError('Station parent changed')
    out.mkdir(parents=True,exist_ok=False);archive=out/'pcie';archive.mkdir();cmd=read(parent/'link-command.json')
    oldar,=[Path(v.split(',')[-1]) for v in cmd if v.endswith('/libEldenPcie.a')]
    names=[v for v in subprocess.check_output(['ar','t',str(oldar)],text=True).splitlines() if not v.startswith('__.SYMDEF')]
    before={};after={}
    for name in names:
        data=subprocess.check_output(['ar','p',str(oldar),name]);before[name]=hashlib.sha256(data).hexdigest()
        if name=='Native.o':data=(a.native_build/name).read_bytes()
        if name=='WifiRuntimeMsiBinding.o':data=(a.runtime_build/name).read_bytes()
        (archive/name).write_bytes(data);after[name]=hashlib.sha256(data).hexdigest()
    newar=archive/'libEldenPcie.a';subprocess.run(['ar','rcs',str(newar),*names],cwd=archive,env=dict(os.environ,ZERO_AR_DATE='1'),check=True)
    original=(parent/'link.filelist').read_text();oldcore=Path(core['base']['command'][core['base']['command'].index('-o')+1])
    if original.splitlines().count(str(oldcore))!=1:raise ValueError('Station kern_exec replacement not unique')
    newlist=original.replace(str(oldcore),str(a.core_build/'kern_exec.o'),1);(out/'link.filelist').write_text(newlist)
    cmd=[v.replace(str(parent/'native.macho'),str(out/'native.macho')).replace(str(oldar),str(newar)).replace(str(parent/'link.filelist'),str(out/'link.filelist')) for v in cmd]
    write(out/'link-command.json',cmd)
    env=dict(os.environ,CCC_OVERRIDE_OPTIONS='+-Wno-unknown-warning-option');env.pop('SDKROOT',None)
    with (out/'link.log').open('xb') as f:subprocess.run(cmd,cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    binding=a.runtime_build/'WifiRuntimeMsiBinding.o';oldbinding=Path(prior['component_objects']['WifiRuntimeMsiBinding.o']['path'])
    expected=defs(parent/'native.macho')| (defs(binding)-defs(oldbinding))|{'_elden_wifi_station_native_start','_elden_wifi_station_native_stop'}
    if defs(out/'native.macho')!=expected or refs(out/'native.macho')!=refs(parent/'native.macho'):raise ValueError('Station full native interface differs')
    pre=read(ROOT/'profiles/v91/image-build/plan.json')['prelink'];kit=out/'prelink-tool';kit.mkdir()
    data=subprocess.check_output(['git','-C',str(a.clean_build/'dependencies/XnuPrelink'),'archive',pre['commit']])
    with tarfile.open(fileobj=io.BytesIO(data)) as t:t.extractall(kit,filter='data')
    call=[sys.executable,str(kit/'emit_prelink.py'),'--kernel',str(out/'native.macho'),'--prelinked',str(a.original_kernelcache),'--slide='+pre['slide'],'--output',str(out/'kernel.macho')]
    for name in pre['roots']:call+=['--root',name]
    for name in pre['early_security_initializers']:call+=['--early-security-init',name]
    with (out/'prelink.log').open('xb') as f:subprocess.run(call,cwd=out,stdout=f,stderr=subprocess.STDOUT,check=True)
    if verify_original_executables(out/'kernel.macho',read(out/'kernel.json'),pre['original_executable_sha256'])!=30:raise ValueError('Station Apple executable changed')
    oldentry=entry((parent/'kernel.macho').read_bytes());newentry=entry((out/'kernel.macho').read_bytes())
    if oldentry[1]-oldentry[0]!=7124 or newentry[1]-newentry[0]!=7124:raise ValueError('Station entry changed')
    s,c,h=native_identity(out/'native.macho');write(out/'native-contract.json',dict(sections=s,commands=c,symbols=h))
    from shutil import copytree,copyfile
    copytree(parent/'runtime',out/'runtime')
    for name in ['launchd.plist','launchd.plist.sig','EldenWifiServiceAssets.h','unixnu-wpa_supplicant','wpa_supplicant.conf','runtime.trustcache','org.unixnu.wifi.supplicant.plist']:
        copyfile(a.assets/name,out/'runtime'/name)
    write(out/'runtime/wifi-service-assets.json',assets)
    policy=['tools/build_wifi_station_kernel.py','tools/wifi_station.py','tools/wifi_network17_boot.py','tools/charge_verification_boot.py']
    inputs=dict(prior['source_inputs']);inputs.update(runtime['source_inputs']);inputs.update(worker['source_inputs']);inputs.update(core['source_inputs']);inputs.update(assets['source_inputs']);inputs.update({n:sha(ROOT/n) for n in policy})
    # Asset declarations cover a userland ABI whose comment/declaration-only
    # evolution can leave the executable source and public wire identical.
    # Require all effective native/runtime pins to win; verify separately that
    # the signed helper/source has not changed in the asset qualifier.
    inputs.update(runtime['source_inputs']);inputs.update(worker['source_inputs'])
    for n,h in inputs.items():
        if sha(ROOT/n)!=h:raise ValueError('Station consumed input changed: '+n)
    components=dict(prior['component_objects']);components['Native.o']=dict(path=str(a.native_build/'Native.o'),sha256=worker['object_sha256']);components['WifiRuntimeMsiBinding.o']=dict(path=str(binding),sha256=runtime['binding_sha256'])
    proof=dict(prior);proof.update(station_trial=True,portable_scan_trial=False,station_runtime=runtime,station_worker=worker,station_parent=prior,
        station_parent_kernel_sha256=prior['kernel_sha256'],station_parent_native_sha256=prior['native_sha256'],kernel_sha256=sha(out/'kernel.macho'),native_sha256=sha(out/'native.macho'),
        source_inputs=inputs,component_objects=components,core=core,service_assets=assets,original_physical_return_preserved=True,entry_delta=7124,
        entry_return_target=hex(newentry[1]),original_apple_executables_hashed=30,changed_station_core_objects=1,
        station_archive_before=before,station_archive_after=after,native_identity_contract=dict(path='native-contract.json',sha256=sha(out/'native-contract.json'),native_sha256=sha(out/'native.macho')),
        station_association_accepted=False,hardware_tested=False)
    write(out/'result.json',proof);print(json.dumps({k:proof[k] for k in ['station_trial','kernel_sha256','native_sha256','hardware_tested']}))
if __name__=='__main__':main()
