"""Extend the verified physical-fence worker with service and private MAC input."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def base():
    spec=importlib.util.spec_from_file_location('wifi_service_fence',ROOT/'drivers/EldenPcie/PlatformFenceSource.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m.generated()

def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('Service native anchor differs: '+old[:90])
    return text.replace(old,new,1)

def generated():
    files=base();text=files['MhiRuntime.inc'].decode()
    text=replace(text,'static Context *runtime_context;',
        'extern "C" int elden_wifi_assets_ready(void);\nstatic Context *runtime_context;\n'+
        (ROOT/'drivers/EldenWifi/FactoryMacRuntime.inc').read_text())
    text=replace(text,'    c->runtime_stage=1;int rc=transport_msi_admit(c);',
        '''    c->runtime_stage=1;
    if(!elden_wifi_assets_ready()){c->runtime_error=-19;log("\\nELDEN_WIFI_SERVICE assets-not-ready\\n");return;}
    int rc=transport_msi_admit(c);''')
    text=replace(text,'elden_wifi_dma_map,elden_wifi_dma_sync,elden_wifi_firmware_get,',
        'elden_wifi_dma_map,elden_wifi_dma_sync,runtime_service_firmware_get,')
    files['MhiRuntime.inc']=text.encode()
    text=(ROOT/'drivers/EldenPcie/ControlNative.inc').read_text()
    text=replace(text,'    *info=client;return 0;',
        '    *info=client;log("\\nELDEN_WIFI_SERVICE control-connected=1\\n");return 0;')
    text=replace(text,'    nw_wifi_control_detach(session);IOFree(info,sizeof(WifiControlClient));return 0;',
        '    nw_wifi_control_detach(session);IOFree(info,sizeof(WifiControlClient));log("\\nELDEN_WIFI_SERVICE control-disconnected=1\\n");return 0;')
    files['ControlNative.inc']=text.encode();return files
