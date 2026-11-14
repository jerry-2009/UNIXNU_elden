"""Add the verified launch-cache stage to the exact owned runtime source."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[3]
ORIGINAL='7c0c2186e5ef37be9e554eae60cb2b43b67b8ae4d857f5467fa7f8137e30b842'
def source():
    data=(ROOT/'drivers/EldenBluetooth/runtime/Runtime.inc').read_bytes()
    if hashlib.sha256(data).hexdigest()!=ORIGINAL:raise ValueError('Runtime source changed')
    text=data.decode();marker='    if(!error)error=elden_icon_cpu_visible("/usr/sbin/BlueTool",elden_bt_runtime_payload,sizeof(elden_bt_runtime_payload));'
    if text.count(marker)!=1:raise ValueError('Runtime verification boundary differs')
    text=text.replace(marker,marker+'\n    if(!error)error=elden_bt_launch_cache_prepare(p,scratch,data_mount);')
    if text.count('original-job=1')!=1:raise ValueError('Runtime status boundary differs')
    text=text.replace('original-job=1','job-cache-required=1')
    return (ROOT/'drivers/EldenBluetooth/runtime/LaunchCache.inc').read_bytes()+b'\n'+text.encode()
