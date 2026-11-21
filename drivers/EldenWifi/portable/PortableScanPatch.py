"""Select the successful SM8750 portable scan path in an explicit Peach trial.

No original path is replaced for a normal build or another device. Preserve
original QMI firmware memory and the real registered platform shutdown/fence.
"""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
PORT=Path(__file__).resolve().parent
EXPECTED={'core.c':'267a592a39b5583fb39cf07dc8dad93662473d41c5c186fbc6972eda3cea1074',
          'qmi.c':'0757a84e9d887205dc06e5aa52c06a7b2499bc84ed3d26bbc4122fa665817cca',
          'nw_wifi.c':'7af0ebb0663a79f7364a0ba610a1c4f08f903a8c680372bd8f5efeed6d886cca',
          'nw_mainline.c':'b2c98a7aa6786379bf1ad1baa90893fe17481a1c76184a08f5d15625aecfdb30'}


def patch(name,data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED.get(name):
        raise ValueError('Portable trial requires exact retained parent: '+name)
    original=text=data.decode();changes=[]
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('Portable anchor changed: '+name+': '+old[:80])
        text=text.replace(old,new,1);changes.append((old,new))
    if name=='core.c':
        replace('unsigned int ath12k_debug_mask;',
                (PORT/'PortableGlue.inc').read_text(encoding='utf-8')+'\nunsigned int ath12k_debug_mask;')
        old='\tret = ath12k_core_start_firmware(ab, ab->fw_mode);'
        replace(old,'\tif (ab->hw_rev == ATH12K_HW_PEACH_HW20 && elden_wifi_portable_requested())\n'
                    '\t\treturn elden_wifi_portable_begin(ab);\n\n'+old)
    elif name=='qmi.c':
        replace('\tif (ab->hw_params->supports_shadow_regs) {',
                '\tif (ab->hw_params->supports_shadow_regs &&\n'
                '\t    !(ab->hw_rev == ATH12K_HW_PEACH_HW20 && elden_wifi_portable_requested())) {')
        text='#include "PortableApi.h"\n'+text;changes.append(('','#include "PortableApi.h"\n'))
    elif name=='nw_wifi.c':
        replace('nw_mainline_run(); wmi_stuck();',
                'if (!elden_wifi_portable_requested()) nw_mainline_run();\n'
                '  elden_wifi_portable_runtime_step(); wmi_stuck();')
        replace('  elden_platform_started=1;\n  nw_mainline_shutdown();\n  nw_wifi_control_shutdown();',
                '  elden_platform_started=1;\n'
                '  int portable_stop=elden_wifi_portable_runtime_stop();\n'
                '  if(portable_stop) lx_log(3,"ELDEN_PORTABLE protocol-stop=%d; physical shutdown still required",portable_stop);\n'
                '  nw_mainline_shutdown();\n  nw_wifi_control_shutdown();')
        text='#include "PortableApi.h"\n'+text;changes.append(('','#include "PortableApi.h"\n'))
    elif name=='nw_mainline.c':
        old='int nw_wifi_bss_count(void) { lx_shared_spin_lock(&boundary_lock); unsigned count = bss_count; lx_shared_spin_unlock(&boundary_lock); return count; }'
        replace(old,'int nw_wifi_bss_count(void) { int n=elden_wifi_portable_bss_count();if(n>=0)return n; lx_shared_spin_lock(&boundary_lock); unsigned count = bss_count; lx_shared_spin_unlock(&boundary_lock); return count; }')
        text='#include "PortableApi.h"\n'+text;changes.append(('','#include "PortableApi.h"\n'))
    else:raise ValueError('Unknown portable unit')
    restored=text
    for old,new in reversed(changes):
        if old=='':
            if not restored.startswith(new):raise ValueError('Portable prefix differs')
            restored=restored[len(new):]
        else:
            if restored.count(new)!=1:raise ValueError('Nonreversible portable delta')
            restored=restored.replace(new,old,1)
    if restored!=original:raise ValueError('Unrelated portable source change')
    return text.encode()
