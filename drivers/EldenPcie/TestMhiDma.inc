/* The composed MHI fixture uses the production DMA adapter + arena.
 * Only IOKit memory/locks, power readiness and barriers are modeled here. */
#include <mutex>
#include <vector>
#include <thread>
#include "DmaTables.h"
#include "DmaArena.h"
namespace DmaModel {
using IOLock=std::mutex;
static std::vector<void *> owned;
static std::vector<IOLock *> locks;
static void *IOMalloc(size_t n){void *p=malloc(n);if(p)owned.push_back(p);return p;}
static void IOFree(void *,size_t){assert(false&&"DMA backing retained until modeled platform reset");}
static IOLock *IOLockAlloc(){auto *p=new IOLock;locks.push_back(p);return p;}
static void IOLockLock(IOLock *p){p->lock();}
static void IOLockUnlock(IOLock *p){p->unlock();}
static bool IOLockTryLock(IOLock *p){return p->try_lock();}
struct Memory {uint8_t *cpu;uint8_t *data(){return cpu;}};
struct Context {Memory *memory;};
static Memory memory={};static Context context={&memory};static Context *active=&context;
static void host_order(){}
#include "DmaNativeHost.inc"
static void reset(){
    for(auto *p:locks)delete p;locks.clear();for(auto *p:owned)free(p);owned.clear();
    dma_owner=nullptr;dma_run=dma_stopping=dma_calls=dma_closed=0;dma_first_error=0;
    if(!memory.cpu)memory.cpu=(uint8_t *)aligned_alloc(4096,EldenWifiDmaBytes);
    assert(memory.cpu);
}
}
