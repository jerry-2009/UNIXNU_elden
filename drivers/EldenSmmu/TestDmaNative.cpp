/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "DmaNative.h"
#include "DmaTables.h"
#include "DmaArena.h"
#include <atomic>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <thread>
#include <vector>
static unsigned checks,cases,alloc_calls,fail_alloc,barriers,power_calls,drop_power_at;
static std::atomic<bool> smmu_ready{true},power_ready{true};
static thread_local bool in_irq;
static int owner_token,other_token;
static bool cleanup_allowed;
static thread_local int thread_token;
static void *cleanup_thread;
static uint64_t cleanup_clock,cleanup_deadline;
extern "C" int elden_pcie_dma_cleanup_admit(const void *p,uint64_t epoch){
    return cleanup_allowed&&p==&owner_token&&epoch==7&&cleanup_thread==&thread_token&&cleanup_clock<cleanup_deadline?0:-19;
}
static std::vector<void *> allocations;
using IOLock=std::mutex;
static std::vector<IOLock *> locks;
#define CHECK(x) do{++checks;assert(x);}while(0)
static bool fail(){return ++alloc_calls==fail_alloc;}
static void *IOMalloc(size_t n){if(fail())return nullptr;void *p=malloc(n);if(p)allocations.push_back(p);return p;}
static void IOFree(void *,size_t){assert(false&&"native lifetime must retain resources to reset");}
static IOLock *IOLockAlloc(){if(fail())return nullptr;auto *p=new IOLock;locks.push_back(p);return p;}
static void IOLockLock(IOLock *p){p->lock();}
static void IOLockUnlock(IOLock *p){p->unlock();}
static bool IOLockTryLock(IOLock *p){return p->try_lock();}
static bool ml_at_interrupt_context(){return in_irq;}
static int elden_wifi_smmu_ready(){return smmu_ready.load();}
static int elden_wlan_power_ready(const void *owner,uint64_t epoch){
    ++power_calls;if(drop_power_at&&power_calls==drop_power_at)power_ready=false;
    return owner==&owner_token&&epoch==7&&power_ready?0:-19;
}
struct Memory {uint8_t *cpu;uint8_t *data(){return cpu;}};
struct Context {Memory *memory;};
static Context *active;
static void host_order(){++barriers;}
#include "DmaNativeHost.inc"

static void reset(){
    for(auto p:locks)delete p;locks.clear();
    for(auto p:allocations)free(p);allocations.clear();
    dma_owner=nullptr;dma_run=dma_stopping=dma_calls=dma_closed=0;dma_first_error=0;
    cleanup_allowed=false;cleanup_thread=&thread_token;cleanup_clock=1;cleanup_deadline=5000001;
    alloc_calls=fail_alloc=barriers=power_calls=drop_power_at=0;in_irq=false;smmu_ready=true;power_ready=true;
    ++cases;
}
static EldenWifiDmaStatus status(){EldenWifiDmaStatus s={};CHECK(elden_wifi_dma_status(&s)==0);return s;}
static void bind(){CHECK(elden_wifi_dma_bind(&owner_token,7)==0);CHECK(status().run==2);}
int main(){
    Memory memory={static_cast<uint8_t *>(aligned_alloc(4096,EldenWifiDmaBytes))};assert(memory.cpu);
    Context context={&memory};active=&context;uint64_t bus=0;void *p=nullptr;
    reset();CHECK(elden_wifi_dma_bind(nullptr,7)==-22);CHECK(elden_wifi_dma_bind(&owner_token,0)==-22);
    CHECK(status().version==1&&status().live==0);
    CHECK(elden_wifi_dma_bind(&other_token,7)==-19);CHECK(status().run==0);
    smmu_ready=false;CHECK(elden_wifi_dma_bind(&owner_token,7)==-19);smmu_ready=true;
    in_irq=true;CHECK(elden_wifi_dma_bind(&owner_token,7)==-22);in_irq=false;bind();
    CHECK(elden_wifi_dma_bind(&owner_token,7)==-16);
    for(unsigned fail_at=1;fail_at<=3;fail_at++){
        reset();fail_alloc=fail_at;CHECK(elden_wifi_dma_bind(&owner_token,7)==-12);
        auto s=status();CHECK(s.run==3&&s.stopping==1&&s.first_error==-12);
        CHECK(elden_wifi_dma_alloc(4096,&bus)==nullptr&&bus==0);
    }
    reset();elden_wifi_dma_stop_begin();CHECK(elden_wifi_dma_bind(&owner_token,7)==-19);
    reset();drop_power_at=2;CHECK(elden_wifi_dma_bind(&owner_token,7)==-108);CHECK(status().run==3);
    reset();bind();CHECK(elden_wifi_dma_msi_sink(&bus)==0&&bus==EldenWifiDmaIova);
    p=elden_wifi_dma_alloc(4096,&bus);CHECK(p&&bus==EldenWifiDmaIova+4096&&barriers==1);
    CHECK(elden_wifi_dma_map((uint8_t *)p+8,4088,1)==bus+8);CHECK(barriers==2);
    elden_wifi_dma_sync(bus,4096,2);CHECK(barriers==3);CHECK(status().live==1&&status().calls==0);
    elden_wifi_dma_stop_begin();CHECK(elden_wifi_dma_map(p,1,1)==0);
    uint64_t no=123;CHECK(!elden_wifi_dma_alloc(1,&no)&&no==0);
    elden_wifi_dma_sync(bus,4096,2);CHECK(barriers==4);
    elden_wifi_dma_free(0,p,0);CHECK(status().live==0&&status().stopping==1&&status().first_error==0);
    CHECK(allocations.size()==2&&locks.size()==1); // still retained, not DMA-drain proof
    reset();bind();p=elden_wifi_dma_alloc(65,&bus);CHECK(p);
    CHECK(elden_wifi_dma_map((uint8_t *)p+64,2,1)==0);
    CHECK(status().stopping==1&&status().first_error==-22);elden_wifi_dma_free(0,p,0);CHECK(status().live==0);
    reset();bind();p=elden_wifi_dma_alloc(64,&bus);CHECK(p);
    elden_wifi_dma_free(63,p,bus);CHECK(status().live==1&&status().first_error==-22);
    elden_wifi_dma_free(0,p,0);CHECK(status().live==0);
    reset();bind();p=elden_wifi_dma_alloc(64,&bus);CHECK(p);smmu_ready=false;
    CHECK(elden_wifi_dma_map(p,1,1)==0);elden_wifi_dma_free(0,p,0);CHECK(status().live==0&&status().stopping==1);
    reset();bind();drop_power_at=power_calls+2;p=elden_wifi_dma_alloc(64,&bus);
    CHECK(!p&&bus==0&&status().live==0&&status().stopping==1); // withdrawal while zeroing
    reset();bind();in_irq=true;CHECK(!elden_wifi_dma_alloc(4,&bus));in_irq=false;
    CHECK(status().first_error==-22&&status().stopping==1&&status().calls==0);
    reset();bind();
    std::atomic<bool> held{false},release{false};
    std::thread blocker([&]{IOLockLock(dma_owner->lock);held=true;while(!release.load())std::this_thread::yield();IOLockUnlock(dma_owner->lock);});
    while(!held.load())std::this_thread::yield();
    std::thread waiter([&]{p=elden_wifi_dma_alloc(4096,&bus);});
    while(!__atomic_load_n(&dma_calls,__ATOMIC_ACQUIRE))std::this_thread::yield();
    EldenWifiDmaStatus pending={};CHECK(elden_wifi_dma_status(&pending)==-11);
    elden_wifi_dma_stop_begin();CHECK(__atomic_load_n(&dma_stopping,__ATOMIC_ACQUIRE)==1);
    release=true;blocker.join();waiter.join();CHECK(!p&&bus==0&&status().calls==0&&status().live==0);
    reset();bind();elden_wifi_dma_close_admission();power_ready=false;
    CHECK(!elden_wifi_dma_alloc(64,&bus)&&!bus);
    CHECK(elden_wifi_dma_cleanup_begin(&owner_token,7)==-19);
    cleanup_allowed=true;
    CHECK(elden_wifi_dma_cleanup_begin(&other_token,7)==-19);
    CHECK(elden_wifi_dma_cleanup_begin(&owner_token,8)==-19);
    CHECK(!elden_wifi_dma_cleanup_begin(&owner_token,7));
    CHECK(elden_wifi_dma_cleanup_begin(&owner_token,7)==-16); // no renewal
    p=elden_wifi_dma_alloc(64,&bus);CHECK(p&&bus);CHECK(elden_wifi_dma_map(p,64,1)==bus);
    bool other_rejected=false;
    std::thread other([&]{uint64_t b=1;other_rejected=!elden_wifi_dma_alloc(64,&b)&&!b&&elden_wifi_dma_map(p,64,1)==0;});
    other.join();CHECK(other_rejected);CHECK(elden_wifi_dma_map(p,64,1)==bus);
    cleanup_clock=cleanup_deadline;CHECK(!elden_wifi_dma_map(p,64,1));
    elden_wifi_dma_free(0,p,0);CHECK(status().live==0);
    reset();bind();cleanup_allowed=true;CHECK(!elden_wifi_dma_cleanup_begin(&owner_token,7));
    elden_wifi_dma_stop_begin();CHECK(!elden_wifi_dma_alloc(64,&bus));
    CHECK(elden_wifi_dma_cleanup_begin(&owner_token,7)==-16);
    reset();bind();cleanup_allowed=true;CHECK(!elden_wifi_dma_cleanup_begin(&owner_token,7));
    smmu_ready=false;CHECK(!elden_wifi_dma_alloc(64,&bus));CHECK(status().stopping);
    unsigned completed=cases;reset();free(memory.cpu);
    printf("%u actual native callback scenarios / %u checks passed; IOKit, power, SMMU and barriers modeled\n",completed,checks);
}
