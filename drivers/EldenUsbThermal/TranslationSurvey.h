/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* AT walks translation tables. It does NOT read/write the target FIFO.
 * Only version/APID/ownership tables are read through MMIO below. */
#pragma once
#include <IOKit/IODeviceMemory.h>
#include <IOKit/IOMemoryDescriptor.h>
#include "EldenAdcResources.h"
extern "C" boolean_t ml_set_interrupts_enabled(boolean_t);
namespace elden_spmi_translation {
struct Mapping {
    IOMemoryMap *map=nullptr;
    uintptr_t address=0;
    ~Mapping(){if(map)map->release();}
    bool open(uint64_t physical,unsigned bytes){
        IODeviceMemory *m=IODeviceMemory::withRange(physical,bytes);
        if(!m)return false;
        map=m->map(kIOMapAnywhere|kIOMapInhibitCache);m->release();
        address=map?(uintptr_t)map->getVirtualAddress():0;return address!=0;
    }
    uint32_t read(unsigned off){
        uint32_t value;__asm__ volatile("ldr %w0,[%1]":"=r"(value):"r"(address+off):"memory");return value;
    }
};
static void translate(uintptr_t va,uint64_t *read_par,uint64_t *write_par){
    boolean_t enabled=ml_set_interrupts_enabled(false);
    uint64_t old,r,w;
    __asm__ volatile("mrs %0,par_el1\n\tat s1e1r,%3\n\tisb\n\tmrs %1,par_el1\n\tat s1e1w,%3\n\tisb\n\tmrs %2,par_el1\n\tmsr par_el1,%0"
                     :"=&r"(old),"=&r"(r),"=&r"(w):"r"(va):"memory");
    ml_set_interrupts_enabled(enabled);*read_par=r;*write_par=w;
}
static bool run(void (*log)(const char *,...)){
    Mapping core,owner;
    if(!core.open(ELDEN_ADC_SPMI_CORE,ELDEN_ADC_SPMI_CORE_BYTES)||
       !owner.open(ELDEN_ADC_SPMI_OWNER,ELDEN_ADC_SPMI_OWNER_BYTES))return false;
    if(core.read(0)!=ELDEN_ADC_SPMI_VERSION||(core.read(4)&0x7ff)!=ELDEN_ADC_SPMI_APIDS)return false;
    /* Existing recovery SDAM, ADC SDAM, and the historical DC endpoint.
     * Exact APID is discovered; no owner, FIFO or command register is written. */
    const unsigned ppids[]={0x071,0x090,0x72a};
    for(unsigned ppid:ppids){
        unsigned apid=0,count=0;
        for(unsigned i=0;i<ELDEN_ADC_SPMI_APIDS;i++){
            uint32_t row=core.read(0x2000+4*i);
            if(row&&((row>>8)&0xfff)==ppid&&(owner.read(4*i)&7)==ELDEN_ADC_SPMI_EE){apid=i;count++;}
        }
        if(count!=1){log("\nELDEN_SPMI_AT refused ppid=%x matches=%u\n",ppid,count);return false;}
        uint64_t physical=ELDEN_ADC_SPMI_WRITER+0x1000ull*apid;
        Mapping writer;
        if(!writer.open(physical,4096))return false;
        if(((core.read(0x2000+4*apid)>>8)&0xfff)!=ppid||(owner.read(4*apid)&7)!=ELDEN_ADC_SPMI_EE)return false;
        uint64_t r=0,w=0;translate(writer.address+0x10,&r,&w);
        log("\nELDEN_SPMI_AT ppid=%x apid=%u fifo-pa=%llx va=%llx read-par=%016llx write-par=%016llx; translation only, no FIFO access\n",
            ppid,apid,(unsigned long long)(physical+0x10),(unsigned long long)(writer.address+0x10),
            (unsigned long long)r,(unsigned long long)w);
    }
    return true;
}
}
