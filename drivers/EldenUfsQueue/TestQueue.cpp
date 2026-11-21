// SPDX-License-Identifier: BSD-2-Clause-Patent
#include "QueueCore.h"
#include "DmaPlan.h"
#include "upstream/RootTransportLayout.h"
#include "ReferencePrdt.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <thread>
#include <vector>

static void grant(EldenUfsPool &p,EldenUfsLease &l){assert(elden_ufs_pool_take(&p,&l)==EldenUfsGranted);}
static void issue(EldenUfsPool &p,const EldenUfsLease &l){assert(elden_ufs_pool_issue(&p,&l)==EldenUfsGranted);}
static void done(EldenUfsPool &p,const EldenUfsLease &l,uint32_t db=0){assert(elden_ufs_pool_complete(&p,&l,db,0,0)==EldenUfsGranted);}
static void release(EldenUfsPool &p,const EldenUfsLease &l){assert(elden_ufs_pool_release(&p,&l)==EldenUfsGranted);}
static uint64_t rng=0x43f899432712;
static uint32_t random32(){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return static_cast<uint32_t>(rng);}
struct Pages{uint64_t address[256];unsigned calls=0;};
static uint64_t page(void *opaque,uint64_t offset){auto &p=*static_cast<Pages*>(opaque);assert(!(offset&4095)&&offset/4096<256);p.calls++;return p.address[offset/4096];}
static Pages *refPages;
alignas(4096) static uint8_t virtualBuffer[1<<20];
static uintptr_t virtualBase=reinterpret_cast<uintptr_t>(virtualBuffer);
static uint64_t referenceMap(const void *p){return page(refPages,reinterpret_cast<uintptr_t>(p)-virtualBase);}
int main(){unsigned cases=0;
    for(unsigned n=1;n<=32;++n)for(unsigned stride:{1u,2u}){
        EldenUfsPool p={};auto init=elden_ufs_pool_init(&p,n,32,stride);
        if((n-1)*stride>=32){assert(init==EldenUfsInvalid&&!p.initialized);cases++;continue;}
        assert(init==EldenUfsGranted);EldenUfsLease l[32]={};
        for(unsigned i=0;i<n;++i){grant(p,l[i]);assert(l[i].slot==i&&l[i].entry==i*stride);issue(p,l[i]);}
        assert(p.busy==n&&p.peak==n&&!p.freeMask);EldenUfsLease untouched={};assert(elden_ufs_pool_take(&p,&untouched)==EldenUfsQueued&&!untouched.pool);
        assert(elden_ufs_pool_init(&p,n,32,stride)==EldenUfsInvalid);
        uint32_t db=p.issuedMask;
        for(unsigned i=n;i-- >0;){assert(elden_ufs_pool_release(&p,&l[i])==EldenUfsDmaOwned);
            assert(elden_ufs_pool_complete(&p,&l[i],db,0,0)==EldenUfsNotComplete);
            db&=~(1u<<l[i].entry);assert(elden_ufs_pool_complete(&p,&l[i],db,15,0)==EldenUfsNotComplete);
            done(p,l[i],db);release(p,l[i]);assert(elden_ufs_pool_release(&p,&l[i])==EldenUfsStale);}
        assert(!p.busy&&!p.issuedMask);cases++;
    }
    {EldenUfsPool p={};assert(elden_ufs_pool_init(&p,1,32,1)==0);EldenUfsLease old;grant(p,old);
     EldenUfsWaiter w[4]={};for(auto &v:w)assert(elden_ufs_pool_enqueue(&p,&v)==EldenUfsQueued);
     assert(elden_ufs_pool_enqueue(&p,&w[1])==EldenUfsInvalid&&p.queued==4);
     assert(elden_ufs_pool_cancel(&p,&w[1])==EldenUfsStopped&&p.queued==3);
     release(p,old);assert(w[0].state==2&&p.queued==2&&p.busy==1);
     assert(elden_ufs_pool_cancel(&p,&w[0])==EldenUfsGranted);
     assert(elden_ufs_pool_release(&p,&old)==EldenUfsStale);
     release(p,w[0].lease);assert(w[2].state==2&&w[3].state==1);
     assert(elden_ufs_pool_cancel(&p,&w[0])==EldenUfsStale);
     release(p,w[2].lease);release(p,w[3].lease);assert(!p.head&&!p.tail&&!p.busy&&!p.queued);cases++;}
    for(unsigned cancelled=0;cancelled<3;cancelled++){
        EldenUfsPool p={};elden_ufs_pool_init(&p,1,32,1);EldenUfsLease l;grant(p,l);
        EldenUfsWaiter w[3]={};for(auto &v:w)elden_ufs_pool_enqueue(&p,&v);
        assert(elden_ufs_pool_cancel(&p,&w[cancelled])==EldenUfsStopped);
        release(p,l);for(unsigned i=0;i<3;i++)if(i!=cancelled){assert(w[i].state==2);release(p,w[i].lease);}
        assert(!p.head&&!p.tail&&!p.queued);cases++;
    }
    for(bool uncertain:{false,true}){
        EldenUfsPool p={};elden_ufs_pool_init(&p,2,32,1);EldenUfsLease a,b;grant(p,a);grant(p,b);issue(p,a);
        EldenUfsWaiter w={};elden_ufs_pool_enqueue(&p,&w);elden_ufs_pool_stop(&p,uncertain);
        assert(w.state==3&&!w.owner&&!p.queued&&p.closed);
        assert(elden_ufs_pool_issue(&p,&b)==EldenUfsStopped);release(p,b);
        if(uncertain){assert(elden_ufs_pool_complete(&p,&a,0,0,0)==EldenUfsStopped);assert(elden_ufs_pool_release(&p,&a)==EldenUfsDmaOwned);}
        else {done(p,a);release(p,a);assert(!p.busy);}
        assert(elden_ufs_pool_take(&p,&b)==EldenUfsStopped);cases++;
    }
    {EldenUfsPool p={};elden_ufs_pool_init(&p,32,32,1);EldenUfsLease l[32];for(auto &v:l){grant(p,v);issue(p,v);}
     assert(elden_ufs_pool_complete(&p,&l[4],0,0,0x800)==EldenUfsStopped&&p.failed);
     for(auto &v:l)assert(elden_ufs_pool_release(&p,&v)==EldenUfsDmaOwned);cases++;}
    {EldenUfsPool a={},b={};elden_ufs_pool_init(&a,1,32,1);elden_ufs_pool_init(&b,1,32,1);EldenUfsLease x,y;grant(a,x);grant(b,y);
     assert(elden_ufs_pool_release(&a,&y)==EldenUfsStale);release(a,x);a.generation=UINT64_MAX;
     assert(elden_ufs_pool_take(&a,&x)==EldenUfsStopped&&a.failed);cases++;}
    // Actual core under its specified external mutex, with concurrent callers.
    {EldenUfsPool p={};elden_ufs_pool_init(&p,32,32,1);std::mutex lock;std::vector<std::thread> threads;
     for(unsigned i=0;i<16;i++)threads.emplace_back([&]{for(unsigned k=0;k<200;k++){
        EldenUfsLease l;{std::lock_guard<std::mutex> hold(lock);grant(p,l);issue(p,l);}
        std::this_thread::yield();{std::lock_guard<std::mutex> hold(lock);done(p,l,p.issuedMask&~(1u<<l.entry));release(p,l);}}});
     for(auto &t:threads)t.join();assert(!p.busy&&!p.issuedMask&&p.freeMask==0xffffffffu);cases++;}
    // Layout is the exact upstream region geometry, not a duplicate model.
    for(unsigned i=0;i<16;i++){
        assert(ufsSlotUtrdOffset(i)%64==0&&ufsSlotUtrdOffset(i)+32<=kUcdOffset);
        assert(ufsSlotUcdOffset(i)%64==0&&ufsSlotDataOffset(i)%4096==0);
        assert(ufsSlotDataOffset(i)+kDataMax<=kDmaBytes);
        for(unsigned j=0;j<i;j++)assert(ufsSlotDataOffset(j)+kDataMax<=ufsSlotDataOffset(i));
    }cases++;
    for(unsigned ia=0;ia<16;ia++)for(unsigned oa=0;oa<16;oa++)for(unsigned ub=0;ub<16;ub++){
        auto result=elden_ufs_dma_limit(ia|(oa<<4)|(ub<<8),true,true);
        if(ia>5||oa>5||ub>5)assert(!result);else assert(result>=1ULL<<32&&result<=1ULL<<48);
        assert(!elden_ufs_dma_limit(ia|(oa<<4)|(ub<<8),true,false));
        if(result)assert(elden_ufs_dma_limit(ia|(oa<<4)|(ub<<8),false,true)==1ULL<<32);
    }cases+=4096;
    Pages pages={};EldenUfsPrdtPlan plan={},sentinel;memset(&sentinel,0x5a,sizeof(sentinel));
    for(unsigned round=0;round<4096;round++){
        unsigned count=1+random32()%256;uint64_t address=0x100000000ULL;
        for(unsigned i=0;i<count;i++){pages.address[i]=address;address+=4096*(1+(random32()%3==0?1:0));}
        if(round%7==0)pages.address[random32()%count]=0;
        if(round%11==0)pages.address[random32()%count]|=1;
        refPages=&pages;reference::map=referenceMap;reference::UfsPrd referencePlan[64]={};
        unsigned wanted=reference::hostBuildPrds(virtualBuffer,count*4096ULL,referencePlan);
        plan=sentinel;bool ok=elden_ufs_prdt_build(virtualBase,count*4096ULL,1<<20,1ULL<<48,page,&pages,&plan);
        assert(ok==(wanted!=0));
        if(ok){assert(plan.count==wanted&&plan.bytes==count*4096);for(unsigned i=0;i<wanted;i++)assert(plan.entries[i].address==referencePlan[i].addr&&plan.entries[i].bytes==referencePlan[i].bytes&&!plan.entries[i].reserved);}
        else assert(!memcmp(&plan,&sentinel,sizeof(plan)));cases++;
    }
    for(unsigned i=0;i<256;i++)pages.address[i]=0x100000000ULL+i*4096ULL;
    assert(elden_ufs_prdt_build(virtualBase,1<<20,1<<20,1ULL<<48,page,&pages,&plan)&&plan.count==4);cases++;
    for(unsigned kind=0;kind<9;kind++){
        plan=sentinel;uintptr_t va=kind==0?virtualBase+1:kind==1?UINTPTR_MAX-4095:virtualBase;
        uint64_t bytes=kind==2?0:kind==3?4097:kind==4?(1<<20)+4096:8192;
        uint64_t cap=kind==5?4096:1<<22,limit=kind==6?0:kind==7?1ULL<<32:1ULL<<48;
        assert(!elden_ufs_prdt_build(va,bytes,cap,limit,kind==8?nullptr:page,&pages,&plan));
        assert(!memcmp(&plan,&sentinel,sizeof(plan)));cases++;
    }
    printf("PASS %u queue/PRDT cases; 3200 concurrent leases; 4096 differential PRDT plans\n",cases);
}
