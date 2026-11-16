"""Test native control callbacks with the pinned production control queue."""
import argparse,hashlib,json,subprocess,importlib.util,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PIN='5f7f5a8a9f02f7ab45ed10a2f226e348c519a838'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['runtime-build','component-repository','output']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--service-control-trace',action='store_true')
    p.add_argument('--service-scan',action='store_true')
    p.add_argument('--irq-snapshot',action='store_true')
    a=p.parse_args();a.service_control_trace|=a.service_scan or a.irq_snapshot;out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);module=a.runtime_build/'component'
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
    if a.service_control_trace:abi+=re.search(r'struct nw_control_stats \{.*?\};',endpoint,re.S)[0]+'\n'
    abi+='}\n'
    for n in ['NW_CONTROL_OK','NW_CONTROL_INVALID','NW_CONTROL_BUSY','NW_CONTROL_NOT_READY','NW_CONTROL_AUTH_FAILED','NW_CONTROL_TIMED_OUT','NW_CONTROL_UNSUPPORTED','NW_CONTROL_NO_MEMORY','NW_CONTROL_NOT_FOUND','NW_CONTROL_DRIVER_FAILED','NW_CONTROL_STALE','NW_CONTROL_SEND_OK','NW_CONTROL_SEND_AGAIN','NW_CONTROL_SEND_CLOSED']:
        abi+=f'static_assert(int({n})==int(reference::{n}));\n'
    for n in ['context','send','wake']:
        abi+=f'static_assert(offsetof(nw_control_transport,{n})==offsetof(reference::nw_control_transport,{n}));\nstatic_assert(std::is_same_v<decltype(nw_control_transport::{n}),decltype(reference::nw_control_transport::{n})>);\n'
    abi+='static_assert(sizeof(nw_control_transport)==sizeof(reference::nw_control_transport));\nint main(){}\n';(out/'Abi.cpp').write_text(abi)
    if a.service_control_trace:
        abi='#include "ControlTraceApi.h"\n'+abi
        for name in ['accepted','dispatched','replies','events','malformed','stale_sessions','rx_full','tx_full','send_retries','rx_bytes','tx_bytes','rx_items','tx_items','connections','disconnections','active_session','last_operation','last_status']:
            abi+=f'static_assert(offsetof(nw_control_stats,{name})==offsetof(reference::nw_control_stats,{name}));\n'
        abi+='static_assert(sizeof(nw_control_stats)==sizeof(reference::nw_control_stats));\n';(out/'Abi.cpp').write_text(abi)
    run(['clang++','-std=c++17','-I'+str(ROOT/'drivers/EldenWifi'),str(out/'Abi.cpp'),'-o',str(out/'abi')],'abi')
    includes=['-I'+str(module/n) for n in ['shim/include','include','out/pinned']]
    flags=['-O1','-g','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    objects=[]
    for name in names[:3]:
        obj=out/(Path(name).stem+'.o');objects.append(obj)
        selected=module/name
        if a.irq_snapshot and name=='shim/src/lx_rt.c':
            selected=out/'lx_rt.c';selected.write_bytes((module/name).read_bytes()+b'\n'+(ROOT/'drivers/EldenWifi/IrqSnapshot.inc').read_bytes())
        run(['clang','-std=gnu11',*flags,*includes,'-c',str(selected),'-o',str(obj)],Path(name).stem)
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
    if a.irq_snapshot:
        prefix+='''
void elden_wifi_irq_snapshot(uint32_t,uint32_t [10]);
static unsigned irq_sample_calls;
static irqreturn_t sample_irq(int irq,void *cookie){(void)cookie;uint32_t s[10];elden_wifi_irq_snapshot(1000,s);
  assert(s[5]&(1u<<(irq-1000)));assert(s[6]&&s[7]);irq_sample_calls++;return IRQ_HANDLED;}
void fixture_irq_check(void){
  int one,two;uint32_t a[10],b[10];
  assert(!lx_request_irq(1003,sample_irq,NULL,0,"mhi",&one));
  assert(!lx_request_irq(1005,sample_irq,NULL,0,"ce",&two));
  lx_disable_irq(1003);lx_disable_irq(1005);lx_irq_raise(1003);lx_irq_raise(1005);
  elden_wifi_irq_snapshot(1000,a);elden_wifi_irq_snapshot(1000,b);assert(!memcmp(a,b,sizeof(a)));
  assert(a[0]==40&&a[1]==32&&a[2]==40&&a[3]==8&&a[4]==8&&!a[5]&&!a[6]&&!a[7]&&!a[8]&&!a[9]);
  assert(lx_pump());assert(irq_sample_calls==1);elden_wifi_irq_snapshot(1000,a);assert(a[2]==8&&!a[5]);
  lx_enable_irq(1003);assert(lx_pump());assert(irq_sample_calls==2);elden_wifi_irq_snapshot(1000,a);assert(!a[2]&&a[1]==40);
  elden_wifi_irq_snapshot(UINT32_MAX,b);for(unsigned i=0;i<6;i++)assert(!b[i]);
  lx_free_irq(1003,&one);lx_free_irq(1005,&two);elden_wifi_irq_snapshot(1000,a);for(unsigned i=0;i<6;i++)assert(!a[i]);
}
'''
    (out/'Fixture.c').write_text(prefix)
    run(['clang','-std=gnu11',*flags,*includes,'-c',str(out/'Fixture.c'),'-o',str(out/'Fixture.o')],'fixture')
    fixture_source=ROOT/'drivers/EldenPcie/TestControl.cpp'
    if a.service_control_trace:
        spec=importlib.util.spec_from_file_location('service_trace',ROOT/'drivers/EldenWifi/ServiceControlTraceSource.py')
        tr=importlib.util.module_from_spec(spec);spec.loader.exec_module(tr)
        if a.service_scan:
            spec=importlib.util.spec_from_file_location('service_scan',ROOT/'drivers/EldenWifi/ServiceScanSource.py')
            tr=importlib.util.module_from_spec(spec);spec.loader.exec_module(tr)
        generated=tr.generated();(out/'ControlNative.inc').write_bytes(generated['ControlNative.inc'])
        text=fixture_source.read_text();fixture_source=out/'TestControl.cpp'
        text=text.replace('#include "ControlNative.inc"','#include <cstdarg>\nstatic void log(const char *fmt,...){va_list args;va_start(args,fmt);vprintf(fmt,args);va_end(args);}\n#include "ControlNative.inc"')
        text=text.replace('puts("PASS native socket callbacks', '''unsigned char secret[64]={0};memcpy(secret,"NWC1",4);secret[4]=1;secret[6]=1;secret[8]=1;secret[16]=64;
    memcpy(secret+40,"SHOULD_NOT_LOG",14);wifi_trace_meta("privacy",7,0,secret,sizeof(secret));
    for(unsigned i=0;i<150;i++)wifi_trace_meta("bounded",7,0,nullptr,0);
    puts("PASS native socket callbacks''')
        if a.service_scan:
            runtime=generated['MhiRuntime.inc'].decode();start=runtime.index('        uint64_t current_session=wifi_service_info_session();');end=runtime.index('        if(t>=report_at)',start)
            block=runtime[start:end]
            helper='''static uint64_t scan_session,scan_at;static bool scan;static unsigned scan_attempts,scan_calls;
static struct {unsigned stage;} nw_wifi_stats={4};
static int nw_wifi_scan(const uint8_t *,size_t){scan_calls++;return 0;}
static void scan_tick(uint64_t t){
'''+block+'''}
static void delivered(uint64_t session){unsigned char reply[128]={};size_t n=fixture_packet(reply,sizeof(reply),session);reply[6]=2;
    wifi_note_info_delivery(ENOBUFS,session,reply,n);assert(!wifi_service_info_session());
    reply[20]=3;wifi_note_info_delivery(0,session,reply,n);assert(!wifi_service_info_session());reply[20]=0;
    reply[4]=2;wifi_note_info_delivery(0,session,reply,n);assert(!wifi_service_info_session());reply[4]=1;
    wifi_note_info_delivery(0,session+1,reply,n);assert(!wifi_service_info_session());
    wifi_note_info_delivery(0,session,reply,n);assert(wifi_service_info_session()==session);
}
'''
            text=text.replace('int main(int argc,char **argv){',helper+'int main(int argc,char **argv){')
            text=text.replace('enqueue_error=ENOBUFS;assert(!registered.ctl_send', 'assert(!wifi_service_info_session());scan_tick(0);assert(!scan_calls);\n    enqueue_error=ENOBUFS;assert(!registered.ctl_send',1)
            text=text.replace('assert(fixture_requests()==1&&queues==1);','assert(fixture_requests()==1&&queues==1);assert(!wifi_service_info_session());',1)
            text=text.replace('fixture_pump();assert(queues==2);','fixture_pump();assert(queues==2);assert(wifi_service_info_session()==session);scan_tick(0);scan_tick(1);assert(scan_calls==1);',1)
            text=text.replace('client=nullptr;fixture_pump();assert(!allocations);','client=nullptr;fixture_pump();assert(!allocations);assert(!wifi_service_info_session());scan_tick(2);assert(scan_calls==1);',1)
            text=text.replace('control_stop_begin();assert(!wifi_control_open());assert(registered.ctl_send',
                '''assert(!wifi_service_info_session());scan_tick(3);assert(scan_calls==1);
    unsigned char old_reply[128]={};size_t old_n=fixture_packet(old_reply,sizeof(old_reply),session);old_reply[6]=2;
    wifi_note_info_delivery(0,session,old_reply,old_n);assert(!wifi_service_info_session());
    delivered(next);scan_tick(4);scan_tick(5);assert(scan_calls==2);
    scan_attempts=3;scan=false;scan_tick(6);assert(scan_calls==2);
    control_stop_begin();assert(!wifi_service_info_session());scan_tick(7);assert(scan_calls==2);
    assert(!wifi_control_open());assert(registered.ctl_send''',1)
        if a.irq_snapshot:
            text=text.replace('void fixture_init();','void fixture_init();void fixture_irq_check();',1)
            text=text.replace('fixture_init();\n','fixture_init();fixture_irq_check();\n',1)
        fixture_source.write_text(text)
    run(['clang++','-std=c++17',*flags,'-I'+str(ROOT/'drivers/EldenWifi'),str(fixture_source),str(out/'Fixture.o'),*map(str,objects),'-o',str(out/'native')],'native-build')
    for i in range(7):run([str(out/'native'),str(i)],'native-'+str(i))
    if a.service_control_trace:
        data=(out/'native-0.log').read_text();assert 'SHOULD_NOT_LOG' not in data
        assert re.search(r'where=privacy[^\n]*header=1',data)
        assert len(re.findall(r'ELDEN_WIFI_CTL where=',data))==96
    spec=importlib.util.spec_from_file_location('control',ROOT/'drivers/EldenPcie/ControlNativeSource.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);generated=mod.generated()
    code=generated['MhiRuntime.inc'].decode();assert code.index('nw_wifi_set_platform(')<code.index('rc=control_start();')<code.index('if(!rc)rc=nw_wifi_start(')
    files=[ROOT/'drivers/EldenPcie'/n for n in ['ControlNative.inc','ControlNativeSource.py','TestControl.cpp']]+[ROOT/'drivers/EldenWifi/ControlApi.h',Path(__file__)]
    if a.service_control_trace:files+=[ROOT/'drivers/EldenWifi'/n for n in ['ServiceNativeSource.py','ServiceControlTraceSource.py','ControlTrace.inc','ControlTraceApi.h']]
    if a.service_scan:files+=[ROOT/'drivers/EldenWifi'/n for n in ['ServiceScanSource.py','ControlScan.inc']]
    if a.irq_snapshot:files.append(ROOT/'drivers/EldenWifi/IrqSnapshot.inc')
    result={'passed':True,'scenarios':7,'irq_snapshot_actual_table_checked':a.irq_snapshot,'service_scan':a.service_scan,'actual_scan_block_tested':a.service_scan,'service_control_trace':a.service_control_trace,'trace_payload_redaction_checked':a.service_control_trace,'sanitizers':['address','undefined'],'upstream_output':official,'upstream_sha256':upstream,'source_inputs':{str(f.relative_to(ROOT)):sha(f) for f in files},'kernel_socket_services_modeled':True,'actual_control_queue':True,'abi_checked':True,'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
