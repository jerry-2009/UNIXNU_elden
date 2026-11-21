"""Compile the host DMA fence; native owner and PERST checks bind later."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenPcie';obj=out/'PlatformFence.o'
    cmd=['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-std=c11','-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-stack-protector','-mgeneral-regs-only','-I'+str(d),'-c',str(d/'PlatformFence.c'),'-o',str(obj)]
    r=subprocess.run(cmd,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/'PlatformFence.asm').write_text(asm)
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
    syms=global_symbols(obj);defs={n for n,v in syms.items() if v[0]&0xe};refs={n for n,v in syms.items() if not v[0]&0xe}
    assert defs=={'_elden_pcie_platform_fence'} and refs=={'_elden_pcie_cfg_read','_elden_pcie_cfg_master'}
    result={'compiled':True,'scalar':True,'warnings':r.stderr.count(b'warning:'),'object_sha256':hashlib.sha256(obj.read_bytes()).hexdigest(),'source_inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [d/'PlatformFence.c',d/'PlatformFence.h',d/'Config.h',Path(__file__)]},'imports':sorted(refs),'hardware':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
