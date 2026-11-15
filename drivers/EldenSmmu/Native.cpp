/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "Native.h"
#include "DmaMemory.h"
#include "Domain.h"
#include "Irqs.h"
#include <IOKit/IODeviceMemory.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOLib.h>
#include <pexpert/pexpert.h>
#include <stdarg.h>
extern "C" {
int elden_wifi_smmu_early_guard(void);
void elden_usb_log_putc(char);
boolean_t ml_at_interrupt_context(void);
IOReturn armcpu_spi_attach(uint32_t,bool,void(*)(void*),void*,uint32_t*,uint64_t*);
IOReturn armcpu_spi_mask(uint32_t,bool);
extern volatile uint32_t armcpu_gic_ready;
}
namespace {
static unsigned run,stopping;
static EldenWifiSmmuStatus terminal;
static void log(const char *format,...){char line[320];va_list ap;va_start(ap,format);vsnprintf(line,sizeof(line),format,ap);va_end(ap);for(const char *p=line;*p;p++)elden_usb_log_putc(*p);}
struct Region {
    IOMemoryMap *keep=nullptr;uintptr_t va=0;size_t bytes=0;
    bool map(uint64_t pa,size_t n){
        if(keep)return false;IODeviceMemory *m=IODeviceMemory::withRange(pa,n);if(!m)return false;
        keep=m->map(kIOMapAnywhere|kIOMapInhibitCache);m->release();if(!keep)return false;
        va=keep->getVirtualAddress();bytes=n;return va!=0;
    }
    int read32(size_t off,uint32_t *v){if(!va||!v||(off&3)||off>bytes-4)return -14;uintptr_t p=va+off;__asm__ volatile("ldr %w0,[%1]":"=r"(*v):"r"(p):"memory");return 0;}
    int read64(size_t off,uint64_t *v){if(!va||!v||(off&7)||off>bytes-8)return -14;uintptr_t p=va+off;__asm__ volatile("ldr %0,[%1]":"=r"(*v):"r"(p):"memory");return 0;}
    int write32(size_t off,uint32_t v){if(!va||(off&3)||off>bytes-4)return -14;uintptr_t p=va+off;__asm__ volatile("str %w0,[%1]\n\tdsb sy"::"r"(v),"r"(p):"memory");return 0;}
    int write64(size_t off,uint64_t v){if(!va||(off&7)||off>bytes-8)return -14;uintptr_t p=va+off;__asm__ volatile("str %0,[%1]\n\tdsb sy"::"r"(v),"r"(p):"memory");return 0;}
};
struct Context;
struct IrqCookie {Context *context;unsigned kind,intid;};
struct Context {
    static void *operator new(size_t n) noexcept{return IOMalloc(n);}
    static void operator delete(void *p) noexcept{if(p)IOFree(p,sizeof(Context));}
    Region smmu,wlan;
    EldenSmmuSelection selection={};EldenSmmuDomain domain={};EldenWifiDmaMemory *memory=nullptr;
    IrqCookie irq[2]={{this,0,EldenSmmuGlobalIntid},{this,1,0}};
    unsigned attached[2]={0,0};bool memory_claimed=false;
    unsigned fault_claimed=0,fault_complete=0,fault_kind=0,fault_status=0,fault_syndrome=0,fault_reads_failed=0;
    unsigned spurious[2]={0,0};
    uint64_t fault_address=0;
    uint32_t stage=0;
};
static Context *active;
static uint64_t now(void*){uint64_t t;__asm__ volatile("mrs %0,cntpct_el0":"=r"(t));return t/96*5+(t%96)*5/96;}
static void delay(void*,unsigned us){IODelay(us);}
static int basic(void *p){
    Context *c=static_cast<Context*>(p);
    if(!c||__atomic_load_n(&stopping,__ATOMIC_ACQUIRE)||__atomic_load_n(&c->fault_claimed,__ATOMIC_ACQUIRE)||
       ml_at_interrupt_context()||!armcpu_gic_ready||!elden_wifi_smmu_early_guard())return -11;
    uint32_t io=UINT32_MAX,ctl=UINT32_MAX;
    if(c->wlan.read32(0,&ctl)||c->wlan.read32(4,&io))return -5;
    /* No pin write here. GPIO mux and both observed/latched WLAN_EN must be low. */
    if(ctl==UINT32_MAX||io==UINT32_MAX||(ctl&0x3c)||(io&3))return -16;
    return 0;
}
static int domain_admit(void *p){Context *c=static_cast<Context*>(p);int rc=basic(p);return rc?rc:(!__atomic_load_n(&c->attached[0],__ATOMIC_ACQUIRE)||!__atomic_load_n(&c->attached[1],__ATOMIC_ACQUIRE)||!c->memory_claimed)?-11:0;}
static int read32(void *p,size_t off,uint32_t *v){
    Context *c=static_cast<Context*>(p);int rc=basic(p);if(rc)return rc;
    if(!(off<0x2000||(off>=0x80000&&off<0xd3000)))return -22;
    if(c->stage==2&&off>=0x80000&&!(off&4095))log("\nELDEN_SMMU read-context bank=%u offset=%x\n",(unsigned)((off-0x80000)/4096),(unsigned)off);
    return c->smmu.read32(off,v);
}
static int select_read(void *p,uint32_t off,uint32_t *v){return read32(p,off,v);}
static int read64(void *p,size_t off,uint64_t *v){
    Context *c=static_cast<Context*>(p);int rc=domain_admit(p);if(rc)return rc;
    size_t cb=0x80000+4096*c->selection.route.bank;
    if(off!=cb+0x20&&off!=cb+0x28&&off!=cb+0x50&&off!=cb+0x60)return -22;
    return c->smmu.read64(off,v);
}
static int write32(void *p,size_t off,uint32_t value){
    Context *c=static_cast<Context*>(p);int rc=domain_admit(p);if(rc)return rc;
    if(elden_smmu_boot_route_state()!=EldenSmmuBootPreparing)return -16;
    unsigned bank=c->selection.route.bank,slot=c->selection.route.slot;size_t cb=0x80000+4096*bank;
    if(off!=0x800+4*slot&&off!=0xc00+4*slot&&off!=0x1000+4*bank&&off!=0x1800+4*bank&&
       off!=cb&&off!=cb+0x10&&off!=cb+0x30&&off!=cb+0x38&&off!=cb+0x3c&&off!=cb+0x58&&
       off!=cb+0x610&&off!=cb+0x618&&off!=cb+0x7f0)return -22;
    return c->smmu.write32(off,value);
}
static int write64(void *p,size_t off,uint64_t value){
    Context *c=static_cast<Context*>(p);int rc=domain_admit(p);if(rc)return rc;
    if(elden_smmu_boot_route_state()!=EldenSmmuBootPreparing)return -16;
    size_t cb=0x80000+4096*c->selection.route.bank;
    if(off!=cb+0x20&&off!=cb+0x28&&off!=cb+0x810&&off!=cb+0x818)return -22;
    if((off==cb+0x810||off==cb+0x818)&&(c->selection.id0&(1u<<26)))return -95;
    return c->smmu.write64(off,value);
}
static int barrier(void *p){int rc=domain_admit(p);if(rc)return rc;__asm__ volatile("dsb sy\n\tisb":::"memory");return 0;}
static void progress(void *p,unsigned stage,unsigned translations){Context *c=static_cast<Context*>(p);c->stage=10+stage;log("\nELDEN_SMMU domain-stage=%u translations=%u\n",stage,translations);}
static void fault(void *p){
    auto *cookie=static_cast<IrqCookie*>(p);Context *c=cookie->context;
    size_t cb=0x80000+4096*c->selection.route.bank;uint32_t status=UINT32_MAX;
    int read_error=c->smmu.read32(cookie->kind?cb+0x58:0x48,&status);
    if(!read_error&&!(status&(cookie->kind?0xc00001feu:UINT32_MAX))){
        if(__atomic_add_fetch(&c->spurious[cookie->kind],1u,__ATOMIC_RELAXED)<128)return;
    }
    /* Mask only this registered line. Leave SMMU fault registers latched; no
     * global fault acknowledgement, recovery, allocation or console lock here. */
    (void)armcpu_spi_mask(cookie->intid,true);
    unsigned expected=0;
    if(!__atomic_compare_exchange_n(&c->fault_claimed,&expected,1,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return;
    c->fault_kind=cookie->kind+1;c->fault_status=status;
    if(read_error)c->fault_reads_failed|=1;
    if(c->smmu.read32(cookie->kind?cb+0x68:0x50,&c->fault_syndrome))c->fault_reads_failed|=2;
    if(cookie->kind&&c->smmu.read64(cb+0x60,&c->fault_address))c->fault_reads_failed|=4;
    __atomic_store_n(&c->fault_complete,1u,__ATOMIC_RELEASE);
}
static int attach_irqs(Context *c){
    c->irq[1].intid=elden_smmu_context_intids[c->selection.route.bank];
    uint64_t mpidr;__asm__ volatile("mrs %0,mpidr_el1":"=r"(mpidr));uint64_t affinity=mpidr&0xff00ffffffULL;
    for(unsigned i=0;i<2;i++){
        uint32_t observed=0;uint64_t router=0;
        IOReturn rc=armcpu_spi_attach(c->irq[i].intid,false,fault,&c->irq[i],&observed,&router);
        if(rc)return (int)rc;
        __atomic_store_n(&c->attached[i],1u,__ATOMIC_RELEASE);
        log("\nELDEN_SMMU irq kind=%u intid=%u flags=%08x router=%llx\n",i,c->irq[i].intid,observed,(unsigned long long)router);
        if(observed!=0xa003||router!=affinity)return -71;
        if(basic(c))return -11;
    }
    return 0;
}
static void finish(Context *c,int error){
    terminal.version=1;terminal.run=error?3:2;terminal.error=error;
    if(c){
        terminal.stage=c->stage;terminal.bank=c->selection.route.bank;terminal.slot=c->selection.route.slot;terminal.asid=c->selection.asid;
        terminal.translations=c->domain.translations;terminal.selection_reads=c->selection.reads;
        terminal.translation_mode=c->domain.translation_mode;
        terminal.software_pages=c->domain.software_pages;
        terminal.global_irq=c->irq[0].intid;terminal.context_irq=c->irq[1].intid;
        terminal.context_sctlr=c->domain.program.readback.sctlr;terminal.context_tcr2=c->domain.program.readback.tcr2;
        terminal.last_iova=c->domain.last_iova;terminal.last_par=c->domain.last_par;
        if(c->memory){terminal.data_physical=c->memory->dataPhysical();terminal.table_physical=c->memory->tablePhysical();
            terminal.table_pages=(uint32_t)c->memory->tables()->result.table_pages;terminal.leaf_pages=(uint32_t)c->memory->tables()->result.leaf_pages;}
        if(error)for(unsigned i=0;i<2;i++)if(__atomic_load_n(&c->attached[i],__ATOMIC_ACQUIRE))(void)armcpu_spi_mask(c->irq[i].intid,true);
    }
    log("\nELDEN_SMMU end rc=%d stage=%u bank=%u slot=%u asid=%u translations=%u translation-mode=%u software-pages=%u pages=%u/%u data=%llx tables=%llx sctlr=%x tcr2=%x\n",
        error,terminal.stage,terminal.bank,terminal.slot,terminal.asid,terminal.translations,terminal.translation_mode,terminal.software_pages,terminal.table_pages,terminal.leaf_pages,
        (unsigned long long)terminal.data_physical,(unsigned long long)terminal.table_physical,terminal.context_sctlr,terminal.context_tcr2);
    __atomic_store_n(&run,terminal.run,__ATOMIC_RELEASE);
}
static int initialize(Context *c){
    c->stage=1;log("\nELDEN_SMMU begin early=1 dma=0\n");
    if(!c->wlan.map(0x0f110000,4096)||!c->smmu.map(0x15000000,0x100000))return -12;
    int rc=basic(c);if(rc)return rc;
    c->stage=2;EldenSmmuSelectIo select={c,basic,select_read};rc=elden_smmu_select_boot_domain(&select,&c->selection);
    log("\nELDEN_SMMU selection rc=%d stage=%u last=%x:%x reads=%u bank=%u asid=%u cb0=%x\n",rc,c->selection.stage,c->selection.last_offset,
        c->selection.last_value,c->selection.reads,c->selection.route.bank,c->selection.asid,c->selection.cb0_sctlr);if(rc)return rc;
    c->stage=3;rc=EldenWifiDmaMemory::create(&c->memory,c->selection.id0,c->selection.id2);if(rc)return rc;
    if((rc=basic(c)))return rc;
    c->stage=4;if((rc=attach_irqs(c)))return rc;
    c->stage=5;rc=c->memory->claimForContext(c,1);if(rc)return rc;c->memory_claimed=true;
    EldenSmmuDomainOps ops={c,domain_admit,now,delay,progress,{c,0x100000,read32,read64,write32,write64,barrier}};
    return elden_smmu_domain_start(&c->domain,&ops,&c->selection,c->memory->tables());
}
}
extern "C" int elden_wifi_smmu_early_initialize(void){
    unsigned enabled=0;PE_parse_boot_argn("esm",&enabled,sizeof(enabled));if(!enabled)return 0;
    unsigned root=0,wlan=0,budget=0,endpoint=0;
    PE_parse_boot_argn("elden-pcie-root",&root,sizeof(root));PE_parse_boot_argn("elden-wlan-power",&wlan,sizeof(wlan));
    PE_parse_boot_argn("elden-pcie-full-on",&budget,sizeof(budget));PE_parse_boot_argn("epe",&endpoint,sizeof(endpoint));
    if(root!=1||wlan!=1||budget!=1||endpoint!=1)return -22;
    unsigned expected=0;if(enabled!=1||!__atomic_compare_exchange_n(&run,&expected,1,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return -16;
    Context *c=new Context;if(!c){finish(nullptr,-12);return -12;}
    __atomic_store_n(&active,c,__ATOMIC_RELEASE);int rc=initialize(c);
    if(!rc&&__atomic_load_n(&c->fault_claimed,__ATOMIC_ACQUIRE))rc=-5;
    finish(c,rc);return rc;
}
extern "C" int elden_wifi_smmu_ready(void){
    Context *c=__atomic_load_n(&active,__ATOMIC_ACQUIRE);
    return c&&__atomic_load_n(&run,__ATOMIC_ACQUIRE)==2&&!__atomic_load_n(&stopping,__ATOMIC_ACQUIRE)&&!__atomic_load_n(&c->fault_claimed,__ATOMIC_ACQUIRE);
}
extern "C" int elden_wifi_smmu_status(EldenWifiSmmuStatus *out){
    if(!out)return -22;unsigned state=__atomic_load_n(&run,__ATOMIC_ACQUIRE);if(state<2)return -11;
    Context *c=__atomic_load_n(&active,__ATOMIC_ACQUIRE);*out=terminal;out->ready=elden_wifi_smmu_ready();out->stopping=__atomic_load_n(&stopping,__ATOMIC_ACQUIRE);
    if(c){out->fault_claimed=__atomic_load_n(&c->fault_claimed,__ATOMIC_ACQUIRE);out->fault_complete=out->fault_claimed?__atomic_load_n(&c->fault_complete,__ATOMIC_ACQUIRE):0;
        if(out->fault_claimed&&!out->fault_complete)return -11;
        if(out->fault_claimed){out->ready=0;out->fault_kind=c->fault_kind;out->fault_status=c->fault_status;out->fault_syndrome=c->fault_syndrome;out->fault_address=c->fault_address;out->fault_reads_failed=c->fault_reads_failed;}
        out->spurious_global=__atomic_load_n(&c->spurious[0],__ATOMIC_RELAXED);out->spurious_context=__atomic_load_n(&c->spurious[1],__ATOMIC_RELAXED);}
    return 0;
}
extern "C" void elden_wifi_smmu_stop_begin(void){
    __atomic_store_n(&stopping,1u,__ATOMIC_RELEASE);Context *c=__atomic_load_n(&active,__ATOMIC_ACQUIRE);
    if(c){int rc[2]={0,0};for(unsigned i=0;i<2;i++)if(__atomic_load_n(&c->attached[i],__ATOMIC_ACQUIRE))rc[i]=(int)armcpu_spi_mask(c->irq[i].intid,true);
        log("\nELDEN_SMMU stop irq-mask=%d/%d resources-retained=1 dma-started=0 fault=%u\n",rc[0],rc[1],__atomic_load_n(&c->fault_claimed,__ATOMIC_ACQUIRE));}
}
