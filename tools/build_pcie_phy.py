"""Compile the reviewed cold PHY transaction for ARM64/iOS17; no kernel link."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from replay_xnu_objects import sections,global_symbols
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--llvm',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenPcie';obj=out/'Phy.o'
    cmd=['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-std=c11','-O2','-Wall','-Wextra','-Werror',
         '-ffreestanding','-fno-builtin','-fno-stack-protector','-mgeneral-regs-only','-c',str(d/'Phy.c'),'-o',str(obj)]
    r=subprocess.run(cmd,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/'Phy.asm').write_text(asm,encoding='utf-8')
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
    symbols=global_symbols(obj);exports={n for n,v in symbols.items() if v[0]&0x0e};imports={n for n,v in symbols.items() if not v[0]&0x0e}
    assert exports=={'_elden_pcie_phy_start'} and not imports
    report={'compiled':True,'object_sha256':hashlib.sha256(obj.read_bytes()).hexdigest(),'command':cmd,'warnings':r.stderr.count(b'warning:'),
            'exports':sorted(exports),'imports':sorted(imports),'scalar':True,'kernel_linked':False,'hardware_tested':False,
            'source_sha256':{n:hashlib.sha256((d/n).read_bytes()).hexdigest() for n in ['Phy.c','Phy.h','PhySequence.inc']}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
