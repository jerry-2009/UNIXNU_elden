"""Exercise the composed native MHI path with real config/MSI/QMI binding code."""
import argparse,hashlib,json,subprocess,importlib.util,re
from pathlib import Path
from prepare_elden_peach import sections
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--component-repository',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenPcie';wifi=ROOT/'drivers/EldenWifi'
    abi=subprocess.check_output(['git','-C',str(a.component_repository),'show','5f7f5a8a9f02f7ab45ed10a2f226e348c519a838:include/nw_abi.h']).decode()
    abi_code='#include "RuntimeApi.h"\n#include <type_traits>\n'
    for name,alias,fields in [('lx_platform','ReferencePlatform',['now_ms','sleep_ms','poll','log','halt','alloc','free','dma_alloc','dma_free','dma_map','dma_sync','fw_get','now_ns','boottime_ns','busy_delay_us','preempt_disable','preempt_enable']),
                              ('nw_board','ReferenceBoard',['bar','bar_len','device_id','msi_cap','irq_base','cfg_read','cfg_write','msi_target','map_phys','diagnostics']),
                              ('nw_wifi_stats','ReferenceStats',['stage','scans','frames','beacons','bss_seen','last_err'])]:
        begin=abi.index('struct '+name+' {');end=abi.index('};',begin)+2
        abi_code+=abi[begin:end].replace('struct '+name,'struct '+alias,1)+'\n'
        abi_code+=f'static_assert(sizeof(struct {name})==sizeof({alias}));\n'
        for field in fields:
            abi_code+=f'static_assert(offsetof(struct {name},{field})==offsetof({alias},{field}));\n'
            abi_code+=f'static_assert(std::is_same_v<decltype(((struct {name}*)nullptr)->{field}),decltype({alias}::{field})>);\n'
    abi_code+='int main(){}\n';(out/'Abi.cpp').write_text(abi_code)
    r=subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-I'+str(wifi),str(out/'Abi.cpp'),'-o',str(out/'abi-test')],capture_output=True)
    (out/'abi.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    spec=importlib.util.spec_from_file_location('mhi_source',d/'MhiRuntimeSource.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    generated=mod.generated()
    for name,data in generated.items():(out/name).write_bytes(data)
    wcn=mod.wcn();assert b'    elden_wifi_smmu_stop_begin();' not in wcn
    runtime=generated['NativeRuntime.inc'].decode()
    assert runtime.index('int transport=transport_stop(c,deadline)')<runtime.index('elden_pcie_pins_set(&c->pins,false)')<runtime.index('elden_wifi_smmu_stop_begin();')
    fields=re.search(r'    void \*runtime_consumer=nullptr;.*?EldenMhiStop mhi_stop=\{\};',runtime,re.S)[0]
    source=(d/'TestTransport.cpp').read_text().split('int main(){',1)[0]
    source=source.replace('static int allow_master(void *){return 0;}','')
    source=source.replace('#include "DmaNative.h"','#include "DmaNative.h"\n#include "FirmwareCache.h"\n#include "RuntimeApi.h"\n#include "MhiStop.h"\n#include "WlanPower.h"\n#include "QmiPowerBinding.h"')
    source=source.replace('    EldenPcieConfigAccess config={};EldenPcieMsi msi={};','    EldenPcieConfigAccess config={};EldenPcieMsi msi={};\n'+fields)
    source=source.replace('static int elden_wlan_power_ready','extern "C" int elden_wlan_power_ready')
    source=source.replace('struct Region {','static bool hang_reset,bad_bar,hold_transactions;\nstatic uint64_t reset_due;static uint32_t mhi_bar[1024];\nstruct Region {')
    old='int read(uint32_t off,uint32_t *v){assert(!(off&3)&&off<4096);int rc=hit();if(!rc)*v=data[off/4];return rc;}'
    new='''int read(uint32_t off,uint32_t *v){assert(!(off&3)&&off<4096);int rc=hit();if(rc)return rc;
        if(data==mhi_bar){if(bad_bar)return -5;
            if(reset_due&&clock_us>=reset_due&&!hang_reset){mhi_bar[0x38/4]&=~2u;mhi_bar[0x48/4]=0x101;if(!hold_transactions)cfg[0x48/4]&=~(32u<<16);}}
        *v=data[off/4];return 0;}'''
    assert old in source;source=source.replace(old,new)
    source=source.replace('if(data==dbi&&off==EldenMsiStatus)',
        'if(data==mhi_bar){data[off/4]=v;if(off==0x38&&(v&2))reset_due=clock_us+2000;}\n        else if(data==dbi&&off==EldenMsiStatus)')
    mocks=(d/'TestMhiMocks.inc').read_text().replace('static bool hang_reset,bad_bar,hold_transactions;','').replace('static uint64_t reset_due;static uint32_t mhi_bar[1024];','')
    source=source.replace('#include "TransportNativeRuntime.inc"',mocks+'\n#include "TransportNativeRuntime.inc"\n#include "MhiRuntimeHost.inc"\n#include "MhiRuntimeExports.inc"')
    source+='\n#include "TestMhiRuntime.inc"\n';(out/'Test.cpp').write_text(source,encoding='utf-8')
    body=(d/'MhiRuntime.inc').read_text();start=body.index('static uint64_t runtime_ns()');end=body.index('\n',start)
    body=body[:start]+'static uint64_t runtime_ns(){return now(nullptr)*1000;}'+body[end:]
    (out/'MhiRuntimeHost.inc').write_text(body,encoding='utf-8')
    headers=out/'include';(headers/'linux/pwrseq').mkdir(parents=True)
    header=sections((wifi/'peach/upstream-peach.patch').read_text())['include/linux/pwrseq/qcom_wcn.h'][0]['new']
    assert hashlib.sha256(header.encode()).hexdigest()=='09d5313e43cdcc0a57426d5aea26e25aea8a124411440c4cf3dd29a675319a1a'
    (headers/'linux/pwrseq/qcom_wcn.h').write_text(header)
    for n,s in {'types.h':'#include <stdint.h>\n#include <stddef.h>\ntypedef uint8_t u8;typedef uint32_t u32;\n','kconfig.h':'#define IS_REACHABLE(x) 1\n','errno.h':'#include <errno.h>\n'}.items():(headers/'linux'/n).write_text(s)
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',*['-I'+str(p) for p in [out,headers,d,wifi,ROOT/'drivers/EldenSmmu',ROOT/'drivers/EldenBluetooth']]]
    inputs=[d/'Config.c',d/'Msi.c',d/'MhiStop.c',wifi/'QmiPower.c'];objects=[]
    for f in inputs:
        obj=out/(f.stem+'.o');objects.append(obj);r=subprocess.run(['clang','-std=c11',*flags,'-c',str(f),'-o',str(obj)],capture_output=True)
        (out/(f.stem+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run(['clang++','-std=c++17',*flags,str(out/'Test.cpp'),*map(str,objects),'-o',str(out/'test')],capture_output=True)
    (out/'link.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run([str(out/'test')],capture_output=True,timeout=120);(out/'run.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    files=inputs+[d/n for n in ['MhiStop.h','MhiRuntime.inc','MhiRuntimeExports.inc','MhiRuntimeSource.py','TestMhiMocks.inc','TestMhiRuntime.inc','TestTransport.cpp']]+[wifi/'RuntimeApi.h',Path(__file__)]
    result={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'hardware':False,'linux_runtime_and_hardware_modeled':True,'actual_qmi_binding':True,
            'abi_layouts_and_field_types_checked':True,'upstream_abi_sha256':hashlib.sha256(abi.encode()).hexdigest(),
            'generated_sources':{n:hashlib.sha256(b).hexdigest() for n,b in generated.items()},'wcn_source_sha256':hashlib.sha256(wcn).hexdigest(),
            'source_inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
