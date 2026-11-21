"""Run actual native transport callbacks with the real config/MSI cores."""
import argparse,hashlib,json,subprocess,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--firmware-cache',action='store_true');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenPcie'
    generator=d/('FirmwareNativeSource.py' if a.firmware_cache else 'TransportNativeSource.py')
    spec=importlib.util.spec_from_file_location('transport',generator);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    generated=mod.generated()
    for n,b in generated.items():(out/n).write_bytes(b)
    assert generated['NativeRuntime.inc'].count(b'if(!rc&&c->endpoint_confirmed&&c->transport_requested)transport_run(c);')==1
    assert generated['NativeRuntime.inc'].index(b'transport_stop(c,deadline)')<generated['NativeRuntime.inc'].index(b'elden_pcie_pins_set(&c->pins,false)')
    fixture=(d/'TestTransport.cpp').read_text(encoding='utf-8')
    if a.firmware_cache:
        fixture=fixture.replace('#include "TransportNativeRuntime.inc"','''extern "C" int elden_wifi_firmware_bind(const void *p,uint64_t e){int rc=hit();if(rc)return rc;CHECK(p==active&&e==7);return 0;}
extern "C" void elden_wifi_firmware_stop_begin(){CHECK(dma_stops>0);}
#include "TransportNativeRuntime.inc"''')
    (out/'Test.cpp').write_text(fixture,encoding='utf-8')
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(out),'-I'+str(d),'-I'+str(ROOT/'drivers/EldenSmmu')]
    commands=[['clang','-std=c11',*flags,'-c',str(d/(n+'.c')),'-o',str(out/(n+'.o'))] for n in ['Config','Msi']]
    commands += [['clang++','-std=c++17',*flags,str(out/'Test.cpp'),str(out/'Config.o'),str(out/'Msi.o'),'-o',str(out/'test')],[str(out/'test')]]
    for name,cmd in zip(['config','msi','link','run'],commands):
        r=subprocess.run(cmd,capture_output=True,timeout=90);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    files=[d/n for n in ['Config.c','Config.h','Msi.c','Msi.h','TransportNative.h','TransportNativeRuntime.inc','TransportNativeSource.py','TestTransport.cpp']]+[Path(__file__)]
    if a.firmware_cache:files.append(generator)
    result={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'hardware':False,'physical_and_dma_provider_modeled':True,'firmware_cache_bound':a.firmware_cache,
            'generated_sources':{n:hashlib.sha256(b).hexdigest() for n,b in generated.items()},
            'source_inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
