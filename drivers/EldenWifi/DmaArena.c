/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Split/coalesce and size alignment adapted from UniXNU-sheng WifiProbe.cpp,
 * e8937177309d88c93b305a57bad147fd5fac8a86. See DMA-ARENA.md for provenance.
 */
#include "DmaArena.h"
#include <string.h>

static int owner(const EldenWifiDmaArena *a,const void *token,uint64_t epoch) {
    if(!a||!token||!epoch)return -22;
    if(a->state==EldenWifiArenaEmpty||a->owner!=token||a->epoch!=epoch)return -19;
    return 0;
}
static int running(const EldenWifiDmaArena *a,const void *token,uint64_t epoch) {
    int rc=owner(a,token,epoch);return rc?rc:a->state==EldenWifiArenaRunning?0:-108;
}
static int overlaps(uintptr_t a,size_t an,uintptr_t b,size_t bn) {
    return a<b+bn&&b<a+an;
}
int elden_wifi_dma_arena_init(EldenWifiDmaArena *a,const void *token,uint64_t epoch,
    void *cpu,uint64_t iova,uint32_t bytes,EldenWifiDmaBlock *blocks,uint32_t capacity) {
    if(!a||!token||!epoch||!cpu||!blocks||!capacity||capacity>EldenWifiArenaMaxBlocks||
       bytes<8192||bytes>EldenWifiArenaMaxBytes||(bytes&(bytes-1))||!iova||(iova&(bytes-1))||
       iova>UINT32_MAX-(uint64_t)bytes+1||((uintptr_t)cpu&4095)||
       ((uintptr_t)blocks%_Alignof(EldenWifiDmaBlock)))return -22;
    if(a->state!=EldenWifiArenaEmpty)return -16;
    size_t table_bytes=(size_t)capacity*sizeof(*blocks);
    if((uintptr_t)cpu>UINTPTR_MAX-bytes||(uintptr_t)blocks>UINTPTR_MAX-table_bytes||
       (uintptr_t)a>UINTPTR_MAX-sizeof(*a))return -22;
    if(overlaps((uintptr_t)cpu,bytes,(uintptr_t)blocks,table_bytes)||
       overlaps((uintptr_t)a,sizeof(*a),(uintptr_t)cpu,bytes)||
       overlaps((uintptr_t)a,sizeof(*a),(uintptr_t)blocks,table_bytes))return -22;
    /* The first 4 KiB is permanently reserved for the MSI sink. Only the
     * already-qualified NC alias is touched; no cached alias is accepted here. */
    memset(cpu,0,bytes);
    blocks[0]=(EldenWifiDmaBlock){4096,bytes-4096,0,0};
    *a=(EldenWifiDmaArena){.owner=token,.epoch=epoch,.iova=iova,.cpu=cpu,.blocks=blocks,
        .state=EldenWifiArenaRunning,.bytes=bytes,.capacity=capacity,.count=1,.used=4096,.peak=4096};
    return 0;
}
int elden_wifi_dma_arena_alloc(EldenWifiDmaArena *a,const void *token,uint64_t epoch,
    size_t request,void **cpu,uint64_t *bus) {
    if(cpu)*cpu=0;
    if(bus)*bus=0;
    if(!cpu||!bus)return -22;
    int rc=running(a,token,epoch);if(rc)return rc;
    if(!request||request>a->bytes-4096u)return -22;
    /* Bound before rounding: the size_t additions and uint32_t alignment loop
     * cannot overflow. Offset alignment also aligns the power-of-two IOVA. */
    uint32_t n=((uint32_t)request+63u)&~63u;
    if(n>=4096)n=(n+4095u)&~4095u;
    uint32_t align=64;
    if(n>=4096){align=4096;while(align<n)align<<=1;}
    for(uint32_t i=0;i<a->count;i++) {
        EldenWifiDmaBlock b=a->blocks[i];
        if(b.used)continue;
        uint32_t start=(b.offset+align-1)&~(align-1),pad=start-b.offset;
        if(pad>b.bytes||n>b.bytes-pad)continue;
        uint32_t tail=b.bytes-pad-n,extra=(pad?1u:0u)+(tail?1u:0u);
        if(extra>a->capacity-a->count)continue;
        memmove(&a->blocks[i+extra],&a->blocks[i],(a->count-i)*sizeof(*a->blocks));
        a->count+=extra;uint32_t at=i;
        if(pad)a->blocks[at++]=(EldenWifiDmaBlock){b.offset,pad,0,0};
        a->blocks[at]=(EldenWifiDmaBlock){start,n,(uint32_t)request,1};
        if(tail)a->blocks[at+1]=(EldenWifiDmaBlock){start+n,tail,0,0};
        a->used+=n;if(a->used>a->peak)a->peak=a->used;a->live++;
        memset(a->cpu+start,0,n);*cpu=a->cpu+start;*bus=a->iova+start;return 0;
    }
    a->allocation_failures++;return -12;
}
static const EldenWifiDmaBlock *range(const EldenWifiDmaArena *a,uint64_t offset,size_t bytes) {
    if(offset<4096||offset>=a->bytes||!bytes||bytes>a->bytes-offset)return 0;
    for(uint32_t i=0;i<a->count;i++) {
        const EldenWifiDmaBlock *b=&a->blocks[i];
        if(b->used&&offset>=b->offset&&offset-b->offset<b->requested&&
           bytes<=b->requested-(offset-b->offset))return b;
    }
    return 0;
}
int elden_wifi_dma_arena_free(EldenWifiDmaArena *a,const void *token,uint64_t epoch,
    size_t bytes,void *cpu,uint64_t bus) {
    int rc=owner(a,token,epoch);if(rc)return rc;
    uintptr_t p=(uintptr_t)cpu,base=(uintptr_t)a->cpu;
    if(p<base||p-base>=a->bytes)return -22;
    uint32_t offset=(uint32_t)(p-base);
    for(uint32_t i=0;i<a->count;i++) {
        EldenWifiDmaBlock *b=&a->blocks[i];
        if(!b->used||b->offset!=offset)continue;
        if((bytes&&bytes!=b->requested)||(bus&&bus!=a->iova+offset))return -22;
        a->used-=b->bytes;a->live--;b->used=0;b->requested=0;
        if(i+1<a->count&&!a->blocks[i+1].used) {
            b->bytes+=a->blocks[i+1].bytes;
            memmove(&a->blocks[i+1],&a->blocks[i+2],(a->count-i-2)*sizeof(*b));a->count--;
        }
        if(i&&!a->blocks[i-1].used) {
            a->blocks[i-1].bytes+=b->bytes;
            memmove(&a->blocks[i],&a->blocks[i+1],(a->count-i-1)*sizeof(*b));a->count--;
        }
        return 0;
    }
    return -22;
}
int elden_wifi_dma_arena_map(const EldenWifiDmaArena *a,const void *token,uint64_t epoch,
    const void *cpu,size_t bytes,int direction,uint64_t *bus) {
    if(!bus)return -22;*bus=0;
    int rc=running(a,token,epoch);if(rc)return rc;
    uintptr_t p=(uintptr_t)cpu,base=(uintptr_t)a->cpu;
    if(direction<0||direction>2||p<base||!range(a,p-base,bytes))return -22;
    *bus=a->iova+(p-base);return 0;
}
int elden_wifi_dma_arena_bus_range(const EldenWifiDmaArena *a,const void *token,uint64_t epoch,
    uint64_t bus,size_t bytes,int direction) {
    int rc=owner(a,token,epoch);if(rc)return rc;
    if(direction<0||direction>2||bus<a->iova||!range(a,bus-a->iova,bytes))return -22;
    return 0;
}
int elden_wifi_dma_arena_stop(EldenWifiDmaArena *a,const void *token,uint64_t epoch) {
    int rc=owner(a,token,epoch);if(rc)return rc;
    a->state=EldenWifiArenaStopping;return 0;
}
