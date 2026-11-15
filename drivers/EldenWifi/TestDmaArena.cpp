/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "DmaArena.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include "OldArena.inc"

static unsigned checks=0;
#define CHECK(x) do {++checks;assert(x);} while(0)
constexpr uint32_t Bytes=16u<<20;
static int token,foreign;
static uint8_t *buffer;
static EldenWifiDmaBlock blocks[EldenWifiArenaMaxBlocks];
static EldenWifiDmaArena arena;
static void setup(unsigned cap=EldenWifiArenaMaxBlocks) {
    arena={};CHECK(elden_wifi_dma_arena_init(&arena,&token,7,buffer,0x10000000,Bytes,blocks,cap)==0);
}
static void invariant() {
    CHECK(arena.count&&arena.count<=arena.capacity);
    uint64_t next=4096,used=4096;unsigned live=0;
    for(unsigned i=0;i<arena.count;i++) {
        const auto &b=blocks[i];CHECK(b.offset==next&&b.bytes);next+=b.bytes;
        if(b.used){CHECK(b.requested&&b.requested<=b.bytes);used+=b.bytes;live++;}
        else {CHECK(!b.requested);CHECK(!i||blocks[i-1].used);}
    }
    CHECK(next==Bytes&&used==arena.used&&live==arena.live&&arena.used<=arena.peak);
}
static int allocate(size_t n,void **p,uint64_t *bus) {
    return elden_wifi_dma_arena_alloc(&arena,&token,7,n,p,bus);
}
int main() {
    buffer=static_cast<uint8_t *>(aligned_alloc(4096,Bytes));assert(buffer);
    gArena.va=static_cast<uint8_t *>(aligned_alloc(4096,Bytes));assert(gArena.va);
    gArena.blocks=static_cast<Arena::Block *>(calloc(kArenaBlocks,sizeof(Arena::Block)));assert(gArena.blocks);
    setup();gArena.iova=0x10000000;gArena.bytes=Bytes;gArena.count=1;
    gArena.blocks[0]={4096,Bytes-4096,false};gArena.used=gArena.peak=4096;
    struct Held {void *now,*old;size_t n;uint64_t bus;} held[128]={};
    uint32_t random=17;unsigned compared=0;
    for(unsigned trial=0;trial<4000;trial++) {
        random=random*1664525u+1013904223u;unsigned slot=(random>>16)%128;
        if(held[slot].now) {
            CHECK(elden_wifi_dma_arena_free(&arena,&token,7,held[slot].n,held[slot].now,held[slot].bus)==0);
            arenaFree(held[slot].old);held[slot]={};
        } else {
            random=random*1664525u+1013904223u;size_t n=1+(random%65536);
            void *now=nullptr;uint64_t bus=0,oldbus=0;int rc=allocate(n,&now,&bus);
            void *old=arenaAlloc(n,&oldbus);CHECK((rc==0)==(old!=nullptr));
            if(!rc) {
                CHECK(bus==oldbus&&((uint8_t *)now-buffer)==((uint8_t *)old-gArena.va));
                static const uint8_t zero[65536]={};CHECK(memcmp(now,zero,n)==0);
                memset(now,0x5a,n);held[slot]={now,old,n,bus};
            }
        }
        CHECK(arena.count==gArena.count&&arena.used==gArena.used);
        for(unsigned i=0;i<arena.count;i++)CHECK(blocks[i].offset==gArena.blocks[i].off&&blocks[i].bytes==gArena.blocks[i].size&&bool(blocks[i].used)==gArena.blocks[i].used);
        invariant();compared++;
    }
    for(auto &b:held)if(b.now)CHECK(elden_wifi_dma_arena_free(&arena,&token,7,0,b.now,0)==0);
    invariant();CHECK(arena.count==1&&arena.live==0&&arena.used==4096);

    void *p=nullptr;uint64_t bus=0,mapped=0;
    CHECK(allocate(6u<<20,&p,&bus)==0&&bus% (8u<<20)==0);
    CHECK(elden_wifi_dma_arena_free(&arena,&token,7,6u<<20,p,bus)==0);
    CHECK(allocate(65,&p,&bus)==0);
    CHECK(elden_wifi_dma_arena_map(&arena,&token,7,(uint8_t *)p+1,64,2,&mapped)==0&&mapped==bus+1);
    CHECK(elden_wifi_dma_arena_bus_range(&arena,&token,7,bus+1,64,2)==0);
    /* The exact upstream mapper ignores n; demonstrate the gap it would accept. */
    CHECK(pDmaMap(gArena.va+Bytes-1,2,1)!=0);
    CHECK(elden_wifi_dma_arena_map(&arena,&token,7,buffer+Bytes-1,2,1,&mapped)==-22);
    CHECK(elden_wifi_dma_arena_map(&arena,&token,7,(uint8_t *)p+64,2,1,&mapped)==-22);
    CHECK(elden_wifi_dma_arena_map(&arena,&token,7,buffer,4,1,&mapped)==-22);
    CHECK(elden_wifi_dma_arena_map(&arena,&token,7,p,SIZE_MAX,1,&mapped)==-22);
    CHECK(elden_wifi_dma_arena_map(&arena,&token,7,p,0,1,&mapped)==-22);
    CHECK(elden_wifi_dma_arena_map(&arena,&token,7,p,1,3,&mapped)==-22);
    CHECK(elden_wifi_dma_arena_bus_range(&arena,&token,7,UINT64_MAX,2,1)==-22);
    CHECK(elden_wifi_dma_arena_map(&arena,&foreign,7,p,1,1,&mapped)==-19);
    CHECK(elden_wifi_dma_arena_map(&arena,&token,8,p,1,1,&mapped)==-19);
    unsigned used=arena.used,count=arena.count;
    CHECK(elden_wifi_dma_arena_free(&arena,&token,7,64,p,bus)==-22);
    CHECK(elden_wifi_dma_arena_free(&arena,&token,7,65,p,bus+1)==-22);
    CHECK(elden_wifi_dma_arena_free(&arena,&token,7,0,(uint8_t *)p+1,0)==-22);
    CHECK(arena.used==used&&arena.count==count&&arena.live==1);
    CHECK(elden_wifi_dma_arena_free(&arena,&token,7,0,p,0)==0);
    CHECK(elden_wifi_dma_arena_free(&arena,&token,7,0,p,0)==-22);
    CHECK(elden_wifi_dma_arena_map(&arena,&token,7,p,1,1,&mapped)==-22);
    CHECK(allocate(SIZE_MAX,&p,&bus)==-22&&p==nullptr&&bus==0);
    CHECK(allocate(0,&p,&bus)==-22);
    CHECK(allocate(Bytes,&p,&bus)==-22);
    setup(1);CHECK(allocate(64,&p,&bus)==-12);invariant();CHECK(arena.count==1&&arena.live==0);
    setup();CHECK(allocate(16,&p,&bus)==0);
    CHECK(elden_wifi_dma_arena_stop(&arena,&foreign,7)==-19);
    CHECK(elden_wifi_dma_arena_stop(&arena,&token,7)==0);
    CHECK(elden_wifi_dma_arena_stop(&arena,&token,7)==0);
    void *other=nullptr;uint64_t otherbus=0;
    CHECK(allocate(1,&other,&otherbus)==-108);
    CHECK(elden_wifi_dma_arena_map(&arena,&token,7,p,1,1,&mapped)==-108);
    CHECK(elden_wifi_dma_arena_bus_range(&arena,&token,7,bus,1,1)==0);
    CHECK(elden_wifi_dma_arena_free(&arena,&token,7,0,p,0)==0);invariant();
    CHECK(elden_wifi_dma_arena_init(&arena,&token,8,buffer,0x10000000,Bytes,blocks,EldenWifiArenaMaxBlocks)==-16);
    arena={};
    CHECK(elden_wifi_dma_arena_init(&arena,&token,7,buffer,0x10000001,Bytes,blocks,1)==-22);
    CHECK(elden_wifi_dma_arena_init(&arena,&token,7,buffer,1ull<<32,Bytes,blocks,1)==-22);
    CHECK(elden_wifi_dma_arena_init(&arena,&token,7,buffer,0x10000000,Bytes,(EldenWifiDmaBlock *)buffer,1)==-22);
    CHECK(arena.state==EldenWifiArenaEmpty);
    free(gArena.blocks);free(gArena.va);free(buffer);
    printf("%u upstream allocation/free comparisons; %u checks passed, boundary/metadata/epoch/stop failures rejected\n",compared,checks);
}
