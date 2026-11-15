/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include <stdint.h>
#include <stddef.h>
using IOOptionBits=uint64_t;
using IOByteCount=uint64_t;
enum {kIODirectionInOut=3,kIOMemoryPhysicallyContiguous=0x100,kIOMemoryMapperNone=0x200,
      kIOMapAnywhere=1,kIOMapWriteCombineCache=2,kIOMapUnique=4,kIOMapPrefault=8,kIOReturnSuccess=0};
extern void *kernel_task;
void *IOMalloc(size_t);
void IOFree(void *,size_t);
class IOMemoryMap;
class IOGeneralMemoryDescriptor {
public:
    unsigned index=0;uint8_t *cpu=nullptr;size_t bytes=0;uint64_t pa=0;bool prepared=false,nc=false,present=true;
    int prepare(unsigned);
    int complete(unsigned);
    uint64_t getPhysicalSegment(size_t,IOByteCount *,unsigned);
    IOMemoryMap *createMappingInTask(void *,unsigned,unsigned);
};
class IOBufferMemoryDescriptor:public IOGeneralMemoryDescriptor {
public:
    static IOBufferMemoryDescriptor *inTaskWithOptions(void *,IOOptionBits,size_t,size_t);
    void *getBytesNoCopy();
    void release();
};
class IOMemoryMap {
public:
    IOGeneralMemoryDescriptor *memory=nullptr;
    uintptr_t getVirtualAddress();
    void release();
};
uint64_t mock_translate(uintptr_t,bool);
void mock_clean(void *,size_t,size_t);
size_t mock_cache_line();
