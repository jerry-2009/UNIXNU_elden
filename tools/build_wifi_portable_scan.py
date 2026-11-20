"""Build the fixed successful SM8750 portable scan over the OEM firmware path.

All paths are explicit inputs; no hidden workbench, WSL or v99 directory.
Four selected C units and one new scalar C++ unit;121 original units retained.
This tool does not sign, flash, change Goal state or claim hardware acceptance.
"""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
PORT=ROOT/'drivers/EldenWifi/portable'
sys.path.insert(0,str(PORT))
from PortableScanPatch import EXPECTED,patch

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def defs(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(p).items() if not v[0]&0x0e}
def execute(cmd,out,name):
    r=subprocess.run(cmd,cwd=out,capture_output=True)
    (out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode();return r

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime-build','parent-build','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base,parent,out=a.runtime_build.resolve(),a.parent_build.resolve(),a.output.resolve()
    prior=read(parent/'result.json');original=read(base/'result.json')
    if not prior.get('eager_memory_trial') or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:
        raise ValueError('Require the fixed eager-memory parent')
    lock=read(PORT/'upstream/source.json')
    for row in lock['files']:
        if sha(PORT/'upstream'/row['path'])!=row['sha256']:raise ValueError('Portable donor bytes changed: '+row['path'])
    old_objects=[Path(v) for i,v in enumerate(prior['link']) if v.endswith('.o') and prior['link'][i-1]!='-o']
    if len(old_objects)!=125:raise ValueError('Wrong retained runtime')
    component=base/'component'
    abi_record=read(base/'objects/raw/nw_mainline.inputs.json')['dependencies']
    abi_path=str(component/'include/nw_abi.h')
    if abi_path not in abi_record:raise ValueError('Original ABI compile record missing')
    out.mkdir(parents=True,exist_ok=False);changes={};units={};rename_path=base/'objects/rename.txt'
    rename=dict(line.split() for line in rename_path.read_text().splitlines())
    for n in ['core.c','qmi.c','nw_wifi.c','nw_mainline.c']:
        member=('ath12k_' if n in ('core.c','qmi.c') else '')+n[:-2]+'.o'
        old,=[x for x in old_objects if x.name==member]
        if n=='core.c':row=prior['first_failure_units'][n];cmd=list(row['command']);source=Path(row['source']);inputs=row['consumed_inputs']
        elif n=='qmi.c':
            cmd=list(prior['host_wake_qmi_command']);source=Path(prior['eager_memory_source']);inputs=prior['host_wake_consumed_inputs']
            cmd[cmd.index(next(v for v in cmd if v.endswith('/qmi.c')))]=str(source)
        elif n=='nw_wifi.c':
            source=old.with_name('nw_wifi.c')
            row=read(old.parent/'result.json')['rebuilt_units'][member];cmd=list(row['command']);inputs=row['compile_inputs'] if 'compile_inputs' in row else read(old.parent/'result.json').get('compile_inputs',{})
        else:
            source=component/'src/nw_mainline.c'
            cmd=read(base/'objects'/('nw_mainline.command.json'))
            inputs=read(base/'objects/raw/nw_mainline.inputs.json')['dependencies']
        if sha(source)!=EXPECTED[n]:raise ValueError('Retained source differs: '+n)
        data=source.read_bytes();new=out/n;new.write_bytes(patch(n,data))
        raw=out/(member+'.raw.o');obj=out/member;dep=out/(member+'.d')
        cmd[cmd.index(next(v for v in cmd if v.endswith('/'+n)))]=str(new)
        cmd[cmd.index('-o')+1]=str(raw)
        if '-MF' in cmd:cmd[cmd.index('-MF')+1]=str(dep)
        else:cmd+=['-MD','-MF',str(dep)]
        cmd+=['-I',str(PORT)]
        r=execute(cmd,out,member+'-compile')
        deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
        for path in deps:
            if path==str(new) or Path(path).is_relative_to(PORT):continue
            if path==abi_path:
                if sha(Path(path))!=abi_record[path]:raise ValueError('Original ABI changed')
                continue
            if inputs and path not in inputs:raise ValueError('New non-portable header: '+path)
            if inputs and sha(Path(path))!=inputs[path]:raise ValueError('Changed retained header: '+path)
        execute([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(rename_path),str(raw),str(obj)],out,member+'-rename')
        if global_symbols(obj)!={rename.get(k,k):v for k,v in global_symbols(raw).items()} or sections(obj)!=sections(raw):
            raise ValueError('Portable rename changed data/code')
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/(member+'.asm')).write_text(asm)
        if any(k.endswith('/__mod_init_func') for k in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):
            raise ValueError('Portable C initializer/SIMD')
        changes[str(old)]=str(obj)
        units[n]=dict(source=str(new),source_sha256=sha(new),parent_source=str(source),parent_source_sha256=sha(source),
            parent_object=str(old),parent_object_sha256=sha(old),object=str(obj),object_sha256=sha(obj),command=cmd,
            consumed_inputs={v:sha(Path(v)) for v in deps},warnings=r.stderr.count(b'warning:'))
    cpp=out/'PortableScan.o'
    cppcmd=[str(a.llvm/'clang++'),'-target','arm64-apple-ios17.0','-std=c++17','-O2','-g0','-mkernel',
        '-ffreestanding','-fno-builtin','-fno-exceptions','-fno-rtti','-fno-stack-protector','-fno-common',
        '-fno-threadsafe-statics','-mgeneral-regs-only','-nostdinc++','-DELDEN_WIFI_PORTABLE_SCAN_TRIAL=1',
        '-Wall','-Wextra','-Werror','-MD','-MF',str(out/'PortableScan.d'),'-c',str(PORT/'PortableScan.cpp'),'-o',str(cpp)]
    execute(cppcmd,out,'portable-native')
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(cpp)],text=True);(out/'PortableScan.asm').write_text(asm)
    if any(k.endswith('/__mod_init_func') for k in sections(cpp)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):
        raise ValueError('Portable C++ initializer/SIMD')
    cppdeps=shlex.split((out/'PortableScan.d').read_text().replace('\\\n',' ').split(':',1)[1])
    target=out/'WifiRuntimeMsiBinding.o';link=list(prior['link']);link[link.index('-o')+1]=str(target)
    link=[changes.get(v,v) for v in link]+[str(cpp)];execute(link,out,'portable-link')
    retained={str(v):sha(v) for v in old_objects if str(v) not in changes}
    for path,digest in retained.items():
        if sha(Path(path))!=digest:raise ValueError('Retained runtime changed')
    if not defs(parent/'WifiRuntimeMsiBinding.o')<=defs(target):raise ValueError('Original exports lost')
    if refs(target)-refs(parent/'WifiRuntimeMsiBinding.o'):raise ValueError('Unexpected kernel imports: '+str(refs(target)-refs(parent/'WifiRuntimeMsiBinding.o')))
    own=[str(p.relative_to(ROOT)) for p in PORT.rglob('*') if p.is_file()]+['tools/build_wifi_portable_scan.py','tools/wifi_portable_scan.py']
    proof=dict(compiled=True,portable_scan_trial=True,donor=lock,hardware_tested=False,source_inputs={n:sha(ROOT/n) for n in own},
        portable_parent=prior,portable_parent_binding_sha256=prior['binding_sha256'],portable_parent_report_sha256=sha(parent/'result.json'),
        portable_units=units,portable_native=dict(object=str(cpp),object_sha256=sha(cpp),command=cppcmd,consumed_inputs={v:sha(Path(v)) for v in cppdeps}),
        retained_objects=retained,changed_runtime_units=list(units),original_runtime_count=125,new_runtime_count=126,link=link,binding_sha256=sha(target),
        original_firmware_memory_lifecycle_retained=True,no_fake_network_interface=True,scan_only=True,physical_return_contract_retained=True,
        no_board_power_or_firmware_replacement=True,stopping_keeps_dma_until_reset=True)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(dict(compiled=True,binding_sha256=sha(target),retained=len(retained),hardware_tested=False)))

if __name__=='__main__':main()
