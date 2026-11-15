"""Compile bounded endpoint config access without touching hardware."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from replay_xnu_objects import sections,global_symbols
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenPcie';obj=out/'Config.o'
    cmd=['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-std=c11','-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-stack-protector','-mgeneral-regs-only','-I'+str(d),'-c',str(d/'Config.c'),'-o',str(obj)]
    r=subprocess.run(cmd,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/'Config.asm').write_text(asm,encoding='utf-8')
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
    syms=global_symbols(obj);exports={n for n,v in syms.items() if v[0]&0x0e};imports={n for n,v in syms.items() if not v[0]&0x0e}
    assert not imports and exports=={'_elden_pcie_cfg_'+n for n in ['open','read','write','master']}
    result={'compiled':True,'scalar':True,'warnings':r.stderr.count(b'warning:'),'object_sha256':hashlib.sha256(obj.read_bytes()).hexdigest(),
            'source_inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [d/'Config.c',d/'Config.h',Path(__file__)]},
            'exports':sorted(exports),'imports':sorted(imports),'command':cmd,'hardware':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
