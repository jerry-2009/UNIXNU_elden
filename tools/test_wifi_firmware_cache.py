"""Exercise actual cache/FAT methods on the retained stock modem image."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MODEM='725134ea3cef706988e6f15813aaba41956a89f1f2a2a6bfd961c99cb56d0221'
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['modem','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();assert hashlib.sha256(a.modem.read_bytes()).hexdigest()==MODEM
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenWifi';fat=ROOT/'drivers/EldenPmicGlink'
    raw=(d/'FirmwareCache.cpp').read_text(encoding='utf-8')
    for line in ['#include <IOKit/IOLib.h>\n','#include <IOKit/IOLocks.h>\n','#include <libkern/crypto/sha2.h>\n']:
        assert raw.count(line)==1;raw=raw.replace(line,'',1)
    (out/'FirmwareCacheHost.inc').write_text(raw,encoding='utf-8',newline='\n')
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',*['-I'+str(p) for p in [d,fat,ROOT/'package',ROOT/'soc/sm8750/include',out]]]
    commands=[['clang','-std=c11',*flags,'-c',str(src),'-o',str(out/(src.stem+'.o'))] for src in [d/'ModemFiles.c',fat/'FatVolume.c']]
    commands += [['clang++','-std=c++17','-pthread','-Wno-deprecated-declarations',*flags,str(d/'TestFirmwareCache.cpp'),str(out/'ModemFiles.o'),str(out/'FatVolume.o'),'-o',str(out/'test')],[str(out/'test'),str(a.modem)]]
    for name,cmd in zip(['files','fat','link','run'],commands):
        r=subprocess.run(cmd,capture_output=True,timeout=120);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    files=[d/n for n in ['FirmwareCache.cpp','FirmwareCache.h','TestFirmwareCache.cpp','ModemFiles.c','ModemFiles.h']]+[fat/'FatVolume.c',fat/'FatVolume.h',ROOT/'package/EldenWifiFirmwareInputs.h',ROOT/'soc/sm8750/include/EldenWifiResources.h',Path(__file__)]
    result={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'modem_sha256':MODEM,'real_fat_and_sha256':True,'hardware':False,
            'source_inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
