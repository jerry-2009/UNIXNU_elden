"""Wire the real Linux runtime and defer SMMU IRQ withdrawal until quiescence."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[2]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('MHI native source anchor changed: '+old[:90])
    return text.replace(old,new,1)
def wcn():
    text=module('mhi_early_wcn',ROOT/'drivers/EldenSmmu/EarlySource.py').wcn().decode()
    return replace(text,'    elden_wifi_smmu_stop_begin();','    /* The PCIe quiesce callback withdraws SMMU IRQs after MHI/PERST. */').encode()
def generated():
    files=module('mhi_firmware',ROOT/'drivers/EldenPcie/FirmwareNativeSource.py').generated()
    text=files['Native.cpp'].decode()
    text=replace(text,'#include "FirmwareCache.h"','#include "FirmwareCache.h"\n#include "RuntimeApi.h"\n#include "QmiPowerBinding.h"\n#include "MhiStop.h"')
    text=replace(text,'void elden_usb_log_putc(char);','void elden_usb_log_putc(char);\nvoid _disable_preemption(void);void _enable_preemption(void);')
    files['Native.cpp']=text.encode()
    text=files['NativeRuntime.inc'].decode()
    marker='    unsigned transport_stage=0,transport_wake=0,transport_gate=0;int transport_result=-11;'
    extra='''
    void *runtime_consumer=nullptr;thread_t runtime_thread=nullptr;uint64_t runtime_cleanup_deadline=0;
    bool runtime_prepared=false,runtime_entered=false,runtime_returned=false,runtime_stack_started=false,runtime_quiesced=false;
    unsigned runtime_stage=0,runtime_irq_seen=0,runtime_log_cursor=0,runtime_log_repeats=0;
    int runtime_error=0,runtime_start_error=0,runtime_stop_error=0,runtime_bss=0;
    uint64_t runtime_rounds=0;char runtime_log_lines[8][192]={};
    struct lx_platform runtime_platform={};struct nw_board runtime_board={};EldenMhiStop mhi_stop={};
'''
    text=replace(text,marker,marker+extra)
    text=replace(text,'#include "TransportNativeRuntime.inc"','#include "TransportNativeRuntime.inc"\n#include "MhiRuntime.inc"')
    text=replace(text,'    if(!rc&&c->endpoint_confirmed&&c->transport_requested)transport_run(c);',
        '''    if(!rc&&c->endpoint_confirmed&&c->transport_requested){
        transport_run(c);
        if(c->transport_ready)runtime_run(c);
        if(c->runtime_error){c->transport_result=c->runtime_error;c->transport_ready=false;}
    }''')
    text=replace(text,'    log("\\nELDEN_PCIE quiesced=1 perst-low=1 dma-enabled-by-driver=0\\n");return 0;',
        '''    log("\\nELDEN_PCIE quiesced=1 perst-low=1 dma-attempted=%u protocol-reset=%u\\n",(unsigned)c->config.master_attempted,c->mhi_stop.reset_observed);
    elden_wifi_smmu_stop_begin();return 0;''')
    text=replace(text,'''    /* This cold worker never creates a DMA window or enables EP bus master.
     * Once it is terminal, assert its owned reset and verify it remains low.
     * Replace this contract with MHI/DMA draining before adding DMA operation. */''',
        '''    /* Runtime protocol/BM/IRQ shutdown has returned successfully above.
     * Assert the owned endpoint reset before permitting WLAN power release. */''')
    files['NativeRuntime.inc']=text.encode()
    text=files['TransportNativeRuntime.inc'].decode()
    text='static int runtime_master_ready(void *);\nstatic int runtime_quiesced(Context *);\n'+text
    text=replace(text,'static int transport_master_ready(void *){return -95;}','static int transport_master_ready(void *p){return runtime_master_ready(p);}')
    text=replace(text,'if(c->config.master_attempted)return -95;','if(c->config.master_attempted)return runtime_quiesced(c);')
    text=replace(text,'''/* This component does not include the MHI execution/drain provider yet.
 * Refuse master enable until that provider is wired and independently checked. */''',
        '/* The concrete runtime checks prepared DMA/MSI/firmware and the actual consumer. */')
    text=replace(text,'''    /* No master write is permitted in this variant. Once one is attempted,
     * only the future real MHI shutdown provider may attest quiescence. */''',
        '    /* A master attempt requires the actual runtime protocol shutdown proof. */')
    files['TransportNativeRuntime.inc']=text.encode()
    text=files['NativeExports.inc'].decode()
    text=replace(text,'extern "C" void elden_pcie_native_stop_begin(void){__atomic_store_n(&stop_requested,1u,__ATOMIC_RELEASE);}',
        '''extern "C" void elden_pcie_native_stop_begin(void){
    __atomic_store_n(&stop_requested,1u,__ATOMIC_RELEASE);
    elden_wifi_firmware_stop_begin();elden_wifi_dma_close_admission();
}''')
    files['NativeExports.inc']=(text+'\n#include "MhiRuntimeExports.inc"\n').encode()
    return files
