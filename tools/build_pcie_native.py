"""Compile native root worker with the source-built XNU SDK and bind its providers."""
import argparse,hashlib,importlib.util,json,re,subprocess
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def defs(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(p).items() if not v[0]&0x0e}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['clean-build','root-build','power-build','wlan-build','wcn-build','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--endpoint-build',type=Path,help='Explicit CPU-only BAR/Peach extension')
    p.add_argument('--smmu-build',type=Path,help='Require the concrete early SMMU domain')
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);base=a.clean_build.resolve()
    generated={};native_source=ROOT/'drivers/EldenPcie/Native.cpp'
    if a.endpoint_build:
        spec=importlib.util.spec_from_file_location('endpoint_native',ROOT/'drivers/EldenPcie/EndpointNativeSource.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        folder=out/'source';folder.mkdir()
        derive=mod.generated
        if a.smmu_build:
            spec=importlib.util.spec_from_file_location('pcie_smmu_source',ROOT/'drivers/EldenSmmu/EarlySource.py')
            early=importlib.util.module_from_spec(spec);spec.loader.exec_module(early);derive=early.pcie_generated
        for name,data in derive().items():(folder/name).write_bytes(data);generated[name]=hashlib.sha256(data).hexdigest()
        native_source=folder/'Native.cpp'
    elif a.smmu_build:raise ValueError('SMMU requires endpoint stage')
    row=read(base/'units/result.json')['units']['WcnPowerNative'];cmd=list(row['command']);ov=read(Path(cmd[cmd.index('-ivfsoverlay')+1]));assert ov['fallthrough'] is False
    inherited={};directories=set();bindings=[]
    for item in ov['roots']:
        old=Path(item['external-contents']);h=sha(old);inherited[str(old)]=h
        if item['name'].endswith('/WcnPowerNative.cpp'):
            assert h=='5c16106e90622150686b90706fcfc8c674cf3c4d563ed782fd7d57fc864e2c72'
            item['external-contents']=str(native_source);directories.add(str(Path(item['name']).parent));bindings.append(item['name'])
    assert bindings
    files={n:ROOT/'drivers/EldenPcie'/n for n in ['Native.h','NativeRuntime.inc','NativeExports.inc','Root.h','Phy.h','Power.h','Pins.h']}
    files.update({'WlanPower.h':ROOT/'drivers/EldenWifi/WlanPower.h','EldenWifiResources.h':ROOT/'soc/sm8750/include/EldenWifiResources.h'})
    if a.endpoint_build:
        files.update({n:ROOT/'drivers/EldenPcie'/n for n in ['Endpoint.h','EndpointNative.h','EndpointNativeRuntime.inc']})
    if a.smmu_build:files['EldenWifiSmmuNative.h']=ROOT/'drivers/EldenSmmu/Native.h'
    existing={item['name']:item for item in ov['roots']}
    for directory in directories:
        for n,original in files.items():
            file=out/'source'/n if n in generated else original
            key=str(Path(directory)/n)
            if key in existing:
                assert sha(Path(existing[key]['external-contents']))==sha(file),'VFS collision '+key
            else:ov['roots'].append({'type':'file','name':key,'external-contents':str(file)})
    vfs=out/'overlay.json';write(vfs,ov);cmd[cmd.index('-ivfsoverlay')+1]=str(vfs);obj=out/'Native.o';cmd[cmd.index('-o')+1]=str(obj)
    r=subprocess.run(cmd,cwd=base/'units/working/WcnPowerNative',capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    expected_defs={'_elden_pcie_native_start','_elden_pcie_native_stop_begin','_elden_pcie_native_status','_sm8750_gcc_vote_owner'}
    if a.endpoint_build:expected_defs.add('_elden_pcie_endpoint_status')
    assert defs(obj)==expected_defs
    assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/'Native.asm').write_text(asm,encoding='utf-8')
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    roots=read(a.root_build/'result.json');powers=read(a.power_build/'result.json');wlan=read(a.wlan_build/'result.json');wcn=read(a.wcn_build/'result.json')
    assert wlan['root_worker_hooks'] and wlan['root_power_provider']
    assert bool(wlan.get('smmu_stop_hook'))==bool(a.smmu_build)
    for name,h in roots['source_sha256'].items():assert sha(ROOT/'drivers/EldenPcie'/name)==h,name
    for name,h in powers['source_sha256'].items():assert sha(ROOT/name)==h,name
    for name,h in wlan['source_inputs'].items():assert sha(ROOT/name)==h,name
    objects=[obj,a.root_build/'Root.o',a.root_build/'Phy.o',a.power_build/'Power.o',a.wlan_build/'WcnPowerNative.o',a.wcn_build/'WcnPower.o']
    expected=[None,roots['objects']['Root']['object_sha256'],roots['objects']['Phy']['object_sha256'],powers['plan_object_sha256'],wlan['object_sha256'],wcn['objects']['WcnPower']['object_sha256']]
    if a.endpoint_build:
        endpoint=read(a.endpoint_build/'result.json')
        for name,h in endpoint['source_sha256'].items():assert sha(ROOT/'drivers/EldenPcie'/name)==h,name
        objects.append(a.endpoint_build/'Endpoint.o');expected.append(endpoint['object_sha256'])
    if a.smmu_build:
        smmu=read(a.smmu_build/'result.json')
        for name,h in smmu['source_inputs'].items():assert sha(ROOT/name)==h,name
        objects.append(a.smmu_build/'SmmuNativeBinding.o');expected.append(smmu['binding_sha256'])
    for file,h in zip(objects,expected):
        if h:assert sha(file)==h,file
    rpmh=read(base/'units/result.json')['units']['Sm8750Rpmh'];rp=Path(rpmh['object']);assert sha(rp)==rpmh['sha256'];objects.append(rp)
    union=set().union(*(defs(f) for f in objects));pending=set().union(*(refs(f) for f in objects))-union
    required={'_elden_pcie_root_start','_elden_pcie_phy_start','_elden_wlan_root_power','_elden_pcie_power_plan','_elden_pcie_native_start','_elden_pcie_native_stop_begin'}
    if a.endpoint_build:required|={'_elden_pcie_endpoint_identify','_elden_wlan_power_confirm_endpoint','_elden_wlan_power_ready'}
    if a.smmu_build:required|={'_elden_wifi_smmu_ready','_elden_wifi_smmu_status','_elden_wifi_smmu_stop_begin'}
    assert required<=union and not required&pending
    target=out/'PcieNativeBinding.o';link=['xcrun','ld','-r','-arch','arm64','-platform_version','ios','17.0','17.0','-o',str(target),*map(str,objects)]
    linked=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(linked.stdout+linked.stderr);linked.check_returncode()
    assert defs(target)==union and refs(target)==pending
    inputs={str(p.relative_to(ROOT)):sha(p) for p in files.values()};inputs['drivers/EldenPcie/Native.cpp']=sha(ROOT/'drivers/EldenPcie/Native.cpp')
    if a.endpoint_build:inputs['drivers/EldenPcie/EndpointNativeSource.py']=sha(ROOT/'drivers/EldenPcie/EndpointNativeSource.py')
    if a.smmu_build:inputs['drivers/EldenSmmu/EarlySource.py']=sha(ROOT/'drivers/EldenSmmu/EarlySource.py')
    report={'compiled':True,'object_sha256':sha(obj),'binding_sha256':sha(target),'command':cmd,'link':link,'source_inputs':inputs,'inherited_input_count':len(inherited),
            'input_objects':{str(f):sha(f) for f in objects},'remaining_imports':sorted(pending),'warnings':r.stderr.count(b'warning:'),'scalar':True,
            'native_root_worker_bound':True,'endpoint_worker_bound':bool(a.endpoint_build),'smmu_domain_required':bool(a.smmu_build),'generated_sources':generated,
            'kernel_linked':False,'boot_created':False,'hardware_tested':False}
    write(out/'result.json',report);print(json.dumps({k:v for k,v in report.items() if k in ['compiled','object_sha256','binding_sha256','warnings','kernel_linked']}))
if __name__=='__main__':main()
