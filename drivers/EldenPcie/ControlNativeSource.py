"""Install the real privileged native control socket before nl80211 binding."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[2]
def generated():
    spec=importlib.util.spec_from_file_location('control_mhi',ROOT/'drivers/EldenPcie/MhiRuntimeSource.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);files=mod.generated();replace=mod.replace
    text=files['Native.cpp'].decode()
    text=replace(text,'#include "RuntimeApi.h"','#include "RuntimeApi.h"\n#include "ControlApi.h"\n#include <IOKit/IOLocks.h>\n#include <sys/kern_control.h>\n#include <sys/kpi_mbuf.h>\n#include <sys/errno.h>')
    files['Native.cpp']=text.encode()
    text=files['NativeRuntime.inc'].decode()
    text=replace(text,'#include "MhiRuntime.inc"','#include "MhiRuntime.inc"\n#include "ControlNative.inc"');files['NativeRuntime.inc']=text.encode()
    text=(ROOT/'drivers/EldenPcie/MhiRuntime.inc').read_text(encoding='utf-8')
    text='static int control_start();\nstatic void control_stop_begin();\n'+text
    text=replace(text,'c->runtime_stage=4;c->transport_cleanup=true;c->transport_ready=false;','c->runtime_stage=4;c->transport_cleanup=true;c->transport_ready=false;control_stop_begin();')
    text=replace(text,'rc=nw_wifi_start(&c->runtime_platform,&c->runtime_board);',
        'rc=control_start();log("\\nELDEN_WIFI_CONTROL start=%d\\n",rc);\n    if(!rc)rc=nw_wifi_start(&c->runtime_platform,&c->runtime_board);')
    files['MhiRuntime.inc']=text.encode()
    text=files['NativeExports.inc'].decode()
    text=replace(text,'    elden_wifi_firmware_stop_begin();elden_wifi_dma_close_admission();','    control_stop_begin();elden_wifi_firmware_stop_begin();elden_wifi_dma_close_admission();')
    files['NativeExports.inc']=text.encode();return files
