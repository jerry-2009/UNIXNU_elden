"""Test native control callbacks with the pinned production control queue."""
import argparse,hashlib,json,subprocess,importlib.util,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PIN='5f7f5a8a9f02f7ab45ed10a2f226e348c519a838'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['runtime-build','component-repository','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);module=a.runtime_build/'component'
    def run(cmd,name):
        r=subprocess.run(cmd,capture_output=True,timeout=90);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode();return r.stdout.decode()
    names=['src/nw_control.c','src/nw_control_wire.c','shim/src/lx_rt.c','include/nw_control.h','include/nw_control_endpoint.h','tests/control_endpoint_test.c']
    upstream={}
    for name in names:
        blob=subprocess.check_output(['git','-C',str(a.component_repository),'show',PIN+':'+name]);assert (module/name).read_bytes()==blob,name
        upstream[name]=hashlib.sha256(blob).hexdigest()
    # Extract the original declarations unchanged, avoiding conflicting C
    # linkage names when comparing the two copies in one translation unit.
    wire=(module/'include/nw_control.h').read_text();endpoint=(module/'include/nw_control_endpoint.h').read_text()
    abi='#include "ControlApi.h"\n#include <type_traits>\nnamespace reference {\n'
    for kind,name,text in [('enum','nw_control_status',wire),('enum','nw_control_send_result',endpoint),('struct','nw_control_transport',endpoint)]:
        abi+=re.search(kind+' '+name+r' \{.*?\};',text,re.S)[0]+'\n'
    abi+='}\n'
    for n in ['NW_CONTROL_OK','NW_CONTROL_INVALID','NW_CONTROL_BUSY','NW_CONTROL_NOT_READY','NW_CONTROL_AUTH_FAILED','NW_CONTROL_TIMED_OUT','NW_CONTROL_UNSUPPORTED','NW_CONTROL_NO_MEMORY','NW_CONTROL_NOT_FOUND','NW_CONTROL_DRIVER_FAILED','NW_CONTROL_STALE','NW_CONTROL_SEND_OK','NW_CONTROL_SEND_AGAIN','NW_CONTROL_SEND_CLOSED']:
        abi+=f'static_assert(int({n})==int(reference::{n}));\n'
    for n in ['context','send','wake']:
        abi+=f'static_assert(offsetof(nw_control_transport,{n})==offsetof(reference::nw_control_transport,{n}));\nstatic_assert(std::is_same_v<decltype(nw_control_transport::{n}),decltype(reference::nw_control_transport::{n})>);\n'
    abi+='static_assert(sizeof(nw_control_transport)==sizeof(reference::nw_control_transport));\nint main(){}\n';(out/'Abi.cpp').write_text(abi)
    run(['clang++','-std=c++17','-I'+str(ROOT/'drivers/EldenWifi'),str(out/'Abi.cpp'),'-o',str(out/'abi')],'abi')
    includes=['-I'+str(module/n) for n in ['shim/include','include','out/pinned']]
    flags=['-O1','-g','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    objects=[]
    for name in names[:3]:
        obj=out/(Path(name).stem+'.o');objects.append(obj)
        run(['clang','-std=gnu11',*flags,*includes,'-c',str(module/name),'-o',str(obj)],Path(name).stem)
    original=(module/'tests/control_endpoint_test.c').read_text();anchor='  assert(!nw_wifi_control_transport_set(&transport) && !nw_wifi_control_bind(&dispatch));'
    assert original.count(anchor)==1
    fixture=original.replace(anchor,'  assert(nw_wifi_control_bind(&dispatch) == NW_CONTROL_NOT_READY);\n'+anchor)
    (out/'upstream.c').write_text(fixture)
    run(['clang','-std=gnu11',*flags,*includes,str(out/'upstream.c'),*map(str,objects),'-o',str(out/'upstream')],'upstream-build')
    official=run([str(out/'upstream')],'upstream-run')
    prefix=original[:original.index('int main(void)')]
    prefix+='''
void fixture_init(void){lx_plat=&platform;lx_irq_polling(0);}
static int fixture_request(void *c,uint64_t id,const struct nw_control_view *v,struct nw_control_builder *b){(void)c;(void)id;(void)v;(void)b;dispatched++;return 0;}
int fixture_bind(void){struct nw_control_dispatch d={.request=fixture_request};return nw_wifi_control_bind(&d);}
int fixture_occupy(void){struct nw_control_transport t={.send=send_message,.wake=wake};int r=nw_wifi_control_transport_set(&t);return r?r:fixture_bind();}
void fixture_pump(void){drain();}
void fixture_shutdown(void){nw_wifi_control_shutdown();}
size_t fixture_packet(void *bytes,size_t capacity,uint64_t id){struct nw_control_builder b;assert(!nw_control_begin(&b,bytes,capacity,NW_CONTROL_REQUEST,NW_CONTROL_INFO,1,id,7,0));return b.length;}
unsigned fixture_requests(void){return dispatched;}
'''
    (out/'Fixture.c').write_text(prefix)
    run(['clang','-std=gnu11',*flags,*includes,'-c',str(out/'Fixture.c'),'-o',str(out/'Fixture.o')],'fixture')
    run(['clang++','-std=c++17',*flags,'-I'+str(ROOT/'drivers/EldenWifi'),str(ROOT/'drivers/EldenPcie/TestControl.cpp'),str(out/'Fixture.o'),*map(str,objects),'-o',str(out/'native')],'native-build')
    for i in range(7):run([str(out/'native'),str(i)],'native-'+str(i))
    spec=importlib.util.spec_from_file_location('control',ROOT/'drivers/EldenPcie/ControlNativeSource.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);generated=mod.generated()
    code=generated['MhiRuntime.inc'].decode();assert code.index('nw_wifi_set_platform(')<code.index('rc=control_start();')<code.index('if(!rc)rc=nw_wifi_start(')
    files=[ROOT/'drivers/EldenPcie'/n for n in ['ControlNative.inc','ControlNativeSource.py','TestControl.cpp']]+[ROOT/'drivers/EldenWifi/ControlApi.h',Path(__file__)]
    result={'passed':True,'scenarios':7,'sanitizers':['address','undefined'],'upstream_output':official,'upstream_sha256':upstream,'source_inputs':{str(f.relative_to(ROOT)):sha(f) for f in files},'kernel_socket_services_modeled':True,'actual_control_queue':True,'abi_checked':True,'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
