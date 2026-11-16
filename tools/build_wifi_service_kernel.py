"""Link one service core and one native worker over the verified v173 kernel."""
import argparse,hashlib,io,json,os,shutil,subprocess,sys,tarfile
from pathlib import Path
from replay_xnu_objects import global_symbols
from link_v91_kernel import verify_original_executables
from audit_entry_relocation import entry
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def defs(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['parent-build','service-core','service-native','service-assets','clean-build','original-kernelcache','output']:
        p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();parent=a.parent_build.resolve();out=a.output.resolve();prior=read(parent/'result.json')
    assert prior['profile']=='wifi-platform-fence' and prior['platform_physical_fence']
    for name in ['native','kernel']:assert sha(parent/(name+'.macho'))==prior[name+'_sha256']
    core=read(a.service_core/'result.json');native=read(a.service_native/'result.json');assets=read(a.service_assets/'result.json')
    assert sha(a.service_core/'kern_exec.o')==core['object_sha256'] and sha(a.service_native/'Native.o')==native['object_sha256']
    assert assets==core['assets'] and native['platform_physical_fence_preserved'] and native['service_admission']
    inputs={**prior['source_inputs'],**core['source_inputs'],**native['source_inputs']}
    for name,h in inputs.items():assert sha(ROOT/name)==h,name
    out.mkdir(parents=True,exist_ok=False);folder=out/'pcie';folder.mkdir()
    cmd=read(parent/'link-command.json');archives=[x.split(',')[-1] for x in cmd if x.endswith('/libEldenPcie.a')];assert len(archives)==1
    oldar=Path(archives[0]);names=[n for n in subprocess.check_output(['ar','t',oldar],text=True).splitlines() if not n.startswith('__.SYMDEF')]
    assert len(names)==len(set(names)) and names.count('Native.o')==1
    members={};original_members={}
    for name in names:
        old=subprocess.check_output(['ar','p',oldar,name]);original_members[name]=hashlib.sha256(old).hexdigest()
        data=(a.service_native/'Native.o').read_bytes() if name=='Native.o' else old
        if name=='Native.o':assert sha(Path(prior['component_objects'][name]['path']))==native['base_object_sha256']
        (folder/name).write_bytes(data);members[name]=hashlib.sha256(data).hexdigest()
    archive=folder/'libEldenPcie.a';subprocess.run(['ar','rcs',str(archive),*names],cwd=folder,env=dict(os.environ,ZERO_AR_DATE='1'),check=True)
    for name in names:
        actual=subprocess.check_output(['ar','p',archive,name]);expected=(folder/name).read_bytes()
        assert actual==expected or actual==expected+b'\n'*((-len(expected))%8),name
    lines=(parent/'link.filelist').read_text().splitlines();cores=[n for n in lines if Path(n).name=='kern_exec.o'];assert len(cores)==1
    assert sha(Path(cores[0]))==core['base_object_sha256']
    inherited={n:sha(Path(n)) for n in lines}
    for arg in cmd:
        name=arg.split(',')[-1]
        if name.endswith(('.o','.a')) and Path(name).is_file():inherited[name]=sha(Path(name))
    filelist=out/'link.filelist';filelist.write_text('\n'.join(str(a.service_core/'kern_exec.o') if n==cores[0] else n for n in lines)+'\n')
    oldlists=[x.split(',')[-1] for x in cmd if x.endswith('link.filelist')];assert len(oldlists)==1
    cmd=[x.replace(str(parent/'native.macho'),str(out/'native.macho')).replace(str(oldar),str(archive)).replace(oldlists[0],str(filelist)) for x in cmd]
    write(out/'link-command.json',cmd);env=dict(os.environ,CCC_OVERRIDE_OPTIONS='+-Wno-unknown-warning-option');env.pop('SDKROOT',None)
    with (out/'link.log').open('x') as f:subprocess.run(cmd,cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    assert defs(out/'native.macho')==defs(parent/'native.macho')|{'_elden_wifi_assets_ready'}
    for name,h in inherited.items():assert sha(Path(name))==h,name
    pre=read(ROOT/'profiles/v91/image-build/plan.json')['prelink'];assert sha(a.original_kernelcache)==pre['original_kernelcache_sha256']
    kit=out/'prelink-tool';kit.mkdir()
    with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','-C',str(a.clean_build/'dependencies/XnuPrelink'),'archive',pre['commit']]))) as t:t.extractall(kit,filter='data')
    cmd=[sys.executable,str(kit/'emit_prelink.py'),'--kernel',str(out/'native.macho'),'--prelinked',str(a.original_kernelcache.resolve()),'--slide='+pre['slide'],'--output',str(out/'kernel.macho')]
    for n in pre['roots']:cmd+=['--root',n]
    for n in pre['early_security_initializers']:cmd+=['--early-security-init',n]
    with (out/'prelink.log').open('x') as f:subprocess.run(cmd,cwd=out,stdout=f,stderr=subprocess.STDOUT,check=True)
    assert verify_original_executables(out/'kernel.macho',read(out/'kernel.json'),pre['original_executable_sha256'])==30
    before=entry((parent/'kernel.macho').read_bytes());after=entry((out/'kernel.macho').read_bytes())
    assert before[2]==after[2] and before[1]-before[0]==after[1]-after[0]==7124
    runtime=out/'runtime';shutil.copytree(parent/'runtime',runtime)
    for name in ['runtime.trustcache','launchd.plist','launchd.plist.sig','EldenBtLaunchCache.h']:shutil.copyfile(runtime/name,runtime/('base-'+name))
    for name in ['runtime.trustcache','launchd.plist','launchd.plist.sig','EldenWifiServiceAssets.h','unixnu-wpa_supplicant','wpa_supplicant.conf','org.unixnu.wifi.supplicant.plist']:
        shutil.copyfile(a.service_assets/name,runtime/name)
    write(runtime/'wifi-service-assets.json',assets)
    for name in ['tools/build_wifi_service_kernel.py','tools/wifi_service_boot.py','tools/charge_verification_boot.py','tools/bt_runtime_boot.py']:
        inputs[name]=sha(ROOT/name)
    if native.get('control_trace') and not core.get('owner_launch_required'):raise ValueError('Control trace requires the qualified owner rule')
    result=dict(prior);result.update(profile='wifi-service-control-trace' if native.get('control_trace') else 'wifi-service-owner' if core.get('owner_launch_required') else 'wifi-service',kernel_sha256=sha(out/'kernel.macho'),native_sha256=sha(out/'native.macho'),
        source_inputs=inputs,changed_core_objects=1,changed_native_objects=1,added_native_objects=0,core_filelist_unchanged=False,
        core=core,service_native=native,service_assets=assets,base_report=prior,
        service_archive_members=members,base_archive_members=original_members,inherited_inputs=inherited,
        parent_kernel_sha256=prior['kernel_sha256'],entry_return_target=hex(after[1]),
        endpoint_generated_sources=native['generated_sources'],boot_packaged=False,hardware_tested=False)
    result['component_objects']=dict(prior['component_objects']);result['component_objects']['Native.o']={'path':str(a.service_native/'Native.o'),'sha256':native['object_sha256']}
    write(out/'result.json',result);print(json.dumps({k:result[k] for k in ['profile','kernel_sha256','original_apple_executables_hashed']}))
if __name__=='__main__':main()
