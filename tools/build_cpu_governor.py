"""Compile the source-only governor component and check its kernel dependencies."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenCpuPower'))
from GovernorSource import policy
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--llvm',type=Path,required=True);p.add_argument('--reference-native',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);header=out/'EldenCpuFreqPolicy.h';header.write_bytes(policy())
    clang=a.llvm/'clang++';resource=subprocess.check_output([str(clang),'-print-resource-dir'],text=True).strip()
    obj=out/'GovernorApi.o';source=ROOT/'drivers/EldenCpuPower/GovernorApi.cpp'
    cmd=[str(clang),'-target','arm64-apple-ios17.0','-std=c++17','-O2','-Wall','-Wextra','-ffreestanding','-fno-exceptions','-fno-rtti','-fno-stack-protector','-fno-threadsafe-statics','-fno-builtin','-mgeneral-regs-only','-nostdinc','-isystem',str(Path(resource)/'include'),'-I',str(out),'-I',str(source.parent),'-I',str(ROOT/'profiles/v91/sources/power'),'-c',str(source),'-o',str(obj)]
    r=subprocess.run(cmd,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    symbols=global_symbols(obj);exports={k for k,v in symbols.items() if v[0]&0x0e};imports={k for k,v in symbols.items() if not v[0]&0x0e}
    expected={'_elden_cpu_governor_'+s for s in ('context_bytes','initialize','step','message_allowed','terminal')};assert exports==expected
    assert not any(s.endswith('/__mod_init_func') for s in sections(obj))
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/'GovernorApi.asm').write_text(asm)
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    reference=global_symbols(a.reference_native);assert all(k in reference and reference[k][0]&0x0e for k in imports),imports
    assert all(op not in asm for op in ('\tsmc\t','\thvc\t','\twfi','\twfe'))
    files=[source,source.parent/'GovernorControl.h',source.parent/'GovernorSource.py',source.parent/'upstream/CpuFreqGovernor.h',source.parent/'upstream/source.json',source.parent/'upstream/LICENSE',ROOT/'profiles/v91/sources/power/EldenScmiPerf.h',ROOT/'profiles/v91/sources/power/CpuPerfAccess.h',Path(__file__).resolve()]
    report={'compiled':True,'target':'arm64-apple-ios17.0','object_sha256':sha(obj),'reference_native_sha256':sha(a.reference_native),'policy_sha256':sha(header),'exports':sorted(exports),'imports':sorted(imports),'scalar':True,'automatic_initializers':False,'whole_kernel_linked':False,'hardware':False,'source_inputs':{str(f.relative_to(ROOT)):sha(f) for f in files},'command':cmd,'warnings':r.stderr.decode().count('warning:')}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('command','source_inputs')}))
if __name__=='__main__':main()
