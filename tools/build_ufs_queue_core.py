"""Compile the multi-slot/PRDT core for OS17; this is not a linked driver."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1];DRIVER=ROOT/'drivers/EldenUfsQueue'
sys.path.insert(0,str(DRIVER))
from PrdtSource import header
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('llvm','reference-native','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'EldenUfsPrdtAlgorithm.h').write_bytes(header())
    clang=a.llvm/'clang++';resource=subprocess.check_output([str(clang),'-print-resource-dir'],text=True).strip()
    expected={'QueueCore':{'_elden_ufs_pool_'+s for s in ('init','take','enqueue','cancel','issue','complete','release','stop')},
              'DmaPlan':{'_elden_ufs_dma_limit','_elden_ufs_prdt_build'}}
    reference=global_symbols(a.reference_native);records={}
    for name in ('QueueCore','DmaPlan'):
        src=DRIVER/(name+'.cpp');obj=out/(name+'.o')
        cmd=[str(clang),'-target','arm64-apple-ios17.0','-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffreestanding',
             '-fno-exceptions','-fno-rtti','-fno-stack-protector','-fno-threadsafe-statics','-fno-builtin','-mgeneral-regs-only',
             '-nostdinc','-isystem',str(Path(resource)/'include'),'-I',str(out),'-I',str(DRIVER),'-c',str(src),'-o',str(obj)]
        r=subprocess.run(cmd,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        symbols=global_symbols(obj);export={k for k,v in symbols.items() if v[0]&0x0e};imports={k for k,v in symbols.items() if not v[0]&0x0e}
        assert export==expected[name],export;assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
        assert all(k in reference and reference[k][0]&0x0e for k in imports),imports
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/(name+'.asm')).write_text(asm)
        assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
        assert all(op not in asm for op in ('\tsmc\t','\thvc\t','\twfi','\twfe'))
        records[name]={'object_sha256':sha(obj),'exports':sorted(export),'imports':sorted(imports),'command':cmd,'warnings':r.stderr.count(b'warning:')}
    files=[p for p in DRIVER.rglob('*') if p.is_file() and (p.suffix in ('.cpp','.h','.py','.json') or p.name=='LICENSE')]+[Path(__file__).resolve()]
    report={'passed':True,'target':'arm64-apple-ios17.0','objects':records,'scalar':True,'automatic_initializers':False,
            'header_sha256':sha(out/'EldenUfsPrdtAlgorithm.h'),'reference_native_sha256':sha(a.reference_native),
            'source_inputs':{str(p.relative_to(ROOT)):sha(p) for p in files},'native_adapter':False,'whole_kernel':False,'hardware':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('passed','target','scalar','native_adapter','whole_kernel','hardware')}))
if __name__=='__main__':main()
