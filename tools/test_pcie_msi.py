"""Exercise the actual MSI receiver lifecycle and IRQ/stop interleavings."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenPcie'
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(d)]
    commands=[['clang','-std=c11',*flags,'-c',str(d/'Msi.c'),'-o',str(out/'Msi.o')],
              ['clang++','-std=c++17','-pthread',*flags,str(d/'TestMsi.cpp'),str(out/'Msi.o'),'-o',str(out/'test')],[str(out/'test')]]
    for name,cmd in zip(['compile','link','run'],commands):
        r=subprocess.run(cmd,capture_output=True,timeout=90);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    result={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'hardware':False,'mmio_gic_modeled':True,
            'source_inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [d/'Msi.c',d/'Msi.h',d/'TestMsi.cpp',Path(__file__)]}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
