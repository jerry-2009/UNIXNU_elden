/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "DmaMemory.h"
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IOLib.h>
#include <kern/task.h>
#include <string.h>

namespace {
constexpr size_t Block=2u<<20,DataAllocation=EldenWifiDmaBytes+Block,TableAllocation=EldenWifiTablePages*4096;
static uint64_t translate(uintptr_t address,bool write){
    uint64_t daif,saved,result;
    if(write)__asm__ volatile("mrs %0,daif\n\tmsr daifset,#2\n\tmrs %1,par_el1\n\tat s1e1w,%3\n\tisb\n\tmrs %2,par_el1\n\tmsr par_el1,%1\n\tmsr daif,%0"
        :"=&r"(daif),"=&r"(saved),"=&r"(result):"r"(address):"memory");
    else __asm__ volatile("mrs %0,daif\n\tmsr daifset,#2\n\tmrs %1,par_el1\n\tat s1e1r,%3\n\tisb\n\tmrs %2,par_el1\n\tmsr par_el1,%1\n\tmsr daif,%0"
        :"=&r"(daif),"=&r"(saved),"=&r"(result):"r"(address):"memory");
    return result;
}
static void clean(void *start,size_t bytes,size_t line){
    uintptr_t first=(uintptr_t)start,end=first+bytes;
    for(uintptr_t at=first;at<end;at+=line)__asm__ volatile("dc civac,%0"::"r"(at):"memory");
    __asm__ volatile("dsb sy":::"memory");
}
}
int EldenWifiDmaMemory::verify(IOBufferMemoryDescriptor *memory,size_t offset,void *mapping,uint64_t pa,size_t bytes,unsigned attr){
    if(!memory||!mapping||!pa||!bytes||((uintptr_t)mapping&4095)||(pa&4095)||(bytes&4095)||
       bytes>UINTPTR_MAX-(uintptr_t)mapping||bytes>UINT64_MAX-pa)return -22;
    for(size_t at=0;at<bytes;at+=4096){
        IOByteCount length=0;uint64_t physical=memory->IOGeneralMemoryDescriptor::getPhysicalSegment(offset+at,&length,kIOMemoryMapperNone);
        if(physical!=pa+at||length<4096)return -71;
        for(unsigned access=0;access<2;access++){
            uint64_t par=translate((uintptr_t)mapping+at,access!=0);
            if((par&1)||((par>>56)&255)!=attr||(par&0x0000fffffffff000ULL)!=physical)return -71;
        }
    }
    return 0;
}
int EldenWifiDmaMemory::publishTables(){
    if(!table_prepared_||!table_cpu_||!tables_.ready)return -11;
    clean(table_cpu_,TableAllocation,line_);
    EldenWifiSmmu4KTableAuditResult audit={};return elden_wifi_dma_tables_audit(&tables_,&audit);
}
int EldenWifiDmaMemory::initialize(uint32_t id0,uint32_t id2){
    uint64_t ctr;__asm__ volatile("mrs %0,ctr_el0":"=r"(ctr));line_=4u<<((ctr>>16)&15);
    if(line_<32||line_>4096)return -95;
    const IOOptionBits options=static_cast<IOOptionBits>(kIODirectionInOut)|static_cast<IOOptionBits>(kIOMemoryPhysicallyContiguous)|static_cast<IOOptionBits>(kIOMemoryMapperNone);
    data_memory_=IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,options,DataAllocation,Block);
    table_memory_=IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,options,TableAllocation,4096);
    if(!data_memory_||!table_memory_)return -12;
    if(data_memory_->IOGeneralMemoryDescriptor::prepare(kIODirectionInOut)!=kIOReturnSuccess)return -5;
    data_prepared_=true;
    if(table_memory_->IOGeneralMemoryDescriptor::prepare(kIODirectionInOut)!=kIOReturnSuccess)return -5;
    table_prepared_=true;
    uint8_t *cached=static_cast<uint8_t *>(data_memory_->IOBufferMemoryDescriptor::getBytesNoCopy());
    table_cpu_=static_cast<uint8_t *>(table_memory_->IOBufferMemoryDescriptor::getBytesNoCopy());
    IOByteCount data_length=0,table_length=0;
    uint64_t base=data_memory_->IOGeneralMemoryDescriptor::getPhysicalSegment(0,&data_length,kIOMemoryMapperNone);
    table_pa_=table_memory_->IOGeneralMemoryDescriptor::getPhysicalSegment(0,&table_length,kIOMemoryMapperNone);
    if(!cached||!table_cpu_||!base||!table_pa_||data_length<DataAllocation||table_length<TableAllocation||
       base>UINT64_MAX-DataAllocation||table_pa_>UINT64_MAX-TableAllocation||(table_pa_&4095))return -71;
    if(base<table_pa_+TableAllocation&&table_pa_<base+DataAllocation)return -71;
    size_t shift=(Block-(base&(Block-1)))&(Block-1);data_pa_=base+shift;
    int rc=verify(data_memory_,0,cached,base,DataAllocation,0xff);if(rc)return rc;
    rc=verify(table_memory_,0,table_cpu_,table_pa_,TableAllocation,0xff);if(rc)return rc;
    /* The cached data mapping is used only here, before its NC alias exists. */
    memset(cached,0,DataAllocation);clean(cached,DataAllocation,line_);
    data_map_=data_memory_->createMappingInTask(kernel_task,0,kIOMapAnywhere|kIOMapWriteCombineCache);
    if(!data_map_||!data_map_->getVirtualAddress())return -12;
    uintptr_t mapped=data_map_->getVirtualAddress();if(mapped>UINTPTR_MAX-shift)return -71;
    data_=reinterpret_cast<uint8_t *>(mapped+shift);
    rc=verify(data_memory_,shift,data_,data_pa_,EldenWifiDmaBytes,0x44);if(rc)return rc;
    rc=elden_wifi_dma_tables_build(&tables_,id0,id2,data_pa_,table_pa_,reinterpret_cast<uint64_t *>(table_cpu_),EldenWifiDmaBytes);
    if(rc)return rc;
    return publishTables();
}
int EldenWifiDmaMemory::create(EldenWifiDmaMemory **out,uint32_t id0,uint32_t id2){
    if(!out||*out)return -22;
    if(!elden_wifi_dma_output_bits(id0,id2))return -95;
    void *raw=IOMalloc(sizeof(EldenWifiDmaMemory));if(!raw)return -12;
    auto *m=new(raw) EldenWifiDmaMemory;*out=m;int rc=m->initialize(id0,id2);
    if(rc){int cleanup=destroy(out,nullptr,0,nullptr);return cleanup?cleanup:rc;}
    m->ready_=true;
    return 0;
}
int EldenWifiDmaMemory::claimForContext(const void *owner,uint64_t epoch){
    if(!owner||!epoch||claimed_||!ready_||!tables_.ready)return -22;
    int rc=publishTables();if(rc)return rc;
    owner_=owner;epoch_=epoch;claimed_=true;return 0;
}
int EldenWifiDmaMemory::encodeContext(unsigned asid,EldenWifiSmmu4KContextImage *out){
    return ready_?elden_wifi_dma_context_image(&tables_,asid,out):-11;
}
int EldenWifiDmaMemory::destroy(EldenWifiDmaMemory **out,const void *owner,uint64_t epoch,int (*proof)(const void *,uint64_t)){
    if(!out||!*out)return -22;
    auto *m=*out;
    if(m->cleanup_uncertain_)return -5;
    if(m->claimed_){if(owner!=m->owner_||epoch!=m->epoch_||!proof)return -16;int rc=proof(owner,epoch);if(rc)return rc;}
    m->ready_=false;
    if(m->table_prepared_){if(m->table_memory_->IOGeneralMemoryDescriptor::complete(kIODirectionInOut)!=kIOReturnSuccess){m->cleanup_uncertain_=true;return -5;}m->table_prepared_=false;}
    if(m->data_prepared_){if(m->data_memory_->IOGeneralMemoryDescriptor::complete(kIODirectionInOut)!=kIOReturnSuccess){m->cleanup_uncertain_=true;return -5;}m->data_prepared_=false;}
    if(m->data_map_)m->data_map_->release();
    if(m->table_memory_)m->table_memory_->release();
    if(m->data_memory_)m->data_memory_->release();
    m->~EldenWifiDmaMemory();IOFree(m,sizeof(EldenWifiDmaMemory));*out=nullptr;return 0;
}
