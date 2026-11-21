"""Add the explicit root full-on budget provider to the shared WCN adapter."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def source():
    spec=importlib.util.spec_from_file_location('wlan_shared',ROOT/'drivers/EldenWifi/SharedNativeSource.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);text=mod.source().decode()
    old='#include "WcnSharedPower.h"';assert text.count(old)==1
    text=text.replace(old,old+'\n#include "EldenPciePower.h"',1)
    decl='int elden_recovery_armed(void);';assert text.count(decl)==1
    text=text.replace(decl,decl+'\nint elden_recovery_rpc_ready(void);\nunsigned elden_recovery_deadline_remaining(void),elden_charge_policy_ready(void);\nbool elden_battery_temperature_get(int *,uint32_t *,uint32_t *);\nboolean_t ml_at_interrupt_context(void);',1)
    at='static void publish(Context *c){';assert text.count(at)==1
    text=text.replace(at,(ROOT/'drivers/EldenPcie/PowerNative.inc').read_text(encoding='utf-8')+'\n'+at,1)
    return (text+'\n'+(ROOT/'drivers/EldenPcie/PowerExports.inc').read_text(encoding='utf-8')).encode()
