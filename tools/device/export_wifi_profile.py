"""Export only the owner's currently connected WPA2 profile into a private build input.

Read-only Android access. Never prints names, addresses, passwords or XML.
The export is outside the source repository and must not be committed.
"""
import argparse,hashlib,json,re,struct,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb',type=Path,required=True);p.add_argument('--serial',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    if out==ROOT or ROOT in out.parents or out.exists():raise ValueError('A new private output outside source is required')
    def adb(*v):return subprocess.check_output([str(a.adb),'-s',a.serial,*v],timeout=30)
    if adb('shell','getprop','ro.product.model').strip()!=b'TB322FC' or adb('shell','getprop','ro.boot.verifiedbootstate').strip()!=b'green':
        raise ValueError('Verified Y700 Android required')
    if b'uid=0' not in adb('shell','su -c id'):raise ValueError('Root read permission absent')
    status=adb('shell','cmd','wifi','status').decode(errors='replace')
    match=re.search(r'SSID:\s*(.*?),\s*BSSID:',status)
    if not match:raise ValueError('Currently connected SSID not observed')
    ssid=match[1].strip().strip('"')
    if ssid in ('<unknown ssid>',''):raise ValueError('No connected owner network')
    configs=[];source_hashes=[]
    for path in ['/data/misc/apexdata/com.android.wifi/WifiConfigStore.xml','/data/misc/wifi/WifiConfigStore.xml',
                 '/data/misc_ce/0/apexdata/com.android.wifi/WifiConfigStore.xml']:
        r=subprocess.run([str(a.adb),'-s',a.serial,'exec-out','su -c '+"'cat "+path+"'"],capture_output=True,timeout=30)
        if r.returncode:continue
        try:xml=ET.fromstring(r.stdout)
        except ET.ParseError:continue
        source_hashes.append(dict(path=path,sha256=hashlib.sha256(r.stdout).hexdigest()))
        for network in xml.findall('.//Network'):
            cfg=network.find('WifiConfiguration')
            if cfg is None:continue
            values={x.attrib.get('name'):x.text or '' for x in cfg if x.tag=='string'}
            configured=values.get('SSID','').strip('"')
            if configured!=ssid:continue
            key=values.get('PreSharedKey','').strip('"')
            if key and key not in ('*','null'):configs.append(key)
    keys=set(configs)
    if len(keys)!=1:raise ValueError('One plaintext WPA2 key for the current owner network is required; encrypted/ambiguous data not exported')
    psk=keys.pop().encode('ascii');name=ssid.encode('utf-8')
    if not 1<=len(name)<=32 or not (8<=len(psk)<=63 or len(psk)==64 and re.fullmatch(rb'[0-9a-fA-F]{64}',psk)):
        raise ValueError('Connected profile is outside the supported WPA2-Personal shape')
    # StationProfile fixed byte layout:SSID32/PSK64/BSSID6/4 one-byte metadata.
    raw=name.ljust(32,b'\0')+psk.ljust(64,b'\0')+b'\0'*6+bytes([len(name),len(psk),1,0])
    assert len(raw)==106
    header='#pragma once\n#include <stdint.h>\nstatic const uint8_t elden_station_profile_bytes[106]={'+','.join(map(str,raw))+'};\n'
    out.mkdir(parents=True);(out/'profile.bin').write_bytes(raw);(out/'EldenStationProfile.h').write_text(header,encoding='ascii',newline='\n')
    record=dict(schema=1,private=True,network_name_printed=False,credentials_printed=False,read_only=True,currently_connected_profile=True,
        source_hashes=source_hashes,profile_sha256=hashlib.sha256(raw).hexdigest(),header_sha256=hashlib.sha256(header.encode()).hexdigest(),
        ssid_bytes=len(name),psk_bytes=len(psk),security='WPA2-Personal')
    (out/'private-report.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(dict(exported=True,private=True,read_only=True,security='WPA2-Personal')))
if __name__=='__main__':main()
