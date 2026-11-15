/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include "DmaTables.h"
class IOBufferMemoryDescriptor;
class IOMemoryMap;
/* One serialized kernel owner. No copy, static initializer or device writes. */
class EldenWifiDmaMemory final {
public:
    static int create(EldenWifiDmaMemory **out,uint32_t id0,uint32_t id2);
    /* A failed complete keeps *out and all still-owned references. Once
     * claimed, proof must verify DMA stopped + context/translation withdrawn
     * for the same owner/epoch before any buffer/table reference is released. */
    static int destroy(EldenWifiDmaMemory **out,const void *owner,uint64_t epoch,
        int (*release_proof)(const void *,uint64_t));
    int claimForContext(const void *owner,uint64_t epoch);
    int encodeContext(unsigned asid,EldenWifiSmmu4KContextImage *out);
    uint8_t *data() const {return ready_?data_:nullptr;}
    uint64_t dataPhysical() const {return ready_?data_pa_:0;}
    uint64_t tablePhysical() const {return ready_?table_pa_:0;}
    const EldenWifiDmaTables *tables() const {return &tables_;}
private:
    static void *operator new(size_t,void *storage) noexcept {return storage;}
    EldenWifiDmaMemory()=default;
    ~EldenWifiDmaMemory()=default;
    EldenWifiDmaMemory(const EldenWifiDmaMemory&)=delete;
    EldenWifiDmaMemory& operator=(const EldenWifiDmaMemory&)=delete;
    int initialize(uint32_t id0,uint32_t id2);
    int verify(IOBufferMemoryDescriptor *,size_t offset,void *,uint64_t,size_t,unsigned attribute);
    int publishTables();
    IOBufferMemoryDescriptor *data_memory_=nullptr,*table_memory_=nullptr;
    IOMemoryMap *data_map_=nullptr;
    uint8_t *data_=nullptr,*table_cpu_=nullptr;
    uint64_t data_pa_=0,table_pa_=0,epoch_=0;
    size_t line_=0;
    bool data_prepared_=false,table_prepared_=false,claimed_=false,ready_=false,cleanup_uncertain_=false;
    const void *owner_=nullptr;
    EldenWifiDmaTables tables_={};
};
