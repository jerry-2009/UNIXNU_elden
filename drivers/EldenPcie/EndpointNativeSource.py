"""Derive the optional identity worker while preserving v157 root source files."""
from pathlib import Path
HERE=Path(__file__).resolve().parent

def replace(text,before,after):
    if text.count(before)!=1:raise ValueError('Root source anchor drift: '+before[:80])
    return text.replace(before,after,1)

def native():
    text=(HERE/'Native.cpp').read_text(encoding='utf-8')
    text=replace(text,'#include "Root.h"','#include "Root.h"\n#include "Endpoint.h"\n#include "EndpointNative.h"')
    text=replace(text,'static EldenPcieNativeStatus terminal;','static EldenPcieNativeStatus terminal;\nstatic EldenPcieEndpointStatus endpoint_terminal;')
    return text.encode()

def runtime():
    text=(HERE/'NativeRuntime.inc').read_text(encoding='utf-8')
    text=replace(text,'Region maps[EldenPcieWindowCount],pin_map,wlan_observer;',
                 'Region maps[EldenPcieWindowCount],pin_map,wlan_observer,bar0_map;')
    text=replace(text,'bool power_ready=false;',
                 'bool power_ready=false;\n    EldenPcieEndpoint endpoint={};bool endpoint_requested=false,endpoint_confirmed=false;\n    int endpoint_result=-11;unsigned printed_endpoint_stage=0;')
    text=replace(text,'static void trace(Context *c,unsigned w,uint32_t off){',
                 '''static void trace(Context *c,unsigned w,uint32_t off){
    if(c->endpoint_requested&&c->endpoint.stage&&c->printed_endpoint_stage!=c->endpoint.stage){
        c->printed_endpoint_stage=c->endpoint.stage;
        log("\\nELDEN_PCIE_EP stage=%u window=%u offset=%08x\\n",c->endpoint.stage,w,off);
    }''')
    text=replace(text,'static void finish(Context *c,int error){',
                 '#include "EndpointNativeRuntime.inc"\nstatic void finish(Context *c,int error){')
    text=replace(text,'    __atomic_store_n(&run,2u,__ATOMIC_RELEASE);',
                 '    endpoint_capture(c);\n    __atomic_store_n(&run,2u,__ATOMIC_RELEASE);')
    text=replace(text,'unsigned gen=(unsigned)(uintptr_t)arg;',
                 'unsigned gen=(unsigned)(uintptr_t)arg&255u;bool endpoint_requested=((uintptr_t)arg>>8)&1u;')
    text=replace(text,'c->battery_epoch=epoch;', 'c->endpoint_requested=endpoint_requested;c->battery_epoch=epoch;')
    text=replace(text,'int rc=elden_pcie_root_start(&c->root,gen);finish(c,rc);',
                 'int rc=elden_pcie_root_start(&c->root,gen);\n    if(!rc&&c->endpoint_requested)endpoint_run(c);\n    finish(c,rc);')
    return text.encode()

def exports():
    text=(HERE/'NativeExports.inc').read_text(encoding='utf-8')
    text=replace(text,'unsigned enabled=0,wlan=0,budget=0,gen=3;',
                 'unsigned enabled=0,wlan=0,budget=0,gen=3,endpoint=0;\n    PE_parse_boot_argn("epe",&endpoint,sizeof(endpoint));')
    text=replace(text,'if(enabled!=1||','if(endpoint>1||enabled!=1||')
    text=replace(text,'(void *)(uintptr_t)gen,','(void *)(uintptr_t)(gen|(endpoint<<8)),')
    text+='''
extern "C" int elden_pcie_endpoint_status(EldenPcieEndpointStatus *out){
    if(!out)return -22;
    if(__atomic_load_n(&run,__ATOMIC_ACQUIRE)!=2)return -11;
    *out=endpoint_terminal;out->stopped=__atomic_load_n(&stopped,__ATOMIC_ACQUIRE);
    if(__atomic_load_n(&stop_requested,__ATOMIC_ACQUIRE))out->confirmed=0;
    return 0;
}
'''
    return text.encode()

def generated():
    return {'Native.cpp':native(),'NativeRuntime.inc':runtime(),'NativeExports.inc':exports()}
