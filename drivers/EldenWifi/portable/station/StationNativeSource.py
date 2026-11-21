"""Extend the qualified worker with a privileged 802.1X port and private profile."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
STATION=Path(__file__).resolve().parent

def apply(files):
    result=dict(files)
    def replace(name,old,new):
        text=result[name].decode()
        if text.count(old)!=1:raise ValueError('Station worker anchor differs: '+name+': '+old[:70])
        result[name]=text.replace(old,new,1).encode()
    replace('Native.cpp','#include "EldenNet17.h"','#include "EldenNet17.h"\n#include "StationApi.h"\n#include "EldenStationProfile.h"')
    result['NativeExports.inc']+=b'\n'+(STATION/'StationPortNative.inc').read_bytes()
    # Explicit source generation of the existing firmware callback. The same
    # hardware/epoch/stop admission gates remain for the private profile.
    replace('MhiRuntime.inc','    if(strcmp(name,"wlan_mac.bin"))return elden_wifi_firmware_get(name,data,bytes);',
            '    bool station_profile=!strcmp(name,"elden-station-profile.bin");\n'
            '    if(!station_profile&&strcmp(name,"wlan_mac.bin"))return elden_wifi_firmware_get(name,data,bytes);')
    replace('MhiRuntime.inc','    *data=reinterpret_cast<const uint8_t *>(elden_wifi_factory_mac_text);',
            '    if(station_profile){*data=elden_station_profile_bytes;*bytes=sizeof(elden_station_profile_bytes);return 0;}\n'
            '    *data=reinterpret_cast<const uint8_t *>(elden_wifi_factory_mac_text);')
    return result
