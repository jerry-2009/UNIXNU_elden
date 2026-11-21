/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "DmaMemory.h"
#include "TestDmaPlatform.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vector>
static unsigned checks,cases;
#define CHECK(x) do { checks++;if(!(x)){fprintf(stderr,"line%d %s\n",__LINE__,#x);abort();} } while(0)
void *kernel_task=(void *)1;
static IOBufferMemoryDescriptor *objects[2];
static std::vector<void *> heaps;
static unsigned allocations,fail_alloc,fail_prepare,fail_complete,completed,releases,translations,cleans,maps;
static bool bad_attribute,bad_segment,overlap,fail_map;
static bool split_segments,physical_gap;
static bool static_shortcut;
static bool lazy_mapping;
static size_t line=64;
void *IOMalloc(size_t n){void *p=calloc(1,n);CHECK(p);heaps.push_back(p);return p;}
void IOFree(void *p,size_t){for(auto &h:heaps)if(h==p){h=nullptr;free(p);return;}CHECK(false);}
IOBufferMemoryDescriptor *IOBufferMemoryDescriptor::inTaskWithOptions(void *task,IOOptionBits flags,size_t n,size_t alignment){
    CHECK(task==kernel_task&&flags==(kIODirectionInOut|kIOMemoryPhysicallyContiguous|kIOMemoryMapperNone));
    unsigned i=allocations++;CHECK(i<2);if(i+1==fail_alloc)return nullptr;
    auto *m=new IOBufferMemoryDescriptor;m->index=i;m->bytes=n;
    CHECK(!posix_memalign((void **)&m->cpu,alignment,n));
    m->pa=i?(overlap?0x900001000ULL:0x980000000ULL):0x900001000ULL;objects[i]=m;return m;
}
int IOGeneralMemoryDescriptor::prepare(unsigned d){CHECK(d==kIODirectionInOut&&!prepared);if(index+1==fail_prepare)return -5;prepared=true;return 0;}
int IOGeneralMemoryDescriptor::complete(unsigned d){CHECK(d==kIODirectionInOut&&prepared);completed++;if(index+1==fail_complete)return -5;prepared=false;return 0;}
uint64_t IOGeneralMemoryDescriptor::getPhysicalSegment(size_t off,IOByteCount *length,unsigned mapper){
    CHECK(prepared&&off<bytes&&mapper==kIOMemoryMapperNone&&length);
    *length=bytes-off;if(bad_segment&&index==0&&off==4096)*length=2048;
    if(split_segments&&index==0){size_t remaining=(64u<<20)-(off% (64u<<20));if(*length>remaining)*length=remaining;}
    return pa+off+((physical_gap&&index==0&&off>=(64u<<20))?4096:0);
}
void *IOBufferMemoryDescriptor::getBytesNoCopy(){CHECK(prepared);return cpu;}
void IOBufferMemoryDescriptor::release(){CHECK(objects[index]==this&&!prepared);objects[index]=nullptr;free(cpu);releases++;delete this;}
IOMemoryMap *IOGeneralMemoryDescriptor::createMappingInTask(void *task,unsigned offset,unsigned options){
    CHECK(task==kernel_task&&!offset&&(options&~(kIOMapUnique|kIOMapPrefault))==(kIOMapAnywhere|kIOMapWriteCombineCache)&&index==0&&prepared&&cleans==1);
    if(fail_map)return nullptr;
    auto *m=new IOMemoryMap;m->memory=this;nc=!static_shortcut||(options&kIOMapUnique);present=!lazy_mapping||(options&kIOMapPrefault);maps++;return m;
}
uintptr_t IOMemoryMap::getVirtualAddress(){return (uintptr_t)memory->cpu;}
void IOMemoryMap::release(){CHECK(maps);memory->nc=false;maps--;delete this;}
uint64_t mock_translate(uintptr_t va,bool){
    translations++;
    for(auto *m:objects)if(m&&va>=(uintptr_t)m->cpu&&va-(uintptr_t)m->cpu<m->bytes){
        uint64_t pa=m->pa+va-(uintptr_t)m->cpu;
        if(m->nc&&!m->present)return 0x80d;
        unsigned attr=m->nc?(bad_attribute?0xff:0x44):0xff;
        return pa|((uint64_t)attr<<56);
    }
    CHECK(false);return 1;
}
void mock_clean(void *p,size_t n,size_t l){
    CHECK(l==line&&l==64);cleans++;
    if(cleans==1)CHECK(objects[0]&&p==objects[0]->cpu&&n==objects[0]->bytes&&!objects[0]->nc);
    else CHECK(objects[1]&&p==objects[1]->cpu&&n==objects[1]->bytes);
}
size_t mock_cache_line(){return line;}
static void reset(){
    CHECK(!objects[0]&&!objects[1]&&!maps);
    for(void *p:heaps)CHECK(!p);
    heaps.clear();allocations=fail_alloc=fail_prepare=fail_complete=completed=releases=translations=cleans=maps=0;
    bad_attribute=bad_segment=overlap=fail_map=split_segments=physical_gap=static_shortcut=lazy_mapping=false;line=64;cases++;
}
static int proof_rc,proof_calls;
static int proof(const void *p,uint64_t epoch){CHECK(p==(void *)1&&epoch==37);proof_calls++;return proof_rc;}
int main(){
    EldenWifiDmaMemory *m=nullptr;EldenWifiDmaMemoryReport report={};reset();CHECK(!EldenWifiDmaMemory::createWithReport(&m,0x4c017e84,0x5111,&report));
    CHECK(report.version==1&&report.stage==14&&!report.return_status&&!report.cleanup_attempted);
    CHECK(report.data_segment_bytes==(130u<<20)&&report.table_segment_bytes==66*4096);
    CHECK(m&&m->data()&&m->dataPhysical()==0x900200000ULL&&m->tablePhysical()==0x980000000ULL);
    CHECK(m->tables()->result.leaf_pages==32768&&m->tables()->result.table_pages==66);
    CHECK(translations==2*((130u<<20)/4096+66+(128u<<20)/4096));
    EldenWifiSmmu4KContextImage image={};CHECK(!m->encodeContext(7,&image));
    CHECK(image.cbar==0x1f300&&image.cba2r==1&&image.tcr2==0x38011&&image.ttbr0==((7ULL<<48)|m->tablePhysical()));
    CHECK(!m->claimForContext((void *)1,37));CHECK(m->claimForContext((void *)1,37)==-22);
    CHECK(EldenWifiDmaMemory::destroy(&m,nullptr,0,nullptr)==-16&&completed==0);
    proof_rc=-16;CHECK(EldenWifiDmaMemory::destroy(&m,(void *)1,37,proof)==-16&&completed==0);
    proof_rc=0;CHECK(!EldenWifiDmaMemory::destroy(&m,(void *)1,37,proof)&&!m&&releases==2);
    for(unsigned test=0;test<9;test++){
        reset();
        if(test<2)fail_alloc=test+1;
        if(test==2)fail_prepare=1;
        if(test==3)fail_prepare=2;
        if(test==4)bad_attribute=true;
        if(test==5)bad_segment=true;
        if(test==6)overlap=true;
        if(test==7)fail_map=true;
        if(test==8)line=8192;
        CHECK(EldenWifiDmaMemory::createWithReport(&m,0x4c017e84,0x5111,&report)<0&&!m&&!objects[0]&&!objects[1]&&!maps);
        const unsigned stages[]={3,3,4,5,11,7,6,10,2};CHECK(report.stage==stages[test]&&report.cleanup_attempted&&!report.cleanup_status);
        if(test==4)CHECK(report.reason==4&&report.expected_attribute==0x44&&(report.par>>56)==0xff);
        if(test==5)CHECK(report.reason==2&&report.offset==4096&&report.segment_bytes==2048);
        if(test==6)CHECK(report.reason==5);
    }
    reset();CHECK(EldenWifiDmaMemory::create(&m,0,0)==-95&&!m&&!allocations);
    reset();CHECK(!EldenWifiDmaMemory::create(&m,0x4c017e84,0x5111));
    uint64_t saved=((uint64_t *)objects[1]->cpu)[512];((uint64_t *)objects[1]->cpu)[512]=3;
    CHECK(m->encodeContext(7,&image)!=0&&m->claimForContext((void *)1,37)!=0);
    ((uint64_t *)objects[1]->cpu)[512]=saved;CHECK(!EldenWifiDmaMemory::destroy(&m,nullptr,0,nullptr));
    reset();split_segments=true;
#if defined(ELDEN_TEST_SEGMENTED) && ELDEN_TEST_SEGMENTED
    CHECK(!EldenWifiDmaMemory::createWithReport(&m,0x4c017e84,0x5111,&report));
    CHECK(report.stage==14&&report.data_segment_bytes==(64u<<20)&&m->tables()->result.leaf_pages==32768);
    CHECK(!EldenWifiDmaMemory::destroy(&m,nullptr,0,nullptr));
#else
    CHECK(EldenWifiDmaMemory::createWithReport(&m,0x4c017e84,0x5111,&report)==-71&&!m);
    CHECK(report.stage==6&&report.reason==2&&report.data_segment_bytes==(64u<<20));
#endif
    reset();split_segments=physical_gap=true;
    CHECK(EldenWifiDmaMemory::createWithReport(&m,0x4c017e84,0x5111,&report)==-71&&!m);
#if defined(ELDEN_TEST_SEGMENTED) && ELDEN_TEST_SEGMENTED
    CHECK(report.stage==7&&report.reason==2&&report.offset==(64u<<20)&&report.physical==report.expected_physical+4096&&!cleans&&!maps);
#else
    CHECK(report.stage==6&&report.reason==2);
#endif
    reset();static_shortcut=true;
#if defined(ELDEN_TEST_UNIQUE) && ELDEN_TEST_UNIQUE
    CHECK(!EldenWifiDmaMemory::createWithReport(&m,0x4c017e84,0x5111,&report)&&report.stage==14);
    CHECK(!EldenWifiDmaMemory::destroy(&m,nullptr,0,nullptr));
#else
    CHECK(EldenWifiDmaMemory::createWithReport(&m,0x4c017e84,0x5111,&report)==-71&&!m&&report.stage==11&&report.reason==4);
#endif
    reset();lazy_mapping=true;
#if defined(ELDEN_TEST_PREFAULT) && ELDEN_TEST_PREFAULT
    CHECK(!EldenWifiDmaMemory::createWithReport(&m,0x4c017e84,0x5111,&report)&&report.stage==14);
    CHECK(!EldenWifiDmaMemory::destroy(&m,nullptr,0,nullptr));
#else
    CHECK(EldenWifiDmaMemory::createWithReport(&m,0x4c017e84,0x5111,&report)==-71&&!m&&report.stage==11&&report.reason==3&&report.par==0x80d);
#endif
    reset();fail_map=true;fail_complete=2;CHECK(EldenWifiDmaMemory::createWithReport(&m,0x4c017e84,0x5111,&report)==-5&&m);
    CHECK(report.stage==10&&report.initialize_status==-12&&report.cleanup_attempted&&report.cleanup_status==-5&&report.return_status==-5);
    CHECK(!m->data()&&m->claimForContext((void *)1,37)<0);unsigned before=completed;
    CHECK(EldenWifiDmaMemory::destroy(&m,nullptr,0,nullptr)==-5&&m&&completed==before&&!releases);
    /* Model whole-platform reset: uncertain resources were deliberately not
     * released by production cleanup. Never offer this shortcut to the driver. */
    for(auto *o:objects)if(o){free(o->cpu);delete o;}
    objects[0]=objects[1]=nullptr;
    for(void *p:heaps)free(p);
    heaps.clear();m=nullptr;
    printf("%u allocator/lifetime scenarios / %u checks passed; kernel mappings/cache modeled\n",cases,checks);
    return 0;
}
