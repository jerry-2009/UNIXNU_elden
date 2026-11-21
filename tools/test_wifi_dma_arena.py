"""Compare the actual arena core with pinned Sheng functions under ASan/UBSan."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SHENG='e8937177309d88c93b305a57bad147fd5fac8a86'

def function(text,signature):
    start=text.index(signature);opening=text.index('{',start);depth=1;end=opening+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sheng-repository',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    raw=subprocess.check_output(['git','-C',str(a.sheng_repository),'show',SHENG+':package/WifiProbe.cpp'])
    text=raw.decode();lines=[line for line in text.splitlines() if line.startswith(('constexpr unsigned kArenaBlocks','struct Arena {'))]
    assert len(lines)==2
    functions={s:function(text,s) for s in ['void *arenaAlloc(', 'void arenaFree(', 'uint64_t pDmaMap(']}
    legacy='\n'.join(lines)+'\nstatic void pLog(int,const char *) {}\n#define bzero(p,n) memset(p,0,n)\n'+'\n'.join(functions.values())+'\n'
    (out/'OldArena.inc').write_text(legacy,encoding='utf-8',newline='\n')
    driver=ROOT/'drivers/EldenWifi'
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(driver),'-I'+str(out)]
    commands=[['clang','-std=c11',*flags,'-c',str(driver/'DmaArena.c'),'-o',str(out/'arena.o')],
              ['clang++','-std=c++17',*flags,str(driver/'TestDmaArena.cpp'),str(out/'arena.o'),'-o',str(out/'test')],
              [str(out/'test')]]
    for label,cmd in zip(['compile','link','run'],commands):
        r=subprocess.run(cmd,capture_output=True,timeout=120)
        (out/(label+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    result={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'hardware':False,
            'actual_functions_compared':True,'sheng_commit':SHENG,'sheng_wifi_probe_sha256':hashlib.sha256(raw).hexdigest(),
            'legacy_functions_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in functions.items()},
            'source_inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [driver/'DmaArena.c',driver/'DmaArena.h',driver/'TestDmaArena.cpp',ROOT/'tools/test_wifi_dma_arena.py']}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
