// SPDX-License-Identifier: BSD-2-Clause-Patent
#include "DmaPlan.h"
#include "EldenUfsPrdtAlgorithm.h"
extern "C" uint64_t elden_ufs_dma_limit(uint32_t idr2,bool host64,bool identity){
    if(!identity)return 0;
    const unsigned widths[6]={32,36,40,42,44,48};unsigned bits=host64?48u:32u;
    for(unsigned shift=0;shift<=8;shift+=4){
        unsigned code=(idr2>>shift)&15;if(code>5)return 0;
        if(widths[code]<bits)bits=widths[code];
    }
    return 1ULL<<bits;
}
extern "C" bool elden_ufs_prdt_build(uintptr_t va,uint64_t bytes,uint64_t capacity,uint64_t limit,
                                    EldenUfsPageAddress page,void *context,EldenUfsPrdtPlan *out){
    if(!va||!out||!page||!bytes||bytes>capacity||limit<(1ULL<<32)||limit>(1ULL<<48)||
       (limit&(limit-1))||bytes>UINTPTR_MAX-va)return false;
    elden_prdt::UfsPrd raw[elden_prdt::kMaxPrds]={};
    auto map=[&](const void *address)->uint64_t{
        uint64_t offset=reinterpret_cast<uintptr_t>(address)-va;
        if(offset>bytes||4096>bytes-offset)return 0;
        uint64_t physical=page(context,offset);
        return physical&&physical<limit&&4096<=limit-physical?physical:0;
    };
    unsigned count=elden_prdt::eldenUfsBuildPrds(reinterpret_cast<const void*>(va),bytes,raw,map);
    if(!count)return false;
    uint64_t total=0;for(unsigned i=0;i<count;++i)total+=raw[i].bytes;
    if(total!=bytes)return false;
    out->count=count;out->bytes=static_cast<uint32_t>(bytes);
    for(unsigned i=0;i<count;++i)out->entries[i]={raw[i].addr,raw[i].bytes,0};
    return true;
}
