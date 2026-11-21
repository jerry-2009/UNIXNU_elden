"""Compile the serialized DMA arena core; no native provider or hardware activation."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from replay_xnu_objects import sections,global_symbols
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--llvm',type=Path,required=True)
    p.add_argument('--reference-kernel',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);driver=ROOT/'drivers/EldenWifi';obj=out/'DmaArena.o'
    cmd=['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-std=c11','-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-stack-protector','-mgeneral-regs-only','-I'+str(driver),'-c',str(driver/'DmaArena.c'),'-o',str(obj)]
    r=subprocess.run(cmd,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/'DmaArena.asm').write_text(asm,encoding='utf-8')
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
    symbols=global_symbols(obj);exports={n for n,v in symbols.items() if v[0]&0x0e};imports={n for n,v in symbols.items() if not v[0]&0x0e}
    assert exports=={'_elden_wifi_dma_arena_'+n for n in ['init','alloc','free','map','bus_range','stop']}
    # Apple Clang lowers the zero aggregate/memset to bzero on this target.
    assert imports in ({'_bzero','_memmove'},{'_memset','_memmove'}),imports
    available={n for n,v in global_symbols(a.reference_kernel).items() if v[0]&0x0e}
    assert imports<=available,imports-available
    result={'compiled':True,'scalar':True,'warnings':r.stderr.count(b'warning:'),'object_sha256':hashlib.sha256(obj.read_bytes()).hexdigest(),
            'exports':sorted(exports),'imports':sorted(imports),'command':cmd,
            'kernel_imports_verified':True,'reference_kernel_sha256':hashlib.sha256(a.reference_kernel.read_bytes()).hexdigest(),
            'source_inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [driver/'DmaArena.c',driver/'DmaArena.h',ROOT/'tools/build_wifi_dma_arena.py']},
            'native_provider_integrated':False,'kernel_linked':False,'hardware':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
