// SPDX-License-Identifier: BSD-2-Clause-Patent
#include "QueueCore.h"

static bool live(const EldenUfsPool *p){return p&&p->initialized==0x55465351u;}
static bool leaseMatches(const EldenUfsPool *p,const EldenUfsLease *l){
    return live(p)&&l&&l->pool==p&&l->generation&&l->slot<p->count&&
        p->slots[l->slot].generation==l->generation&&p->slots[l->slot].entry==l->entry;
}
extern "C" void elden_ufs_pool_stop(EldenUfsPool *p,bool uncertain){
    if(!live(p))return;
    p->closed=true;p->failed=p->failed||uncertain;
    if(p->failed)for(unsigned i=0;i<p->count;++i)
        if(p->slots[i].state==EldenUfsIssued)p->slots[i].state=EldenUfsQuarantined;
    while(p->head){
        EldenUfsWaiter *w=p->head;p->head=w->next;
        w->next=nullptr;w->owner=nullptr;w->state=3;w->result=EldenUfsStopped;
    }
    p->tail=nullptr;p->queued=0;
}
extern "C" EldenUfsPoolResult elden_ufs_pool_init(EldenUfsPool *p,uint32_t count,uint32_t entries,uint32_t stride){
    if(!p||p->initialized||!count||count>32||!entries||entries>32||(stride!=1&&stride!=2)||
       (count-1)*stride>=entries)return EldenUfsInvalid;
    p->count=count;p->freeMask=count==32?0xffffffffu:(1u<<count)-1;
    p->issuedMask=p->busy=p->peak=p->queued=0;p->closed=p->failed=false;p->generation=0;p->head=p->tail=nullptr;
    for(unsigned i=0;i<32;++i)p->slots[i]={0,i*stride,EldenUfsFree};
    p->initialized=0x55465351u;return EldenUfsGranted;
}
static EldenUfsPoolResult reserve(EldenUfsPool *p,EldenUfsLease *out){
    if(!live(p)||!out)return EldenUfsInvalid;
    if(p->closed)return EldenUfsStopped;
    if(!p->freeMask)return EldenUfsQueued;
    if(p->generation==UINT64_MAX){elden_ufs_pool_stop(p,true);return EldenUfsStopped;}
    const unsigned index=static_cast<unsigned>(__builtin_ctz(p->freeMask));
    p->freeMask&=~(1u<<index);auto &s=p->slots[index];
    s.generation=++p->generation;s.state=EldenUfsLeased;
    if(++p->busy>p->peak)p->peak=p->busy;
    *out={p,s.generation,index,s.entry};return EldenUfsGranted;
}
extern "C" EldenUfsPoolResult elden_ufs_pool_take(EldenUfsPool *p,EldenUfsLease *out){
    if(!live(p)||!out)return EldenUfsInvalid;
    if(p->closed)return EldenUfsStopped;
    if(p->head)return EldenUfsQueued; // do not bypass queued callers
    return reserve(p,out);
}
extern "C" EldenUfsPoolResult elden_ufs_pool_enqueue(EldenUfsPool *p,EldenUfsWaiter *w){
    if(!live(p)||!w||w->state||w->owner||w->next)return EldenUfsInvalid;
    EldenUfsPoolResult result=elden_ufs_pool_take(p,&w->lease);
    w->result=result;
    if(result!=EldenUfsQueued){w->state=result==EldenUfsGranted?2u:3u;return result;}
    w->owner=p;w->state=1;
    if(p->tail)p->tail->next=w;else p->head=w;
    p->tail=w;++p->queued;return result;
}
extern "C" EldenUfsPoolResult elden_ufs_pool_cancel(EldenUfsPool *p,EldenUfsWaiter *w){
    if(!live(p)||!w)return EldenUfsInvalid;
    if(w->state==2)return leaseMatches(p,&w->lease)&&p->slots[w->lease.slot].state==EldenUfsLeased?EldenUfsGranted:EldenUfsStale;
    if(w->state!=1||w->owner!=p)return EldenUfsInvalid;
    EldenUfsWaiter *previous=nullptr,*at=p->head;
    while(at&&at!=w){previous=at;at=at->next;}
    if(!at)return EldenUfsInvalid;
    if(previous)previous->next=w->next;else p->head=w->next;
    if(p->tail==w)p->tail=previous;
    --p->queued;w->next=nullptr;w->owner=nullptr;w->state=3;w->result=EldenUfsStopped;
    return EldenUfsStopped;
}
extern "C" EldenUfsPoolResult elden_ufs_pool_issue(EldenUfsPool *p,const EldenUfsLease *l){
    if(!leaseMatches(p,l))return EldenUfsStale;
    if(p->closed)return EldenUfsStopped;
    auto &s=p->slots[l->slot];if(s.state!=EldenUfsLeased)return EldenUfsInvalid;
    s.state=EldenUfsIssued;p->issuedMask|=1u<<s.entry;return EldenUfsGranted;
}
extern "C" EldenUfsPoolResult elden_ufs_pool_complete(EldenUfsPool *p,const EldenUfsLease *l,uint32_t db,uint32_t ocs,uint32_t status){
    if(!leaseMatches(p,l))return EldenUfsStale;
    if(status&0x71880u){elden_ufs_pool_stop(p,true);return EldenUfsStopped;}
    auto &s=p->slots[l->slot];if(p->failed||s.state==EldenUfsQuarantined)return EldenUfsStopped;
    if(s.state!=EldenUfsIssued)return EldenUfsInvalid;
    if((db&(1u<<s.entry))||ocs==15)return EldenUfsNotComplete;
    if(ocs>255)return EldenUfsInvalid;
    s.state=EldenUfsDone;p->issuedMask&=~(1u<<s.entry);return EldenUfsGranted;
}
extern "C" EldenUfsPoolResult elden_ufs_pool_release(EldenUfsPool *p,const EldenUfsLease *l){
    if(!leaseMatches(p,l))return EldenUfsStale;
    auto &s=p->slots[l->slot];
    if(s.state==EldenUfsIssued||s.state==EldenUfsQuarantined)return EldenUfsDmaOwned;
    if(s.state!=EldenUfsLeased&&s.state!=EldenUfsDone)return EldenUfsStale;
    s.state=EldenUfsFree;p->freeMask|=1u<<l->slot;--p->busy;
    if(p->closed||!p->head)return EldenUfsGranted;
    EldenUfsWaiter *w=p->head;p->head=w->next;if(!p->head)p->tail=nullptr;
    --p->queued;w->next=nullptr;w->owner=nullptr;
    w->result=reserve(p,&w->lease);w->state=w->result==EldenUfsGranted?2u:3u;
    return EldenUfsGranted;
}
