// SPDX-License-Identifier: BSD-2-Clause-Patent
// Actual generated allocator, lease/doorbell, IRQ, command and snapshot code.
// The controller, page tables, IOKit allocation and scheduler are modeled here.
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <utility>
#include <vector>
#include "QueueCore.h"
#include "DmaPlan.h"
using IOReturn=int;using IOOptionBits=uint64_t;using IOByteCount=uint64_t;
using event_t=const volatile void*;using boolean_t=bool;using wait_result_t=int;
enum{ kIOReturnSuccess,kIOReturnBadArgument,kIOReturnNotReady,kIOReturnBusy,kIOReturnIOError,kIOReturnTimeout,
      kIOReturnError,kIOReturnNotWritable,THREAD_UNINT,THREAD_WAITING=-1,THREAD_AWAKENED=0,THREAD_TIMED_OUT=1 };
constexpr uint64_t kIODirectionInOut=3,kIOMemoryPhysicallyContiguous=1<<8,kIOMemoryMapperNone=1<<9;
constexpr unsigned kIOMapAnywhere=1,kIOMapWriteCombineCache=1<<12,kMicrosecondScale=1000,kMillisecondScale=1000000,NSEC_PER_USEC=1000;
static void *kernel_task,*THREAD_CONTINUE_NULL;
static unsigned failures,releaseCalls,mapReleases,allocCeiling=~0u;
static uint64_t nextPa=0x100000000ULL,now=1000000,step=1000;
static uint64_t cacheAttribute=0x44;
static bool writeFault,panicMode,irqEnabled=true,preemptible=true,waiting,awakened,autoFinish;
static bool prepareFail;
static event_t waitingEvent;
static uint32_t regs[256],waitUs,waitBlocks,peakDoorbell;
static std::function<void()> clockHook,assertHook,blockHook;
static void once(std::function<void()> &f){auto g=std::move(f);f={};if(g)g();}
struct IOLock{bool held=false;};static std::vector<IOLock*> locks;
static IOLock *IOLockAlloc(){auto *p=new IOLock;locks.push_back(p);return p;}
static void IOLockLock(IOLock*p){assert(p&&!p->held);p->held=true;}
static void IOLockUnlock(IOLock*p){assert(p&&p->held);p->held=false;}
struct IOMemoryMap;
struct IOBufferMemoryDescriptor {
    uint8_t *data;uint64_t pa,size,cache;bool released=false,prepared=false;
    static std::vector<IOBufferMemoryDescriptor*> all;
    static IOBufferMemoryDescriptor *inTaskWithOptions(void*,IOOptionBits options,unsigned n,unsigned alignment){
        assert(alignment==4096);if(n>allocCeiling)return nullptr;
        auto *d=new IOBufferMemoryDescriptor;d->size=n;d->data=static_cast<uint8_t*>(std::aligned_alloc(4096,(n+4095)&~4095u));assert(d->data);
        d->pa=nextPa;d->cache=(options&kIOMapWriteCombineCache)?0x44:0xff;nextPa+=(n+65535)&~65535ULL;all.push_back(d);return d;
    }
    void *getBytesNoCopy(){return data;}
    uint64_t getPhysicalSegment(uint64_t at,IOByteCount*n,IOOptionBits){assert(at<size&&!released);if(n)*n=size-at;return pa+at;}
    IOMemoryMap *createMappingInTask(void*,unsigned,unsigned);
    IOReturn prepare(uint64_t){if(prepareFail)return kIOReturnError;assert(!prepared);prepared=true;return 0;}
    IOReturn complete(uint64_t){assert(prepared);prepared=false;return 0;}
    void release(){assert(!released&&!prepared);released=true;releaseCalls++;}
};
std::vector<IOBufferMemoryDescriptor*> IOBufferMemoryDescriptor::all;
struct IOMemoryMap {IOBufferMemoryDescriptor *d;bool released=false;uintptr_t getVirtualAddress(){return reinterpret_cast<uintptr_t>(d->data);}void release(){assert(!released);released=true;mapReleases++;}};
static std::vector<IOMemoryMap*> maps;
IOMemoryMap *IOBufferMemoryDescriptor::createMappingInTask(void*,unsigned,unsigned){auto *m=new IOMemoryMap{this};maps.push_back(m);return m;}
static uint64_t virtualPhysical(uintptr_t va){
    for(auto*d:IOBufferMemoryDescriptor::all)if(!d->released&&va>=reinterpret_cast<uintptr_t>(d->data)&&va-reinterpret_cast<uintptr_t>(d->data)<d->size)return d->pa+va-reinterpret_cast<uintptr_t>(d->data);
    assert(false);return 0;
}
static uint8_t *physicalVirtual(uint64_t pa,unsigned bytes){
    for(auto*d:IOBufferMemoryDescriptor::all)if(!d->released&&pa>=d->pa&&pa-d->pa<d->size&&bytes<=d->size-(pa-d->pa))return d->data+(pa-d->pa);
    assert(false);return nullptr;
}
static struct Host {uintptr_t hc=1,smmu=2;IOBufferMemoryDescriptor *dma=nullptr;uint8_t *virt=nullptr;uint64_t phys=0;IOLock *lock=nullptr;bool ready=false,poisoned=false;unsigned dmaBytes=0;}gHost;
#include "Diagnostic.inc"
static UfsRootDiagnostics gRootDiagnostic;
static uint32_t read32(uintptr_t base,unsigned off){if(base==2&&off==0x28)return 0x1555;assert(off/4<256);return regs[off/4];}
static void hostWrite(unsigned off,uint32_t value){
    if(off==0x20){regs[off/4]&=~value;return;}
    if(off==0x58){regs[off/4]|=value;peakDoorbell=std::max(peakDoorbell,static_cast<uint32_t>(__builtin_popcount(regs[off/4])));return;}
    regs[off/4]=value;
}
static void cacheCivac(const void*,size_t){}
static void cacheInvalidate(const void*,size_t){}
static IOReturn recordTransport(IOReturn r,uint32_t ocs){gRootDiagnostic.result=static_cast<uint32_t>(r);gRootDiagnostic.ocs=ocs;return r;}
static void IOLog(const char*,...){}
static void finishAll();
static uint64_t mach_absolute_time(){now+=step;once(clockHook);if(autoFinish&&regs[0x58/4])finishAll();return now;}
static void clock_interval_to_deadline(uint32_t n,uint32_t unit,uint64_t*d){*d=now+uint64_t(n)*unit;}
static void nanoseconds_to_absolutetime(uint64_t ns,uint64_t*t){*t=ns;}
static void absolutetime_to_nanoseconds(uint64_t t,uint64_t*ns){*ns=t;}
static bool ml_get_interrupts_enabled(){return irqEnabled;}
static bool preemption_enabled(){return preemptible;}
static unsigned panic_active(){return panicMode;}
static int current_thread(){return 1;}
static wait_result_t assert_wait_timeout(event_t event,int,uint32_t us,uint32_t scale){assert(!waiting&&us&&scale==1000);waiting=true;waitingEvent=event;awakened=false;waitUs=us;once(assertHook);return THREAD_WAITING;}
static void clear_wait(int,int){assert(waiting);waiting=false;}
static void thread_wakeup(event_t event){if(waiting&&waitingEvent==event)awakened=true;}
static wait_result_t thread_block(void*){for(auto*l:locks)assert(!l->held);assert(waiting);waitBlocks++;once(blockHook);waiting=false;if(awakened)return THREAD_AWAKENED;now+=uint64_t(waitUs)*1000;return THREAD_TIMED_OUT;}
static void IODelay(unsigned us){now+=uint64_t(us)*1000;}
static void modeledTranslate(uintptr_t va,uint64_t*r,uint64_t*w){
    uint64_t pa=virtualPhysical(va),cache=cacheAttribute;
    if(cache==0x44)for(auto*d:IOBufferMemoryDescriptor::all)if(pa>=d->pa&&pa-d->pa<d->size)cache=d->cache;
    *r=(cache<<56)|(pa&~4095ULL);*w=writeFault?1:*r;
}
static void modeledBarrier(){}
extern "C" IOReturn armcpu_spi_attach(uint32_t n,bool edge,void(*)(void*),void*,uint32_t*r,uint64_t*a){assert(n==297&&!edge);*r=0xa003;*a=0;return 0;}
extern "C" IOReturn armcpu_spi_mask(uint32_t n,bool){assert(n==297);return 0;}
#define NATIVE_UFS_READ_ONLY 1
#include "RootTransportLayout.h"
#include "TransferPoll.h"
#include "Prelude.inc"
#include "Completion.inc"
#include "Commands.inc"
struct Window {
#include "NativeWindow.inc"
};
static void finish(unsigned index,uint8_t ocs=0,uint8_t scsi=0,bool badTag=false){
    const UfsSlot &s=gSlotGeom[index];assert(regs[0x58/4]&s.bit);
    uint8_t *rsp=s.ucd+kRspOffset;memset(rsp,0,512);
    rsp[0]=s.ucd[0]==0?0x20:s.ucd[0]==0x16?0x36:0x21;
    rsp[2]=s.ucd[2];rsp[3]=s.ucd[3]+(badTag?1:0);rsp[7]=scsi;
    if(s.ucd[0]==0x16){rsp[12]=s.ucd[12];rsp[13]=s.ucd[13];rsp[23]=0x11;}
    auto*word=reinterpret_cast<uint32_t*>(s.utrd);unsigned count=word[7]&0xffff;
    auto*prd=reinterpret_cast<uint32_t*>(s.ucd+kPrdtOffset);
    for(unsigned p=0;p<count;p++){
        uint64_t address=prd[p*4]|(uint64_t(prd[p*4+1])<<32);unsigned bytes=prd[p*4+3]+1;
        memset(physicalVirtual(address,bytes),0x40+index,bytes);
    }
    word[2]=ocs;regs[0x58/4]&=~s.bit;regs[0x20/4]|=1;eldenUfsInterrupt(nullptr);
}
static void finishAll(){for(unsigned i=0;i<gSlotCount;i++)if(regs[0x58/4]&gSlotGeom[i].bit)finish(i);}
static void reset(unsigned ceiling=~0u,unsigned attr=0x44,bool wf=false){
    // Model a fresh boot between independent cases, never a driver recovery.
    for(auto*m:maps)delete m;maps.clear();
    for(auto*d:IOBufferMemoryDescriptor::all){std::free(d->data);delete d;}IOBufferMemoryDescriptor::all.clear();
    for(auto*l:locks)delete l;locks.clear();
    gHost={};memset(regs,0,sizeof(regs));regs[0]=0x0100001f;
    nextPa=0x100000000ULL;now=1000000;step=1000;cacheAttribute=attr;writeFault=wf;
    releaseCalls=mapReleases=waitBlocks=peakDoorbell=0;allocCeiling=ceiling;
    prepareFail=panicMode=waiting=awakened=autoFinish=false;irqEnabled=preemptible=true;clockHook=assertHook=blockHook={};
    gRootDiagnostic={};gQueuePool={};gQueueFailed=gQueueFinalStop=gQueueFailureRecorded=0;gQueueCommands=gDirectCommands=gStagedCommands=0;
    gOutstanding=gSnapshotCount=0;gDmaLimit=gUtrlPhys=0;gListUncached=false;gSlotCount=1;gListDma=gRegionB=nullptr;gListMap=nullptr;gSnapshotLock=nullptr;
    for(unsigned i=0;i<kSlots;i++){gSlotGeom[i]={};gSlotDiagnostics[i]={};gSlotGen[i]=0;gSlotIssuedAt[i]=0;gSlotOpcode[i]=0;}
    for(auto&s:gSnapshots)s={};
    eldenUfsIrqState=eldenUfsIrqAttached=eldenUfsGen=0;eldenUfsIrqHc=0;eldenUfsSpinTicks=0;
    eldenUfsIrqs=eldenUfsSleeps=eldenUfsWakes=eldenUfsWaitTimeouts=eldenUfsWaitOther=eldenUfsIrqSpurious=eldenUfsWaitTicks=eldenUfsCommands=0;
}
static void setup(unsigned expected=32){const char *why="";assert(eldenAllocateQueue(&why));assert(eldenUpgradeQueue(&why));assert(gSlotCount==expected);gHost.ready=true;eldenUfsIrqStart();assert(eldenUfsIrqRunning());}
int main(){unsigned cases=0;
#if ELDEN_LEGACY_CACHE
    reset();setup(16);assert(!gListUncached);reset();printf("PASS reproduced legacy cache-flag omission: 16-slot fallback\n");return 0;
#endif
    for(unsigned attr:{0x44u,0xffu}){reset(~0u,attr);setup(attr==0x44?32:16);assert(gListUncached==(attr==0x44));cases++;}
    reset(~0u,0x44,true);setup(16);assert(!gListUncached&&mapReleases==1);cases++;
    reset(kDmaBytesOneSlot);setup(1);cases++;
    reset();setup();prepareFail=true;assert(!eldenAllocateSnapshot(4096)&&!gSnapshotCount);cases++;
    reset();setup();
    {UfsSlot slots[32];uint64_t deadlines[32];uint32_t status;uint8_t cdb[10]={0x28};
     for(unsigned i=0;i<32;i++){assert(nativeSlotTake(slots[i]));assert(hostScsiIssue(slots[i],0,cdb,10,2,4096,1000000,&deadlines[i],&status)==0);}
     assert(regs[0x58/4]==0xffffffffu&&peakDoorbell==32&&gQueuePool.peak==32);
     for(unsigned i=32;i-- >0;){finish(i);gRootDiagnostic.residual=0x12345678;assert(hostScsiAwait(slots[i],0,4096,deadlines[i],&status)==0&&status==0);nativeSlotGive(slots[i]);}
     assert(!gQueuePool.busy&&!gQueuePool.issuedMask&&!gOutstanding&&eldenUfsIrqs==32);cases++;}
    // IRQ before the doorbell must not consume the newly published bit/OCS15.
    reset();setup();
    {UfsSlot s;assert(nativeSlotTake(s));uint64_t deadline;uint32_t scsi;uint8_t cdb[10]={0x28};
     clockHook=[] {regs[0x20/4]|=1;eldenUfsInterrupt(nullptr);};
     assert(hostScsiIssue(s,0,cdb,10,2,4096,1000000,&deadline,&scsi)==0);
     assert(gOutstanding==1&&gSlotGen[0]==0);finish(0);assert(gSlotGen[0]==1);assert(hostScsiAwait(s,0,4096,deadline,&scsi)==0);nativeSlotGive(s);cases++;}
    // Real retained snapshot -> direct PRDT; ordinary memory -> staged copy.
    reset();setup();
    {UfsSlot a,b;assert(nativeSlotTake(a)&&nativeSlotTake(b));uint64_t da,db;uint32_t scsi;uint8_t cdb[10]={0x28};
     assert(hostScsiIssue(a,0,cdb,10,2,4096,1000000,&da,&scsi)==0&&hostScsiIssue(b,0,cdb,10,2,4096,1000000,&db,&scsi)==0);
     blockHook=[&]{finish(b.index);};hostWaitCompletion(a.index,0,now-500000,da);assert(eldenUfsWaitTimeouts==1&&!eldenUfsWakes);
     blockHook=[&]{finish(a.index);};hostWaitCompletion(a.index,0,now-500000,da);assert(eldenUfsWakes==1);
     assert(hostScsiAwait(a,0,4096,da,&scsi)==0&&hostScsiAwait(b,0,4096,db,&scsi)==0);nativeSlotGive(a);nativeSlotGive(b);cases++;}
    for(bool granted:{false,true}){
        reset();setup();UfsSlot held[32];for(auto &s:held)assert(nativeSlotTake(s));
        if(granted)blockHook=[&]{nativeSlotGive(held[0]);};
        UfsSlot next;assert(nativeSlotTake(next)==granted&&!gQueuePool.queued&&!gQueuePool.head);
        if(granted)nativeSlotGive(next);else nativeSlotGive(held[0]);
        for(unsigned i=1;i<32;i++)nativeSlotGive(held[i]);assert(!gQueuePool.busy);cases++;
    }
    reset();setup();autoFinish=true;
    {uint8_t *owned=eldenAllocateSnapshot(1<<20);assert(owned&&gSnapshotCount==1);
     assert(hostRead4k(0,128,256,owned)==0&&gDirectCommands==1&&!gStagedCommands&&owned[0]==0x40&&owned[(1<<20)-1]==0x40);
     std::vector<uint8_t> ordinary(4096);assert(hostRead4k(0,0,1,ordinary.data())==0&&gStagedCommands==1&&ordinary[0]==0x40);
     unsigned released=releaseCalls;eldenRetireSnapshot(owned);assert(releaseCalls==released&&!gSnapshots[0].descriptor->released&&gSnapshots[0].descriptor->prepared);cases++;}
    reset();setup();
    {uint8_t *owned=eldenAllocateSnapshot(4096);assert(owned);memset(owned,0xa5,4096);step=10000000;
     assert(hostRead4k(0,0,1,owned)==kIOReturnTimeout&&queueFailed()&&gQueuePool.failed&&gQueuePool.slots[0].state==EldenUfsQuarantined);
     unsigned released=releaseCalls;eldenRetireSnapshot(owned);assert(releaseCalls==released&&!gSnapshots[0].descriptor->released);
     finish(0);assert(owned[0]==0x40);UfsSlot other;assert(!nativeSlotTake(other));cases++;}
    for(bool wrongTag:{false,true}){
        reset();setup();UfsSlot s;assert(nativeSlotTake(s));uint8_t cdb[10]={0x28};uint64_t deadline;uint32_t scsi;
        assert(hostScsiIssue(s,0,cdb,10,2,4096,1000000,&deadline,&scsi)==0);
        finish(0,0,wrongTag?0:8,wrongTag);auto result=hostScsiAwait(s,0,4096,deadline,&scsi);
        assert(result!=0&&queueFailed()==wrongTag);nativeSlotGive(s);cases++;
    }
    reset();setup();
    {UfsSlot a,b;assert(nativeSlotTake(a)&&nativeSlotTake(b));uint64_t d;uint32_t scsi;uint8_t cdb[10]={0x28};
     assert(hostScsiIssue(a,0,cdb,10,2,4096,1000000,&d,&scsi)==0);regs[0x20/4]|=0x800;eldenUfsInterrupt(nullptr);
     assert(queueFailed()&&hostScsiIssue(b,0,cdb,10,2,4096,1000000,&d,&scsi)!=0&&regs[0x58/4]==1);nativeSlotGive(b);nativeSlotGive(a);assert(gQueuePool.slots[0].state==EldenUfsQuarantined);cases++;}
    // Pre-sync shutdown leaves polling reads available; final halt closes them.
    reset();setup();autoFinish=true;
    {std::vector<uint8_t> out(4096);elden_ufs_wait_shutdown();assert(!eldenUfsIrqRunning()&&hostRead4k(0,0,1,out.data())==0);
     elden_ufs_queue_halt();assert(hostRead4k(0,0,1,out.data())!=0&&queueFinalStop());cases++;}
    reset();setup();
    {Window w;w.windowLock=IOLockAlloc();for(unsigned i=0;i<4;i++){w.bounces[i]=eldenAllocateSnapshot(kDataMax);assert(w.bounces[i]);w.bounceFree|=1u<<i;}
     uint8_t *a=w.takeBounce(),*b=w.takeBounce();assert(a&&b&&a!=b);memset(a,0x11,4096);memset(b,0x22,4096);assert(a[0]==0x11&&b[0]==0x22);
     w.giveBounce(a);queueSignalFault();w.giveBounce(b);assert(!w.takeBounce()&&!(w.bounceFree&2));cases++;}
    reset(); // modeled reset releases all host allocations after testing
    printf("PASS %u native allocator/queue/IRQ/command/snapshot cases; 32 concurrent doorbells\n",cases);
}
