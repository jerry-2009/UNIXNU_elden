"""Run actual serialized native DMA callbacks with explicit kernel service models."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);smmu=ROOT/'drivers/EldenSmmu';wifi=ROOT/'drivers/EldenWifi'
    raw=(smmu/'DmaNative.inc').read_text(encoding='utf-8');barrier='__asm__ volatile("dsb sy":::"memory")'
    assert raw.count(barrier)==1
    (out/'DmaNativeHost.inc').write_text(raw.replace(barrier,'host_order()',1),encoding='utf-8',newline='\n')
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(out),'-I'+str(smmu),'-I'+str(wifi)]
    commands=[['clang','-std=c11',*flags,'-c',str(wifi/'DmaArena.c'),'-o',str(out/'arena.o')],
              ['clang++','-std=c++17','-pthread',*flags,str(smmu/'TestDmaNative.cpp'),str(out/'arena.o'),'-o',str(out/'test')],
              [str(out/'test')]]
    for name,cmd in zip(['compile','link','run'],commands):
        r=subprocess.run(cmd,capture_output=True,timeout=90);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    files=[smmu/n for n in ['DmaNative.inc','DmaNative.h','TestDmaNative.cpp','DmaTables.h']]+[wifi/n for n in ['DmaArena.c','DmaArena.h']]+[Path(__file__)]
    result={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'hardware':False,'kernel_services_modeled':True,
            'source_inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
