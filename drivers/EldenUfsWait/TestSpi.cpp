// SPDX-License-Identifier: BSD-2-Clause-Patent
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <thread>
#include <vector>
using IOReturn=int;
enum { kIOReturnSuccess,kIOReturnNotReady,kIOReturnBadArgument,kIOReturnExclusiveAccess,
       kIOReturnNoResources,kIOReturnTimeout,kIOReturnNotFound,ARMCPU_SPI_SLOTS=16 };
using IOLock=std::mutex;
static bool allocFail,waitFail;
static std::atomic<unsigned> allocations{0},frees{0};
static IOLock *IOLockAlloc(){if(allocFail)return nullptr;allocations++;return new IOLock;}
static void IOLockFree(IOLock*p){frees++;delete p;}
static void IOLockLock(IOLock*p){p->lock();}
static void IOLockUnlock(IOLock*p){p->unlock();}
alignas(64) static uint8_t gic[65536];
static uintptr_t gDist;
static unsigned armcpu_gic_ready;
static uint64_t gBootAffinity;
struct ArmCpuSpi{uint32_t id;void(*handler)(void*);void*context;uint64_t count;};
static ArmCpuSpi gSpi[ARMCPU_SPI_SLOTS];
static volatile uint32_t gSpiUsed;
static uint32_t read32(uintptr_t p,unsigned off){return *reinterpret_cast<uint32_t*>(p+off);}
static void write32(uintptr_t p,unsigned off,uint32_t value){
    if(off>=0x100&&off<0x180){*reinterpret_cast<uint32_t*>(p+off)|=value;return;}
    if(off>=0x180&&off<0x200){*reinterpret_cast<uint32_t*>(p+off-0x80)&=~value;return;}
    *reinterpret_cast<uint32_t*>(p+off)=value;
}
static bool waitClear(uintptr_t,unsigned,uint32_t){return !waitFail;}
#include "spi.inc"
static void handler(void*){}
static void reset(){
    // Only after all test threads joined, unlike the platform-lifetime driver.
    if(gEldenSpiRegistrationLock)IOLockFree(gEldenSpiRegistrationLock);
    gEldenSpiRegistrationLock=nullptr;memset(gic,0,sizeof(gic));memset(gSpi,0,sizeof(gSpi));
    gDist=reinterpret_cast<uintptr_t>(gic);armcpu_gic_ready=1;gBootAffinity=0;gSpiUsed=0;
    *reinterpret_cast<uint32_t*>(gic+4)=31;allocFail=waitFail=false;
}
int main(){unsigned cases=0;reset();uint32_t rb=0;uint64_t route=~0ull;
    assert(armcpu_spi_attach(297,false,handler,nullptr,&rb,&route)==0&&rb==0xa003&&route==0&&gSpiUsed==1);cases++;
    assert(armcpu_spi_mask(297,true)==0&&!(read32(gDist,0x124)&512));
    assert(armcpu_spi_mask(297,false)==0&&(read32(gDist,0x124)&512));cases++;
    assert(armcpu_spi_attach(297,false,handler,nullptr,nullptr,nullptr)==kIOReturnExclusiveAccess&&gSpiUsed==1);cases++;
    assert(armcpu_spi_mask(298,true)==kIOReturnNotFound);cases++;
    for(unsigned id:{0u,31u,1020u,0xffffffffu}){assert(armcpu_spi_attach(id,false,handler,nullptr,nullptr,nullptr)==kIOReturnBadArgument);assert(armcpu_spi_mask(id,true)==kIOReturnNotReady);cases++;}
    reset();allocFail=true;assert(armcpu_spi_attach(297,false,handler,nullptr,nullptr,nullptr)==kIOReturnNoResources&&!gSpiUsed);cases++;
    reset();waitFail=true;assert(armcpu_spi_attach(297,false,handler,nullptr,nullptr,nullptr)==kIOReturnTimeout&&!gSpiUsed);cases++;
    reset();armcpu_gic_ready=0;assert(armcpu_spi_attach(297,false,handler,nullptr,nullptr,nullptr)==kIOReturnNotReady);cases++;
    reset();*reinterpret_cast<uint32_t*>(gic+4)=3;assert(armcpu_spi_attach(297,false,handler,nullptr,nullptr,nullptr)==kIOReturnBadArgument);cases++;
    for(bool duplicate:{false,true}){
        reset();std::vector<std::thread> threads;std::atomic<unsigned> successes{0},ready{0};std::atomic<bool> go{false};
        for(unsigned i=0;i<16;i++)threads.emplace_back([&,i]{ready++;while(!go.load())std::this_thread::yield();
            auto r=armcpu_spi_attach(duplicate?297:288+i,false,handler,nullptr,nullptr,nullptr);
            if(!r)successes++;else assert(duplicate&&r==kIOReturnExclusiveAccess);});
        while(ready!=16)std::this_thread::yield();go=true;for(auto&t:threads)t.join();
        assert(successes==(duplicate?1u:16u)&&gSpiUsed==successes);
        if(!duplicate){for(unsigned i=288;i<304;i++)assert(armcpu_spi_mask(i,true)==0);
            assert(armcpu_spi_attach(320,false,handler,nullptr,nullptr,nullptr)==kIOReturnNoResources);}
        cases++;
    }
    reset();assert(allocations==frees);printf("PASS %u actual SPI cases (two 16-thread races)\n",cases);
}
