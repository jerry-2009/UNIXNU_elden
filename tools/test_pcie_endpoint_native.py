"""Run derived production worker/endpoint/root/PHY with modeled physical services."""
import argparse,hashlib,importlib.util,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--wsl-distro');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenPcie'
    spec=importlib.util.spec_from_file_location('endpoint_native',d/'EndpointNativeSource.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    generated=mod.generated()
    for name,data in generated.items():(out/name).write_bytes(data)
    text=(d/'TestNative.cpp').read_text(encoding='utf-8');replace=mod.replace
    text=replace(text,'#include "Root.h"','#include "Root.h"\n#include "Endpoint.h"\n#include "EndpointNative.h"')
    text=replace(text,'static bool ready=true;',
        'static unsigned endpoint_enabled=0,confirmed_calls=0,ready_calls=0;\nstatic int confirm_error=0,ready_error=0;static bool confirm_stops=false;\nstatic bool ready=true;')
    text=replace(text,'    if(!strcmp(name,"elden-pcie-root"))',
        '    if(!strcmp(name,"epe"))*v=endpoint_enabled;\n    else if(!strcmp(name,"elden-pcie-root"))')
    text=replace(text,'namespace {','''extern "C" {
void pcie_ep_fault(unsigned);void pcie_ep_stop(void (*)(void));
int pcie_ep_bar_read(void *,unsigned,uint32_t *);int pcie_ep_bar_write(void *,unsigned,uint32_t);
int elden_wlan_power_confirm_endpoint(const void *p,uint64_t e,uint32_t id,uint32_t major){
    CHECK(p==provider&&e==provided_epoch&&id==0x110e17cb&&major==2);confirmed_calls++;
    if(confirm_stops)elden_pcie_native_stop_begin();
    return confirm_error;
}
int elden_wlan_power_ready(const void *p,uint64_t e){CHECK(p==provider&&e==provided_epoch);ready_calls++;return ready_error;}
}
namespace {''')
    text=replace(text,'static EldenPcieNativeStatus terminal;','static EldenPcieNativeStatus terminal;\nstatic EldenPcieEndpointStatus endpoint_terminal;')
    text=replace(text,'        CHECK(false);return false;',
        '        if(pa==0x40400000&&length==0x200000){kind=9;bytes=length;return true;}\n        CHECK(false);return false;')
    text=replace(text,'        if(kind==7)return pcie_test_pin_read',
        '        if(kind==9)return pcie_ep_bar_read(hw,off,v);\n        if(kind==7)return pcie_test_pin_read')
    text=replace(text,'        if(kind==7)return pcie_test_pin_write',
        '        if(kind==9)return pcie_ep_bar_write(hw,off,value);\n        if(kind==7)return pcie_test_pin_write')
    text=replace(text,'    run=stop_requested=stopped=0;terminal={};',
        '    endpoint_enabled=confirmed_calls=ready_calls=0;confirm_error=ready_error=0;confirm_stops=false;endpoint_terminal={};\n    run=stop_requested=stopped=0;terminal={};')
    text=replace(text,'int main(){','int root_regression(){')
    text+='\n#include "TestEndpointNative.inc"\n';(out/'Test.cpp').write_text(text,encoding='utf-8')
    def path(v):
        v=str(Path(v).resolve());return '/mnt/'+v[0].lower()+v[2:].replace('\\','/') if a.wsl_distro else v
    prefix=['wsl','-d',a.wsl_distro,'--'] if a.wsl_distro else []
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    if a.wsl_distro:flags+=['-fno-pie','-no-pie']
    inc=['-I'+path(p) for p in [out,d,ROOT/'drivers/EldenWifi',ROOT/'drivers/EldenBluetooth',ROOT/'soc/sm8750/include',ROOT/'profiles/current-build/sources/a39f9324d152faf7']]
    commands=[]
    for name,file in [('bridge','TestEndpointNativeBridge.c'),('phy','Phy.c'),('endpoint','Endpoint.c')]:
        commands.append((name,['cc','-std=c11',*flags,*inc,'-c',path(d/file),'-o',path(out/(name+'.o'))]))
    commands += [('native',['c++','-std=c++17',*flags,*inc,path(out/'Test.cpp'),*[path(out/(n+'.o')) for n in ['bridge','phy','endpoint']],'-o',path(out/'test')]),('run',[path(out/'test')])]
    for name,cmd in commands:
        r=subprocess.run(prefix+cmd,capture_output=True,timeout=150);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    report={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'actual_native_worker_root_endpoint_phy':True,'physical_services_modeled':True,'hardware':False,
            'generated_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in generated.items()}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
