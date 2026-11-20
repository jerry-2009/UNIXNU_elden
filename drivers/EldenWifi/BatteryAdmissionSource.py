"""Explicit radio-only admission over exact retained PMIC and WCN sources."""
from pathlib import Path
import importlib.util,sys
ROOT=Path(__file__).resolve().parents[2]


def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('Battery-only admission anchor changed: '+old[:90])
    return text.replace(old,new,1)


def client():
    sys.path.insert(0,str(ROOT/'drivers/EldenPmicGlink'))
    from PdStartupSource import client as original
    text=original().decode()
    text=replace(text,'#include "ChargePolicy.h"','#include "ChargePolicy.h"\n#include "BatteryAdmission.h"')
    marker='static void publishRaw(const EldenChargePoll &poll,uint64_t ageMs) {'
    text=replace(text,marker,(ROOT/'drivers/EldenWifi/BatteryAdmission.inc').read_text()+'\n'+marker+'\n    wifiBatteryPublish(&poll.committed,ageMs);')
    # A transport DOWN/UP, including an ABA, invalidates the cached snapshot.
    marker='        const bool nowUp=__atomic_load_n(&linkUp,__ATOMIC_ACQUIRE)!=0;'
    text=replace(text,marker,marker+'\n        if(!nowUp||epoch!=seen){wifiBatteryDeadline=0;wifiBatteryReported=false;}')
    # Keep the original transcript bounded when the extra cache changes
    # optimizer inlining. Prove snprintf's addition before using signed n.
    old='''            n+=snprintf(line+n,sizeof(line)-(unsigned)n,"%s%08x",i==first?"":",",poll.committed.value[i].raw);'''
    new='''            {
                int written=snprintf(line+n,sizeof(line)-(unsigned)n,"%s%08x",i==first?"":",",poll.committed.value[i].raw);
                if(written<0||written>(int)sizeof(line)-1-n){n=-1;break;}
                n+=written;
            }'''
    text=replace(text,old,new)
    return text.encode()


def worker(files):
    files=dict(files)
    text=files['Native.cpp'].decode();text=replace(text,'void elden_usb_log_putc(char);','void elden_usb_log_putc(char);\nint elden_wifi_battery_ready(uint32_t);');files['Native.cpp']=text.encode()
    text=files['NativeRuntime.inc'].decode();text=replace(text,'||!elden_charge_policy_ready())return false;',')return false;')
    marker='t>3800||(expected&&expected!=e))return false;'
    text=replace(text,marker,'t>3800||(expected&&expected!=e)||!elden_wifi_battery_ready(e))return false;')
    files['NativeRuntime.inc']=text.encode();return files


def wcn():
    path=ROOT/'drivers/EldenPcie/MhiRuntimeSource.py';spec=importlib.util.spec_from_file_location('battery_wcn_parent',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    text=m.wcn().decode()
    text=replace(text,'int elden_recovery_rpc_ready(void);','int elden_recovery_rpc_ready(void);\nint elden_wifi_battery_ready(uint32_t);')
    text=replace(text,'||!elden_charge_policy_ready())return false;',')return false;')
    text=replace(text,'temperature>3800||(expected&&expected!=e))return false;',
        'temperature>3800||(expected&&expected!=e)||!elden_wifi_battery_ready(e))return false;')
    return text.encode()
