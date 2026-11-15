/* SPDX-License-Identifier: GPL-2.0-only */
extern "C" void elden_pcie_native_start(void){
    unsigned enabled=0,wlan=0,budget=0,gen=3;
    PE_parse_boot_argn("elden-pcie-root",&enabled,sizeof(enabled));PE_parse_boot_argn("elden-wlan-power",&wlan,sizeof(wlan));
    PE_parse_boot_argn("elden-pcie-full-on",&budget,sizeof(budget));PE_parse_boot_argn("elden-pcie-gen",&gen,sizeof(gen));
    if(enabled!=1||wlan!=1||budget!=1||gen<1||gen>3||__atomic_load_n(&stop_requested,__ATOMIC_ACQUIRE))return;
    unsigned expected=0;if(!__atomic_compare_exchange_n(&run,&expected,1,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return;
    thread_t thread=nullptr;
    if(kernel_thread_start(worker,(void *)(uintptr_t)gen,&thread)==KERN_SUCCESS)thread_deallocate(thread);
    else finish(nullptr,-12);
}
extern "C" void elden_pcie_native_stop_begin(void){__atomic_store_n(&stop_requested,1u,__ATOMIC_RELEASE);}
extern "C" int elden_pcie_native_status(EldenPcieNativeStatus *out){
    if(!out)return -22;
    if(__atomic_load_n(&run,__ATOMIC_ACQUIRE)!=2)return -11;
    *out=terminal;out->stopped=__atomic_load_n(&stopped,__ATOMIC_ACQUIRE);
    if(out->stopped)out->perst_high=0;
    return 0;
}
