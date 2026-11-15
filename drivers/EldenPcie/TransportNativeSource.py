"""Connect qualified DMA/MSI/config providers to the explicit PCIe worker variant."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def generated():
    spec=importlib.util.spec_from_file_location('transport_early',ROOT/'drivers/EldenSmmu/EarlySource.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);files=mod.pcie_generated();replace=mod.replace
    text=files['Native.cpp'].decode()
    text=replace(text,'#include "EldenWifiSmmuNative.h"','#include "EldenWifiSmmuNative.h"\n#include "EldenWifiDmaNative.h"\n#include "Config.h"\n#include "Msi.h"\n#include "TransportNative.h"')
    text=replace(text,'void elden_usb_log_putc(char);','void elden_usb_log_putc(char);\nIOReturn armcpu_spi_attach(uint32_t,bool,void(*)(void*),void*,uint32_t*,uint64_t*);\nIOReturn armcpu_spi_mask(uint32_t,bool);')
    files['Native.cpp']=text.encode()
    text=files['NativeRuntime.inc'].decode()
    text=replace(text,'    bool power_ready=false;','    bool power_ready=false;\n    EldenPcieConfigAccess config={};EldenPcieMsi msi={};\n    bool transport_requested=false,transport_ready=false,transport_cleanup=false;\n    unsigned transport_stage=0,transport_wake=0,transport_gate=0;int transport_result=-11;')
    text=replace(text,'static int quiesce(const void *provider,uint64_t epoch,uint64_t deadline){','static int transport_stop(Context *,uint64_t);\nstatic int quiesce(const void *provider,uint64_t epoch,uint64_t deadline){')
    text=replace(text,'    if(epoch!=c->wlan_epoch)return -19;','    if(epoch!=c->wlan_epoch)return -19;\n    int transport=transport_stop(c,deadline);if(transport)return transport;')
    text=replace(text,'#include "EndpointNativeRuntime.inc"','#include "EndpointNativeRuntime.inc"\n#include "TransportNativeRuntime.inc"')
    text=replace(text,'bool endpoint_requested=((uintptr_t)arg>>8)&1u;','bool endpoint_requested=((uintptr_t)arg>>8)&1u;bool transport_requested=((uintptr_t)arg>>9)&1u;')
    text=replace(text,'c->endpoint_requested=endpoint_requested;','c->transport_requested=transport_requested;c->endpoint_requested=endpoint_requested;')
    text=replace(text,'    finish(c,rc);','    if(!rc&&c->endpoint_confirmed&&c->transport_requested)transport_run(c);\n    finish(c,rc);')
    files['NativeRuntime.inc']=text.encode()
    text=files['NativeExports.inc'].decode()
    text=replace(text,'unsigned enabled=0,wlan=0,budget=0,gen=3,endpoint=0;','unsigned enabled=0,wlan=0,budget=0,gen=3,endpoint=0,transport=0,smmu=0;\n    PE_parse_boot_argn("ewt",&transport,sizeof(transport));PE_parse_boot_argn("esm",&smmu,sizeof(smmu));')
    text=replace(text,'if(endpoint>1||','if(transport>1||(transport&&(smmu!=1||endpoint!=1))||endpoint>1||')
    text=replace(text,'(gen|(endpoint<<8))','(gen|(endpoint<<8)|(transport<<9))')
    text+='''
extern "C" int elden_pcie_transport_status(EldenPcieTransportStatus *out){
    if(!out)return -22;if(__atomic_load_n(&run,__ATOMIC_ACQUIRE)!=2)return -11;
    return transport_snapshot(__atomic_load_n(&active,__ATOMIC_ACQUIRE),out);
}
'''
    files['NativeExports.inc']=text.encode();return files
