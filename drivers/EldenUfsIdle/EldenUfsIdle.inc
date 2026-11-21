// SPDX-License-Identifier: BSD-2-Clause-Patent
#include "Ah8Control.h"
static EldenAh8Control gEldenAh8;
struct EldenAh8Io {
    bool idle(){return queueReady()&&eldenUfsIrqRunning()&&!gQueuePool.busy&&!gQueuePool.issuedMask&&!panic_active();}
    uint32_t read(unsigned off){return read32(gHost.hc,off);}
    void write(unsigned off,uint32_t value){hostWrite(off,value);}
    void active(bool value){__atomic_store_n(&gEldenAh8Active,value?1u:0u,__ATOMIC_RELEASE);}
    bool wake(){const char *why="";return hostWakeLink(&why);}
};
static int eldenAh8Change(bool start){
    if(!gHost.lock||!preemption_enabled()||!ml_get_interrupts_enabled()||panic_active())return -12;
    IOLockLock(gHost.lock);EldenAh8Io io;int result=start?gEldenAh8.start(io):gEldenAh8.stop(io);IOLockUnlock(gHost.lock);
    return result;
}
extern "C" int elden_ufs_idle_stop(){
    int result=-1;
    for(unsigned n=0;n<300&&result==-1;n++){result=eldenAh8Change(false);if(result==-1)IOSleep(10);}
    IOLog("ELDEN_UFS_IDLE stop=%d phase=%u error=%u active=%u\n",result,static_cast<unsigned>(gEldenAh8.phase),gEldenAh8.error,__atomic_load_n(&gEldenAh8Active,__ATOMIC_ACQUIRE));
    return result;
}
static bool eldenUfsIdleProof(const NativeUfsBlock *owner,const char *name,uint64_t absolute,uint64_t bytes){
    const EldenPinnedState *pin=eldenFindPinned(owner);
    if(!pin||!name||(absolute&4095)||bytes/4096!=pin->blocks||pin->blocks<32)return false;
    uint8_t *buffer=eldenAllocateSnapshot(kDataMax);if(!buffer)return false;
    IOLog("ELDEN_UFS_IDLE prepare name=%s cap=%x version=%x sys1=%u inherited-ahit=%x cfg=%x\n",
        name,read32(gHost.hc,0),read32(gHost.hc,0xe4),read32(gHost.hc,0xc0),gRootDiagnostic.linkAhit,read32(gHost.hc,0xfc));
    int result=eldenAh8Change(true);
    IOLog("ELDEN_UFS_IDLE enable=%d phase=%u ahit=%x cfg=%x ie=%x\n",result,static_cast<unsigned>(gEldenAh8.phase),read32(gHost.hc,0x18),read32(gHost.hc,0xfc),read32(gHost.hc,0x24));
    if(result){(void)elden_ufs_idle_stop();return false;}
    uint32_t enter=read32(gHost.hc,0x2700),exit=read32(gHost.hc,0x270c);unsigned transitions=0;
    for(unsigned i=0;i<16;i++){
        if(!queueReady())return false;
        IOSleep(20);uint64_t block=(uint64_t(i)*(pin->blocks-32)/15)&~31ULL;uint32_t count=(i&1)?32u:1u;
        uint64_t started=mach_absolute_time();IOReturn status=hostRead4k(0,absolute/4096+block,count,buffer);
        uint64_t ns=0;absolutetime_to_nanoseconds(mach_absolute_time()-started,&ns);
        bool verified=status==kIOReturnSuccess;
        for(unsigned b=0;b<count&&verified;b++)verified=eldenPinnedRead(pin,block+b,buffer+b*4096,4096);
        uint32_t nextEnter=read32(gHost.hc,0x2700),nextExit=read32(gHost.hc,0x270c);
        uint32_t enters=nextEnter-enter,exits=nextExit-exit;enter=nextEnter;exit=nextExit;
        if(enters&&enters<1024&&exits&&exits<1024)transitions++;
        IOLog("ELDEN_UFS_IDLE row name=%s seq=%u blocks=%u status=%x verified=%u ns=%llu hw-enter=%u hw-exit=%u enters=%u exits=%u\n",
            name,i,count,static_cast<uint32_t>(status),verified?1u:0u,ns,nextEnter,nextExit,enters,exits);
        if(!verified){queueSignalFault();return false;}
    }
    bool good=transitions==16&&read32(gHost.hc,0x18)==EldenAh8Control::timer&&queueReady();
    IOLog("ELDEN_UFS_IDLE end name=%s good=%u transitions=%u\n",name,good?1u:0u,transitions);
    if(!good)(void)elden_ufs_idle_stop();
    return good;
}
