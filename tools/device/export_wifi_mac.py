"""Read the owner's Y700 factory WLAN identity; keep private outputs off-source."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
SOURCE_ROOT=Path(__file__).resolve().parents[2]
DEVICE_PATH='/mnt/vendor/persist/peach_v2/wlan_mac.bin'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--adb',type=Path,required=True);p.add_argument('--serial',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve()
    if out==SOURCE_ROOT or SOURCE_ROOT in out.parents:raise ValueError('Private output must be outside the source repository')
    if out.exists():raise ValueError('Use a new private output directory')
    def adb(*args):return subprocess.check_output([str(a.adb),'-s',a.serial,*args],timeout=30)
    assert adb('shell','getprop','ro.product.model').strip()==b'TB322FC'
    assert adb('shell','getprop','ro.boot.verifiedbootstate').strip()==b'green'
    assert adb('shell','getprop','sys.boot_completed').strip()==b'1'
    assert b'uid=0' in adb('shell','su','-c','id')
    raw=adb('exec-out','su','-c','cat '+DEVICE_PATH)
    if not 0<len(raw)<=4096:raise ValueError('Invalid factory file length')
    body=raw.rstrip(b'\0')
    if b'\0' in body:raise ValueError('Interior NUL in factory file')
    text=body.decode('ascii');entries=re.findall(r'^([A-Za-z][A-Za-z0-9_]*)\s*=\s*([0-9A-Fa-f]{12})\s*$',text,re.M)
    selected=[v for k,v in entries if k=='Intf0MacAddress']
    if len(selected)!=1:raise ValueError('Exactly one factory Intf0MacAddress required')
    mac=bytes.fromhex(selected[0]);assert len(mac)==6 and not mac[0]&1 and mac not in [b'\0'*6,b'\xff'*6]
    canonical='Intf0MacAddress='+mac.hex().upper()+'\n'
    header='#pragma once\n#include <stdint.h>\nstatic const char elden_wifi_factory_mac_text[]='+json.dumps(canonical)+';\n'
    header+='static const uint8_t elden_wifi_factory_mac_address[6]={'+','.join(str(v) for v in mac)+'};\n'
    out.mkdir(parents=True);(out/'factory-original.bin').write_bytes(raw);(out/'wlan_mac.bin').write_text(canonical,encoding='ascii',newline='\n');(out/'EldenWifiFactoryMac.h').write_text(header,encoding='ascii',newline='\n')
    result={'device_serial':a.serial,'product':'TB322FC','source_path':DEVICE_PATH,'entry_names':[k for k,v in entries],
        'selected':'Intf0MacAddress','original_sha256':hashlib.sha256(raw).hexdigest(),'canonical_sha256':hashlib.sha256(canonical.encode()).hexdigest(),
        'header_sha256':hashlib.sha256(header.encode()).hexdigest(),'device_writes':False,'private_output':True}
    (out/'private-report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'captured':True,'selected':'Intf0MacAddress','entries':len(entries),'device_writes':False,'address_printed':False}))
if __name__=='__main__':main()
