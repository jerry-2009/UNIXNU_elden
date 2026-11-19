"""Rebuild the retained service worker with the iOS17 network bridge callbacks.

Original runtime stop and physical-fence code is retained. No filtered response
diagnostic candidate or device operation is part of this component.
"""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/net'))
from Net17NativeSource import generated


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def defs(path):return {n for n,v in global_symbols(path).items() if v[0]&0x0e}
def refs(path):return {n for n,v in global_symbols(path).items() if not v[0]&0x0e}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('parent-native','net-build','reference-kernel','clean-build','llvm','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--mhi-hold',action='store_true',help='Expose only the bounded opt-in MHI power-state lease')
    group.add_argument('--umac-hold',action='store_true',help='Expose only the OEM MHI+UMAC wake trial')
    parser.add_argument('--dma-inspect',action='store_true',help='Expose bounded first-failure DMA inspection on the UMAC worker')
    args=parser.parse_args();parent=args.parent_native.resolve();out=args.output.resolve()
    prior=json.loads((parent/'result.json').read_text());net=json.loads((args.net_build/'result.json').read_text())
    if not prior.get('service_scan') or not prior.get('platform_physical_fence_preserved') or not net['compiled']:
        raise ValueError('Qualified service-scan worker and net bridge required')
    if sha(parent/'Native.o')!=prior['object_sha256'] or sha(args.net_build/'EldenWifiNet17.late.o')!=net['object_sha256']:
        raise ValueError('Parent component identity mismatch')
    out.mkdir(parents=True,exist_ok=False);source=out/'source';source.mkdir()
    new=generated(args.mhi_hold,args.umac_hold,args.dma_inspect)
    for name,data in new.items():(source/name).write_bytes(data)
    private=parent/'EldenWifiFactoryMac.h'
    if sha(private)!=prior['private_assets']['header_sha256']:raise ValueError('Original factory identity input changed')
    command=list(prior['command']);overlay=json.loads((parent/'overlay.json').read_text());inherited={};bindings=[];directories=set()
    for item in overlay['roots']:
        old=Path(item['external-contents']);inherited[str(old)]=sha(old)
        name=old.name
        if old==parent/'source/Native.cpp':name='Native.cpp'
        if name in new:
            # ControlScan/trace fragments and every hardware file stay exact.
            expected=(parent/'source'/name).read_bytes()
            if old.read_bytes()!=expected:raise ValueError('Unexpected retained worker file: '+name)
            item['external-contents']=str(source/name);bindings.append(item['name']);directories.add(str(Path(item['name']).parent))
    if not bindings or overlay.get('fallthrough') is not False:raise ValueError('Strict captured worker required')
    names={item['name'] for item in overlay['roots']}
    for directory in directories:
        alias=str(Path(directory)/'EldenNet17.h')
        if alias in names:raise ValueError('Network API alias collision')
        overlay['roots'].append(dict(type='file',name=alias,**{'external-contents':str(ROOT/'drivers/EldenWifi/net/EldenNet17.h')}));names.add(alias)
        if args.dma_inspect:
            for file in ('DmaInspect.h','DmaInspect.inc'):
                alias=str(Path(directory)/file)
                if alias in names:raise ValueError('DMA inspection alias collision')
                overlay['roots'].append(dict(type='file',name=alias,**{'external-contents':str(ROOT/'drivers/EldenWifi'/file)}));names.add(alias)
    vfs=out/'overlay.json';vfs.write_text(json.dumps(overlay,indent=2)+'\n')
    command[command.index('-ivfsoverlay')+1]=str(vfs);command[command.index('-o')+1]=str(out/'Native.o')
    result=subprocess.run(command,cwd=args.clean_build/'units/working/WcnPowerNative',capture_output=True)
    (out/'compile.log').write_bytes(result.stdout+result.stderr);result.check_returncode()
    obj=out/'Native.o';additions={'_elden_wifi_net_admit','_native_wifi_logf','_sheng_wifi_wake'}
    if args.mhi_hold:additions.add('_elden_wifi_mhi_hold_requested')
    if args.umac_hold:additions.add('_elden_wifi_umac_hold_requested')
    if args.dma_inspect:additions.add('_elden_wifi_dma_inspect')
    if defs(obj)!=defs(parent/'Native.o')|additions:raise ValueError('Unexpected worker exports')
    bridge=defs(args.net_build/'EldenWifiNet17.late.o');available=defs(args.reference_kernel)|bridge
    missing=refs(obj)-available
    if missing:raise ValueError('Unresolved real worker imports: '+', '.join(sorted(missing)))
    if any(n.endswith('/__mod_init_func') for n in sections(obj)):raise ValueError('Unexpected worker initializer')
    asm=subprocess.check_output([str(args.llvm/'llvm-objdump'),'-dr',obj],text=True)
    (out/'Native.asm').write_text(asm)
    if re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('Unexpected SIMD')
    for name,digest in inherited.items():
        if sha(Path(name))!=digest:raise ValueError('Retained input changed: '+name)
    own=['tools/build_wifi_net17_native.py','drivers/EldenWifi/net/Net17NativeSource.py','drivers/EldenWifi/net/EldenNet17.h']
    if args.dma_inspect:own+=['drivers/EldenWifi/DmaInspect.h','drivers/EldenWifi/DmaInspect.inc']
    proof=dict(compiled=True,object_sha256=sha(obj),base_object_sha256=prior['object_sha256'],
        source_inputs={name:sha(ROOT/name) for name in own},retained_parent_source_inputs=prior['source_inputs'],
        generated_sources={name:hashlib.sha256(data).hexdigest() for name,data in new.items()},
        private_assets=prior['private_assets'],net_object_sha256=net['object_sha256'],
        source_bindings=bindings,command=command,imports_missing=[],added_exports=sorted(additions),
        native_net_imports=sorted(refs(obj)&bridge),warnings=result.stderr.count(b'warning:'),
        no_initializers=True,scalar=True,platform_physical_fence_preserved=True,
        no_ce_wmi_firmware_changes=True,mhi_hold_trial=args.mhi_hold,umac_hold_trial=args.umac_hold,
        ce3_inspect_trial=args.dma_inspect,
        full_kernel_linked=False,hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({key:proof[key] for key in ('compiled','object_sha256','warnings','imports_missing','hardware_tested')}))


if __name__=='__main__':main()
