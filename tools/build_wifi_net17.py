"""Compile the proven Sheng iOS17 BSD bridge with frozen XNU headers.

This component does not boot hardware, replace CE/WMI code or enable a radio.
The native runtime composition and full kernel integration have separate gates.
"""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/net'))
from Net17Source import source


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('clean-build','reference-kernel','llvm','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();base=args.clean_build.resolve();out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False);net=ROOT/'drivers/EldenWifi/net'
    generated=out/'EldenWifiNet17.cpp';generated.write_bytes(source())
    row=json.loads((base/'units/result.json').read_text())['units']['WcnPowerNative']
    command=list(row['command']);overlay=json.loads(Path(command[command.index('-ivfsoverlay')+1]).read_text())
    assert overlay['fallthrough'] is False
    inherited={};directories=set()
    # Supply the public, reconstructed XNU header namespaces as well as the
    # captured transitive headers. The old GPIO/PCIe unit did not include BSD
    # network headers, so its strict overlay alone cannot resolve this source.
    names={item['name'] for item in overlay['roots']}
    virtual=json.loads((ROOT/'profiles/v91/native-build/plan.json').read_text())['virtual_root'].rstrip('/')
    exported_roots=[item['name'] for item in overlay['roots'] if item['name'].endswith('/IOKit/IOLib.h')]
    exported_roots=[name[:-len('IOKit/IOLib.h')] for name in exported_roots]
    header_roots=set(exported_roots)
    for i,value in enumerate(command[:-1]):
        if value=='-I' and '/EXPORT_HDRS/' in command[i+1]:header_roots.add(command[i+1].rstrip('/')+'/')
    for subtree in ('bsd','osfmk','libkern','iokit','pexpert','libsa','EXTERNAL_HEADERS'):
        tree=base/'source/xnu'/subtree
        for path in tree.rglob('*.h'):
            relative=path.relative_to(tree).as_posix()
            aliases=[virtual+'/research/cpu-full-20261111/tree/.cache/xnu-work/'+subtree+'/'+relative]
            export_relative=relative
            if relative.startswith('skywalk/') and '/' in relative[len('skywalk/'):]:
                export_relative='skywalk/'+path.name
            aliases += [header_root+export_relative for header_root in header_roots]
            for alias in aliases:
                if alias not in names:
                    overlay['roots'].append(dict(type='file',name=alias,**{'external-contents':str(path)}));names.add(alias)
            inherited[str(path)]=sha(path)
    for item in overlay['roots']:
        path=Path(item['external-contents']);inherited[str(path)]=sha(path)
        if item['name'].endswith('/WcnPowerNative.cpp'):
            directories.add(str(Path(item['name']).parent));item['external-contents']=str(generated)
    assert directories
    for directory in directories:
        for name,path in [('nw_abi.h',net/'upstream17/nw_abi.h'),('EldenNet17.h',net/'EldenNet17.h')]:
            alias=str(Path(directory)/name)
            if any(item['name']==alias for item in overlay['roots']):raise ValueError('Network header alias collision')
            overlay['roots'].append(dict(type='file',name=alias,**{'external-contents':str(path)}))
    vfs=out/'overlay.json';vfs.write_text(json.dumps(overlay,indent=2)+'\n')
    command[command.index('-ivfsoverlay')+1]=str(vfs)
    command[command.index('-main-file-name')+1]='EldenWifiNet17.cpp'
    raw=out/'EldenWifiNet17.o';command[command.index('-o')+1]=str(raw)
    result=subprocess.run(command,cwd=base/'units/working/WcnPowerNative',capture_output=True)
    (out/'compile.log').write_bytes(result.stdout+result.stderr);result.check_returncode()
    # Clang names the initializer after the source's virtual spelling even
    # when main-file-name is explicit. Read the one actual symbol, then rename.
    listed=subprocess.check_output([str(args.llvm/'llvm-nm'),str(raw)],text=True)
    initializers=re.findall(r'\b[ts] (__GLOBAL__sub_I_[^\s]+)$',listed,re.M)
    if len(initializers)!=1:raise ValueError('Expected one actual network initializer')
    init=initializers[0]
    before=sections(raw)
    assert any(name.endswith('/__mod_init_func') for name in before)
    obj=out/'EldenWifiNet17.late.o'
    objcopy=[str(args.llvm/'llvm-objcopy'),'--remove-section=__DATA,__mod_init_func',
        '--globalize-symbol='+init,'--redefine-sym='+init+'=_elden_wifi_net_static_init',str(raw),str(obj)]
    subprocess.run(objcopy,check=True)
    after=sections(obj)
    assert not any(name.endswith('/__mod_init_func') for name in after)
    assert all(after[name]==value for name,value in before.items() if not name.endswith('/__mod_init_func'))
    symbols=global_symbols(obj);definitions={name for name,row in symbols.items() if row[0]&0x0e}
    imports={name for name,row in symbols.items() if not row[0]&0x0e}
    own={'_elden_wifi_net_start','_elden_wifi_net_stop_begin','_elden_wifi_net_drain','_elden_wifi_net_pump','_elden_wifi_net_static_init'}
    assert own<=definitions
    runtime={'_elden_wifi_net_admit','_native_wifi_logf','_sheng_wifi_wake'}
    available={name for name,row in global_symbols(args.reference_kernel).items() if row[0]&0x0e}|runtime
    missing=imports-available
    if missing:raise ValueError('Missing actual iOS17 imports: '+', '.join(sorted(missing)))
    asm=subprocess.check_output([str(args.llvm/'llvm-objdump'),'-dr',obj],text=True)
    (out/'EldenWifiNet17.asm').write_text(asm)
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    for path,digest in inherited.items():assert sha(Path(path))==digest,path
    names=['tools/build_wifi_net17.py','drivers/EldenWifi/net/Net17Source.py',
        'drivers/EldenWifi/net/EldenNet17.h','drivers/EldenWifi/net/upstream17/source.json',
        'drivers/EldenWifi/net/upstream17/WifiNet.cpp','drivers/EldenWifi/net/upstream17/nw_abi.h']
    proof=dict(compiled=True,source_sha256=sha(generated),raw_object_sha256=sha(raw),object_sha256=sha(obj),
        source_inputs={name:sha(ROOT/name) for name in names},command=command,objcopy_command=objcopy,
        exported_symbols=sorted(definitions),imports=sorted(imports),native_provider_imports=sorted(imports&runtime),
        imports_missing=[],compiler_warnings=result.stderr.count(b'warning:'),late_initializer_owned=True,
        other_sections_preserved=True,scalar=True,hardware_tested=False,full_kernel_linked=False,
        inherited_inputs=inherited)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:proof[k] for k in
        ('compiled','source_sha256','object_sha256','compiler_warnings','imports_missing','hardware_tested')}))


if __name__=='__main__':main()
