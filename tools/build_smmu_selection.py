"""Compile the read-only SMMU selection component, without running it on hardware."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--llvm',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenSmmu';obj=out/'Select.o'
    cmd=['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-std=c11','-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-stack-protector','-mgeneral-regs-only',
         *['-I'+str(v) for v in [d,ROOT/'package',ROOT/'soc/sm8750/include']],'-c',str(d/'Select.c'),'-o',str(obj)]
    r=subprocess.run(cmd,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/'Select.asm').write_text(asm,encoding='utf-8')
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    assert not any(n.endswith('/__mod_init_func') for n in sections(obj));symbols=global_symbols(obj)
    assert {n for n,v in symbols.items() if v[0]&0x0e}=={'_elden_smmu_select_boot_domain'}
    assert not {n for n,v in symbols.items() if not v[0]&0x0e}
    files=['drivers/EldenSmmu/'+n for n in ['Select.c','Select.h','BootRoute.h']]+['package/EldenTouchBoard.h','soc/sm8750/include/EldenTouchResources.h']
    result={'compiled':True,'object_sha256':hashlib.sha256(obj.read_bytes()).hexdigest(),'scalar':True,'warnings':r.stderr.count(b'warning:'),
            'source_inputs':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files},'hardware':False,'kernel_linked':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
