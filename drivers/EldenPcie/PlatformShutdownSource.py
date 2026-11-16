"""Use actual platform shutdown, retaining independent native hardware checks."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[2]
def generated():
    spec=importlib.util.spec_from_file_location('platform_control',ROOT/'drivers/EldenPcie/ControlNativeSource.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);files=mod.generated()
    def replace(text,old,new):
        if text.count(old)!=1:raise ValueError('Platform shutdown source differs: '+old[:80])
        return text.replace(old,new,1)
    text=files['Native.cpp'].decode();text=replace(text,'#include "RuntimeApi.h"','#include "RuntimeApi.h"\n#include "PlatformShutdownApi.h"');files['Native.cpp']=text.encode()
    text=files['MhiRuntime.inc'].decode();text='static int platform_config_error;\n'+text
    text=replace(text,'    return elden_pcie_cfg_write(&c->config,offset,size,value,c->transport_cleanup);',
        '''    int rc=elden_pcie_cfg_write(&c->config,offset,size,value,c->transport_cleanup);
    if(rc&&c->transport_cleanup&&!platform_config_error)platform_config_error=rc;
    return rc;''')
    text=replace(text,'        nw_wifi_stop();','''        int shutdown=nw_wifi_platform_shutdown();
        if(!shutdown&&platform_config_error)shutdown=platform_config_error;
        log("\\nELDEN_WIFI_PLATFORM shutdown=%d config-error=%d\\n",shutdown,platform_config_error);
        if(shutdown){elden_wifi_dma_stop_begin();c->runtime_cleanup_deadline=0;c->runtime_stop_error=shutdown;return shutdown;}''')
    files['MhiRuntime.inc']=text.encode();return files
