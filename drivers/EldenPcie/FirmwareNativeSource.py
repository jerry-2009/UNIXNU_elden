"""Bind firmware caching to the same qualified PCIe worker/epoch."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[2]
def generated():
    spec=importlib.util.spec_from_file_location('firmware_transport',ROOT/'drivers/EldenPcie/TransportNativeSource.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);files=mod.generated()
    text=files['Native.cpp'].decode();old='#include "TransportNative.h"';assert text.count(old)==1
    files['Native.cpp']=text.replace(old,old+'\n#include "FirmwareCache.h"',1).encode()
    text=(ROOT/'drivers/EldenPcie/TransportNativeRuntime.inc').read_text(encoding='utf-8')
    old='    if(!rc)rc=elden_wifi_dma_bind(c,c->wlan_epoch);';assert text.count(old)==1
    text=text.replace(old,old+'\n    if(!rc)rc=elden_wifi_firmware_bind(c,c->wlan_epoch);',1)
    old='c->transport_ready=false;elden_wifi_dma_stop_begin();';assert text.count(old)==1
    text=text.replace(old,old+'elden_wifi_firmware_stop_begin();',1)
    files['TransportNativeRuntime.inc']=text.encode();return files
