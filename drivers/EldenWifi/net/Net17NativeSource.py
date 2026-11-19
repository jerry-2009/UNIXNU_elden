"""Compose only the new BSD/IOKit bridge onto the existing service scan worker."""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[3]


def generated():
    spec=importlib.util.spec_from_file_location('net17_service_scan',ROOT/'drivers/EldenWifi/ServiceScanSource.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);files=module.generated()
    def replace(text,old,new):
        if text.count(old)!=1:raise ValueError('Net17 runtime anchor changed: '+old[:80])
        return text.replace(old,new,1)
    text=files['Native.cpp'].decode()
    text=replace(text,'#include "RuntimeApi.h"','#include "RuntimeApi.h"\n#include "EldenNet17.h"\n#include <libkern/c++/OSMetaClass.h>\n#include <mach/kmod.h>\nextern "C" kmod_info_t g_kernel_kmod_info;')
    files['Native.cpp']=text.encode()
    text=files['MhiRuntime.inc'].decode()
    marker='    log("\\nELDEN_WIFI_RUNTIME start=%d linux-stage=%u master=%u command=%x\\n",rc,nw_wifi_stats.stage,(unsigned)c->config.master_attempted,c->config.command);'
    text=replace(text,marker,marker+'''
    bool network_started=false;
    if(!rc){
        void *handle=OSMetaClass::preModLoad(g_kernel_kmod_info.name);
        int network_error=-12;
        if(handle){elden_wifi_net_static_init();network_error=OSMetaClass::postModLoad(handle);}
        if(!network_error)network_error=elden_wifi_net_start(elden_wifi_factory_mac_address);
        network_started=!network_error;
        log("\\nELDEN_WIFI_NET start=%d\\n",network_error);
        if(network_error)rc=network_error;
    }''')
    text=replace(text,'        int busy=nw_wifi_step();c->runtime_rounds++;',
        '        int busy=nw_wifi_step();c->runtime_rounds++;\n        if(network_started)elden_wifi_net_pump(runtime_ms());')
    marker='    c->runtime_stage=4;c->transport_cleanup=true;c->transport_ready=false;control_stop_begin();'
    text=replace(text,marker,'''    elden_wifi_net_stop_begin();
    int net_drained=-16;
    for(unsigned i=0;i<100;++i){net_drained=elden_wifi_net_drain();if(!net_drained)break;IOSleep(1);}
    log("\\nELDEN_WIFI_NET drain=%d\\n",net_drained);
    if(net_drained){c->runtime_stop_error=-16;return -16;}
'''+marker)
    files['MhiRuntime.inc']=text.encode()
    text=files['NativeExports.inc'].decode()
    text=replace(text,'    control_stop_begin();elden_wifi_firmware_stop_begin();elden_wifi_dma_close_admission();',
        '    elden_wifi_net_stop_begin();control_stop_begin();elden_wifi_firmware_stop_begin();elden_wifi_dma_close_admission();')
    text+='''
extern "C" int elden_wifi_net_admit(void){
    Context *c=runtime_context;
    if(!c||__atomic_load_n(&stop_requested,__ATOMIC_ACQUIRE)||!c->runtime_entered||!c->runtime_stack_started||
       c->runtime_returned||c->transport_cleanup||ml_at_interrupt_context())return -108;
    return transport_admit(c,false);
}
extern "C" void native_wifi_logf(int level,const char *format,...){
    char line[192];va_list args;va_start(args,format);vsnprintf(line,sizeof line,format,args);va_end(args);
    runtime_log(level,line);
}
extern "C" void sheng_wifi_wake(void){
    Context *c=runtime_context;
    if(c&&c->runtime_thread&&elden_wifi_net_admit()==0)transport_wake(c);
}
'''
    files['NativeExports.inc']=text.encode()
    return files
