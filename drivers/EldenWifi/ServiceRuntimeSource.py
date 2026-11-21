"""Extend the exact current owned runtime with checked supplicant staging."""
import hashlib,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
ORIGINAL='4a00bd6d29b6ee5c2c111605664d0fadc3335ba4e2e730ec213c78d96ed5ddbd'
def source():
    path=ROOT/'drivers/EldenBluetooth/runtime/LaunchCacheSource.py'
    spec=importlib.util.spec_from_file_location('wifi_cache_base',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    original=m.source();assert hashlib.sha256(original).hexdigest()==ORIGINAL
    text=original.decode();header='#include "EldenBtLaunchCache.h"'
    assert text.count(header)==1
    text=text.replace(header,header+'\n'+(ROOT/'drivers/EldenWifi/ServiceRuntime.inc').read_text(),1)
    gate='    if(mode!=4)return;';assert text.count(gate)==1
    text=text.replace(gate,'    int wifi=0;PE_parse_boot_argn("ewt",&wifi,sizeof(wifi));\n    if(mode!=4&&wifi!=1)return;',1)
    marker='    if(!error)error=elden_bt_launch_cache_prepare(p,scratch,data_mount);';assert text.count(marker)==1
    text=text.replace(marker,'''    if(!error)error=elden_wifi_service_prepare(p,scratch,data_mount);
'''+marker+'''
    error=elden_wifi_assets_finish(p,scratch,error);''',1)
    return text.encode()
def cache_header():
    return b'#pragma once\n#include "EldenWifiServiceAssets.h"\n#define elden_bt_launch_cache elden_wifi_launch_cache\n#define elden_bt_launch_cache_signature elden_wifi_launch_cache_signature\n'
