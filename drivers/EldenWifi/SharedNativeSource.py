"""Migrate the qualified native BT adapter to one platform WCN owner."""
import hashlib
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ORIGINAL='5c16106e90622150686b90706fcfc8c674cf3c4d563ed782fd7d57fc864e2c72'

def source():
    data=(ROOT/'profiles/v116-hci-reset/sources/WcnPowerNative.cpp').read_bytes()
    if hashlib.sha256(data).hexdigest()!=ORIGINAL:raise ValueError('Native base differs')
    spec=importlib.util.spec_from_file_location('wcn_admission',ROOT/'drivers/EldenBluetooth/AdmissionTraceSource.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    text=mod.source(data).decode()
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('Ambiguous native anchor: '+old[:90])
        text=text.replace(old,new,1)
    replace('#include "WcnPower.h"','#include "WcnPower.h"\n#include "WcnSharedPower.h"\n#include "WlanPower.h"\n#include "WlanGpio.h"\n#include "EldenWifiResources.h"')
    replace('EldenWcnPower power={};EldenWcnStartup startup={};EldenWcnHci hci={};',
            'EldenWcnSharedPower shared={};EldenWcnPower &power=shared.supply;\n    EldenWlanGpio wlan_gpio={};uint64_t bt_epoch=0;unsigned bt_state=EldenWcnPowerIdle;\n    EldenWcnStartup startup={};EldenWcnHci hci={};')
    marker='static void publish(Context *c){'
    replace(marker,(ROOT/'drivers/EldenWifi/WlanPowerNative.inc').read_text(encoding='utf-8')+'\n'+marker)
    replace('&published_epoch,c->power.epoch','&published_epoch,c->bt_epoch')
    replace('&published_state,c->power.state','&published_state,c->bt_state')
    start=text.index('        Context *c=new Context;',text.index('static void worker('))
    end=text.index('        int rc=preflight(c);',start)
    text=text[:start]+'''        Context *c=nullptr;int rc=platform_get(&c);
        if(rc){log("\\nELDEN_WCN refused shared platform %d\\n",rc);goto done;}
        if(!prepare_firmware(c,mode)){log("\\nELDEN_WCN refused firmware/address preflight\\n");goto done;}
        rc=platform_enter();if(rc){retained=true;goto done;}
'''+text[end:]
    replace('        int rc=preflight(c);','        rc=preflight(c);')
    replace('        if(rc||mode==1||elden_wcn_stop_requested()){','        platform_leave();\n        if(rc||mode==1||elden_wcn_stop_requested()){')
    replace('            if(retained)active=c;else delete c;','            // Platform-owned mappings survive both consumers until reset.')
    replace('        active=c;uint64_t epoch=','        uint64_t epoch=')
    replace('elden_wcn_power_acquire(&c->power,epoch)','bt_power_acquire(c,epoch)')
    replace('elden_wcn_power_stop(&c->power,epoch)','bt_power_stop(c,epoch)')
    replace('elden_wcn_power_finish(&c->power,epoch)','bt_power_finish(c,epoch)')
    replace('if(operation==1||operation==2)return elden_wcn_run_live(&run_control)&&state==EldenWcnPowerReady?0:-11;',
            'if(operation==1||operation==2)return elden_wcn_run_live(&run_control)&&state==EldenWcnPowerReady?elden_wcn_shared_check(&c->shared,EldenWcnBluetooth,epoch):-11;')
    for prefix in ['extern "C" int elden_wcn_power_lease_check(uint64_t epoch,unsigned operation){',
                   'extern "C" uint32_t elden_wcn_power_parent_hz(uint64_t epoch,unsigned source){']:
        replace(prefix,prefix+'\n    Context *c=__atomic_load_n(&active,__ATOMIC_ACQUIRE);')
    if text.count('if(!active||epoch!=')!=2:raise ValueError('Lease readers changed')
    text=text.replace('if(!active||epoch!=','if(!c||epoch!=')
    replace('if(parents(active,&main,&even))','if(parents(c,&main,&even))')
    replace('extern "C" int elden_wcn_request_stop(void){','extern "C" int elden_wcn_request_stop(void){\n    uint64_t deadline=now_us(nullptr)+9000000;\n    __atomic_store_n(&platform_stopping,1,__ATOMIC_RELEASE);')
    replace('    return state==EldenWcnStopped;','    int wlan_result=wlan_shutdown(deadline);\n    return state==EldenWcnStopped&&!wlan_result;')
    text+='\n'+(ROOT/'drivers/EldenWifi/WlanPowerExports.inc').read_text(encoding='utf-8')
    return text.encode()
