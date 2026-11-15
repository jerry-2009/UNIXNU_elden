/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Included by the explicit SMMU DMA-provider variant. The early Context and
 * its checked memory remain alive until platform reset. No device DMA starts
 * here, and no callback releases the backing allocation or context tables.
 */
namespace {
struct DmaOwner {
    static void *operator new(size_t n) noexcept{return IOMalloc(n);}
    static void operator delete(void *p) noexcept{if(p)IOFree(p,sizeof(DmaOwner));}
    IOLock *lock=nullptr;
    EldenWifiDmaBlock *blocks=nullptr;
    EldenWifiDmaArena arena={};
};
static DmaOwner *dma_owner;
static unsigned dma_run,dma_stopping,dma_calls;
static int dma_first_error;
static void dma_error(int rc){
    int expected=0;if(rc)__atomic_compare_exchange_n(&dma_first_error,&expected,rc,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);
    __atomic_store_n(&dma_stopping,1u,__ATOMIC_RELEASE);
}
static bool dma_accepts(const DmaOwner *d){
    return d&&!__atomic_load_n(&dma_stopping,__ATOMIC_ACQUIRE)&&elden_wifi_smmu_ready()&&
        elden_wlan_power_ready(d->arena.owner,d->arena.epoch)==0;
}
static void dma_order(){__asm__ volatile("dsb sy":::"memory");}
class DmaCall final {
public:
    DmaOwner *d=nullptr;
    DmaCall(){
        if(ml_at_interrupt_context()){dma_error(-22);return;}
        if(__atomic_load_n(&dma_run,__ATOMIC_ACQUIRE)!=2)return;
        d=__atomic_load_n(&dma_owner,__ATOMIC_ACQUIRE);
        __atomic_add_fetch(&dma_calls,1u,__ATOMIC_ACQ_REL);IOLockLock(d->lock);
        if(__atomic_load_n(&dma_stopping,__ATOMIC_ACQUIRE)||!elden_wifi_smmu_ready()){
            __atomic_store_n(&dma_stopping,1u,__ATOMIC_RELEASE);
            (void)elden_wifi_dma_arena_stop(&d->arena,d->arena.owner,d->arena.epoch);
        }
    }
    ~DmaCall(){if(d){IOLockUnlock(d->lock);__atomic_sub_fetch(&dma_calls,1u,__ATOMIC_RELEASE);}}
    DmaCall(const DmaCall&)=delete;
    DmaCall& operator=(const DmaCall&)=delete;
};
}
extern "C" int elden_wifi_dma_bind(const void *provider,uint64_t epoch){
    if(!provider||!epoch||ml_at_interrupt_context())return -22;
    if(__atomic_load_n(&dma_stopping,__ATOMIC_ACQUIRE)||!elden_wifi_smmu_ready()||elden_wlan_power_ready(provider,epoch))return -19;
    unsigned expected=0;if(!__atomic_compare_exchange_n(&dma_run,&expected,1u,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return -16;
    Context *c=__atomic_load_n(&active,__ATOMIC_ACQUIRE);DmaOwner *d=new DmaOwner;int rc=-12;
    if(d){
        __atomic_store_n(&dma_owner,d,__ATOMIC_RELEASE);
        d->lock=IOLockAlloc();
        d->blocks=static_cast<EldenWifiDmaBlock *>(IOMalloc(EldenWifiArenaMaxBlocks*sizeof(EldenWifiDmaBlock)));
        if(d->lock&&d->blocks&&c&&c->memory&&c->memory->data())
            rc=elden_wifi_dma_arena_init(&d->arena,provider,epoch,c->memory->data(),EldenWifiDmaIova,EldenWifiDmaBytes,d->blocks,EldenWifiArenaMaxBlocks);
        if(!rc&&!dma_accepts(d))rc=-108;
    }
    if(rc)dma_error(rc);
    __atomic_store_n(&dma_run,rc?3u:2u,__ATOMIC_RELEASE);return rc;
}
extern "C" void *elden_wifi_dma_alloc(size_t bytes,uint64_t *bus){
    if(bus)*bus=0;if(!bus)return nullptr;
    DmaCall call;if(!call.d)return nullptr;DmaOwner *d=call.d;
    if(!dma_accepts(d))return nullptr;
    void *p=nullptr;uint64_t b=0;
    if(elden_wifi_dma_arena_alloc(&d->arena,d->arena.owner,d->arena.epoch,bytes,&p,&b))return nullptr;
    /* Do not expose a new allocation if the owner was withdrawn while zeroing.
     * It has never reached the endpoint, so only its metadata can be reclaimed. */
    if(!dma_accepts(d)){
        __atomic_store_n(&dma_stopping,1u,__ATOMIC_RELEASE);
        (void)elden_wifi_dma_arena_stop(&d->arena,d->arena.owner,d->arena.epoch);
        int rc=elden_wifi_dma_arena_free(&d->arena,d->arena.owner,d->arena.epoch,bytes,p,b);if(rc)dma_error(rc);
        return nullptr;
    }
    dma_order();*bus=b;return p;
}
extern "C" void elden_wifi_dma_free(size_t bytes,void *cpu,uint64_t bus){
    if(!cpu)return;DmaCall call;if(!call.d)return;DmaOwner *d=call.d;
    int rc=elden_wifi_dma_arena_free(&d->arena,d->arena.owner,d->arena.epoch,bytes,cpu,bus);
    if(rc)dma_error(rc);
}
extern "C" uint64_t elden_wifi_dma_map(void *cpu,size_t bytes,int direction){
    DmaCall call;if(!call.d)return 0;DmaOwner *d=call.d;if(!dma_accepts(d))return 0;
    uint64_t bus=0;int rc=elden_wifi_dma_arena_map(&d->arena,d->arena.owner,d->arena.epoch,cpu,bytes,direction,&bus);
    if(rc){dma_error(rc);return 0;}dma_order();return dma_accepts(d)?bus:0;
}
extern "C" void elden_wifi_dma_sync(uint64_t bus,size_t bytes,int direction){
    DmaCall call;if(!call.d)return;DmaOwner *d=call.d;
    int rc=elden_wifi_dma_arena_bus_range(&d->arena,d->arena.owner,d->arena.epoch,bus,bytes,direction);
    if(rc)dma_error(rc);else dma_order();
}
extern "C" int elden_wifi_dma_msi_sink(uint64_t *bus){
    if(!bus)return -22;*bus=0;DmaCall call;if(!call.d)return -11;
    if(!dma_accepts(call.d))return -19;*bus=call.d->arena.iova;return 0;
}
extern "C" void elden_wifi_dma_stop_begin(void){__atomic_store_n(&dma_stopping,1u,__ATOMIC_RELEASE);}
extern "C" int elden_wifi_dma_status(EldenWifiDmaStatus *out){
    if(!out||ml_at_interrupt_context())return -22;
    unsigned state=__atomic_load_n(&dma_run,__ATOMIC_ACQUIRE);if(state==1)return -11;
    /* A binder can publish dma_owner after this load of state 0. Do not
     * inspect that pointer until the terminal state has acquired its fields. */
    if(state==0){EldenWifiDmaStatus empty={};empty.version=1;empty.stopping=__atomic_load_n(&dma_stopping,__ATOMIC_ACQUIRE);*out=empty;return 0;}
    DmaOwner *d=__atomic_load_n(&dma_owner,__ATOMIC_ACQUIRE);
    if(d&&d->lock&&!IOLockTryLock(d->lock))return -11;
    EldenWifiDmaStatus s={};s.version=1;s.run=state;s.stopping=__atomic_load_n(&dma_stopping,__ATOMIC_ACQUIRE);
    s.calls=__atomic_load_n(&dma_calls,__ATOMIC_ACQUIRE);s.first_error=__atomic_load_n(&dma_first_error,__ATOMIC_ACQUIRE);
    if(d){s.blocks=d->arena.count;s.live=d->arena.live;s.used=d->arena.used;s.peak=d->arena.peak;
        s.epoch=d->arena.epoch;s.allocation_failures=d->arena.allocation_failures;if(d->lock)IOLockUnlock(d->lock);}
    *out=s;return 0;
}
