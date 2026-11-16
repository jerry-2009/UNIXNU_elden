"""Use an explicit physical-reset proof for completed platform shutdown."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[2]
def generated():
    spec=importlib.util.spec_from_file_location('fence_platform',ROOT/'drivers/EldenPcie/PlatformShutdownSource.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);files=mod.generated()
    def replace(text,old,new):
        if text.count(old)!=1:raise ValueError('Platform fence anchor differs: '+old[:90])
        return text.replace(old,new,1)
    text=files['Native.cpp'].decode();text=replace(text,'#include "MhiStop.h"','#include "MhiStop.h"\n#include "PlatformFence.h"');files['Native.cpp']=text.encode()
    text=files['NativeRuntime.inc'].decode()
    text=replace(text,'EldenMhiStop mhi_stop={};','EldenMhiStop mhi_stop={};EldenPlatformFence platform_fence={};\n    bool platform_callback_returned=false,platform_perst_verified=false;')
    text=replace(text,'#include "MhiRuntime.inc"','#include "MhiRuntime.inc"\n#include "PlatformFenceNative.inc"')
    old='''    int rc=elden_pcie_pins_set(&c->pins,false);if(rc)return rc;
    uint64_t before=now(nullptr);IODelay(1000);uint64_t after=now(nullptr);
    if(after<before||after-before<1000||after>=deadline)return -110;
    uint32_t io=UINT32_MAX;rc=c->pin_map.read(4,&io);
    if(rc||io==UINT32_MAX||(io&3u))return rc?rc:-71;'''
    text=replace(text,old,'    int rc=platform_assert_perst(c,deadline);if(rc)return rc;')
    marker='    log("\\nELDEN_PCIE quiesced=1 perst-low=1 dma-attempted=%u protocol-reset=%u\\n",(unsigned)c->config.master_attempted,c->mhi_stop.reset_observed);'
    text=replace(text,marker,'''    if(c->platform_callback_returned)
        log("\\nELDEN_PCIE_PLATFORM physical-reset=%u perst-low=1 master-off=%u transactions-idle=%u msi=%u warm-reset=unverified\\n",c->platform_perst_verified,c->platform_fence.master_off,c->platform_fence.transactions_idle,c->msi.state);
    else
'''+marker)
    # Context is defined inside this file, before quiesce. Declare the helper
    # there; its implementation follows the existing runtime definitions.
    text=replace(text,'static Context *active;','static Context *active;\nstatic int platform_assert_perst(Context *,uint64_t);')
    files['NativeRuntime.inc']=text.encode()
    text=files['MhiRuntime.inc'].decode()
    text='static int platform_fence_run(Context *);\nstatic int platform_dma_ready(Context *);\n'+text
    text=replace(text,'static int runtime_quiesced(Context *c){','static int runtime_quiesced(Context *c){\n    if(c->platform_callback_returned)return platform_dma_ready(c);')
    marker='        if(shutdown){elden_wifi_dma_stop_begin();c->runtime_cleanup_deadline=0;c->runtime_stop_error=shutdown;return shutdown;}'
    text=replace(text,marker,marker+'\n        c->platform_callback_returned=true;')
    text=replace(text,'    int rc=elden_mhi_stop(&c->mhi_stop,&io,now(nullptr)+3000000);',
        '    int rc=c->platform_callback_returned?platform_fence_run(c):elden_mhi_stop(&c->mhi_stop,&io,now(nullptr)+3000000);')
    marker='    log("\\nELDEN_WIFI_RUNTIME stop=%d stage=%u reset=%u/%u ctl=%x status=%x command=%x transactions=%x consumer=%u\\n",rc,'
    text=replace(text,marker,'''    if(c->platform_callback_returned)
        log("\\nELDEN_WIFI_FENCE result=%d stage=%u master-off=%u transactions-sampled=%u idle=%u command=%x device-status=%x msi=%u perst=pending consumer=%u\\n",rc,c->runtime_stage,c->platform_fence.master_off,c->platform_fence.transactions_sampled,c->platform_fence.transactions_idle,c->platform_fence.command,c->platform_fence.device_status,c->msi.state,c->runtime_consumer!=nullptr);
    else
'''+marker)
    files['MhiRuntime.inc']=text.encode();return files
