"""Use the established exact-helper owner rule for v174's observed failure."""
import hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE='0b575977af3266ab01bd7d07a75fea15387df9ae47be9856e3132ae87ee2916e'
CDHASH='b02572b5f0fd9e79790645ad33df708b24530295'
def predicate():
    text=(ROOT/'drivers/EldenBluetooth/runtime/OwnerLaunch.inc').read_text()
    text=text.replace('elden_bt_runtime_ready','elden_wifi_assets_ready').replace('elden_bt_owner_launch','elden_wifi_owner_launch')
    text=text.replace('!p || !imgp || strcmp(proc_best_name(p),"BlueTool") ||','!p || !imgp ||')
    text=text.replace('"elden-wcn-power"','"ewt"').replace('if(mode!=4)','if(mode!=1)')
    text=text.replace('"/usr/sbin/BlueTool"','"/usr/libexec/unixnu-wpa_supplicant"')
    text=text.replace('ELDEN_BT_OWNER_LAUNCH','ELDEN_WIFI_OWNER_LAUNCH')
    replacement='static const unsigned char expected[20]={'+','.join('0x'+CDHASH[i:i+2] for i in range(0,40,2))+'};'
    text,n=re.subn(r'static const unsigned char expected\[20\]=\{[^}]+\};',lambda _:replacement,text);assert n==1
    # Process names may be truncated; the exact vnode path, CDHash and all
    # original signature/MAC/launch/mount/reason checks bind the executable.
    return text.encode()
def common(original):
    assert hashlib.sha256(original).hexdigest()==BASE
    text=original.decode();marker='static int elden_icon_cpu_owner_launch(proc_t p,struct image_params *imgp,int error,os_reason_t reason)\n{'
    assert text.count(marker)==1
    return text.replace(marker,predicate().decode()+'\n'+marker+'\n    if(elden_wifi_owner_launch(p,imgp,error,reason))return 1;',1).encode()
