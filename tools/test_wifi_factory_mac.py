"""Check the actual private-file firmware adapter; no device identifiers used."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    production=(ROOT/'drivers/EldenWifi/FactoryMacRuntime.inc').read_text()
    (out/'EldenWifiFactoryMac.h').write_text('static const char elden_wifi_factory_mac_text[]="Intf0MacAddress=020000000001\\n";\n')
    prefix=r'''
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
struct Context {bool runtime_prepared,runtime_entered,runtime_returned,transport_cleanup;uint64_t wlan_epoch;};
struct EldenWifiFirmwareStatus {unsigned run,stopping;int error;uint64_t epoch;};
static Context context,*runtime_context;
static unsigned stop_requested,fallbacks,reports;
static int admission,status_error;static EldenWifiFirmwareStatus state;
static int transport_admit(Context *c,bool cleanup){assert(c==&context&&!cleanup);return admission;}
static int elden_wifi_firmware_status(EldenWifiFirmwareStatus *s){*s=state;return status_error;}
static int elden_wifi_firmware_get(const char *n,const uint8_t **data,size_t *bytes){
    assert(strcmp(n,"wlan_mac.bin"));fallbacks++;*data=(const uint8_t*)"original";*bytes=8;return -74;
}
#define log wifi_test_log
static void wifi_test_log(const char *text){assert(!strcmp(text,"\nELDEN_WIFI_SERVICE factory-mac-provided=1\n"));reports++;}
'''
    suffix=r'''
static void reset(){context={true,true,false,false,42};runtime_context=&context;
    stop_requested=fallbacks=reports=0;admission=status_error=0;state={2,0,0,42};}
int main(){unsigned cases=0;const uint8_t *data;size_t bytes;
    for(unsigned failure=0;failure<=13;failure++){
        reset();switch(failure){case 1:runtime_context=nullptr;break;case 2:context.runtime_prepared=false;break;
        case 3:context.runtime_entered=false;break;case 4:context.runtime_returned=true;break;case 5:context.transport_cleanup=true;break;
        case 6:stop_requested=1;break;case 7:admission=-19;break;case 8:status_error=-11;break;case 9:state.run=1;break;
        case 10:state.stopping=1;break;case 11:state.error=-74;break;case 12:state.epoch=43;break;case 13:state.run=3;break;}
        data=(const uint8_t*)1;bytes=99;int rc=runtime_service_firmware_get("wlan_mac.bin",&data,&bytes);
        if(failure)assert(rc<0&&!data&&!bytes&&!reports);else assert(!rc&&bytes==29&&!memcmp(data,elden_wifi_factory_mac_text,bytes)&&reports==1);
        assert(!fallbacks);cases++;
    }
    reset();data=nullptr;bytes=0;assert(runtime_service_firmware_get("amss.bin",&data,&bytes)==-74&&fallbacks==1&&bytes==8);cases++;
    assert(runtime_service_firmware_get("PEACH/hw2.0/wlan_mac.bin",&data,&bytes)==-74&&fallbacks==2);cases++;
    data=(const uint8_t*)1;bytes=1;assert(runtime_service_firmware_get(nullptr,&data,&bytes)==-22&&!data&&!bytes);cases++;
    bytes=1;assert(runtime_service_firmware_get("wlan_mac.bin",nullptr,&bytes)==-22&&!bytes);cases++;
    data=(const uint8_t*)1;assert(runtime_service_firmware_get("wlan_mac.bin",&data,nullptr)==-22&&!data);cases++;
    printf("PASS %u actual factory MAC adapter cases; original firmware fallback unchanged\n",cases);
}
'''
    (out/'test.cpp').write_text(prefix+production+suffix)
    cmd=['c++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'test.cpp'),'-o',str(out/'test')]
    for name,args in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(args,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    result={'passed':True,'cases':19,'actual_adapter':True,'synthetic_mac_only':True,'hardware_services_modeled':True,
        'source_sha256':hashlib.sha256(production.encode()).hexdigest(),'sanitizers':['ASan','UBSan']}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print((out/'run.log').read_text())
if __name__=='__main__':main()
