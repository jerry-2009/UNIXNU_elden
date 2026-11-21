/* SPDX-License-Identifier: GPL-2.0-only */
#include "Msi.h"
#include <atomic>
#include <cassert>
#include <cstdio>
#include <mutex>
#include <thread>
static unsigned checks,scenarios;
#define CHECK(x) do{++checks;assert(x);}while(0)
struct Model {
    EldenPcieMsi m={};std::mutex lock;
    uint32_t lo=0,hi=0,enable=0,mask=~0u,status=0,after_ack=0;
    std::atomic<unsigned> calls{0},writes{0},wakes{0};unsigned fail_at=0;
    bool admitted=true,drained=true,masked=true,bad_flags=false,stuck=false;
    uint64_t now=100;
    void (*handler)(void *)=nullptr;void *cookie=nullptr;
    std::atomic<bool> block{false},entered{false},release{false};
    Model(){m.io={this,admit,quiesced,read,write,attach,mask_irq,wake,clock,delay};++scenarios;}
    int hit(){return ++calls==fail_at?-123:0;}
    static int admit(void *p){auto &x=*(Model *)p;int rc=x.hit();return rc?rc:x.admitted?0:-19;}
    static int quiesced(void *p){auto &x=*(Model *)p;int rc=x.hit();return rc?rc:x.drained?0:-16;}
    uint32_t &reg(uint32_t off){switch(off){case EldenMsiAddrLo:return lo;case EldenMsiAddrHi:return hi;case EldenMsiEnable:return enable;case EldenMsiMask:return mask;case EldenMsiStatus:return status;default:assert(false);return status;}}
    static int read(void *p,uint32_t off,uint32_t *v){auto &x=*(Model *)p;int rc=x.hit();if(rc)return rc;
        if(off==EldenMsiStatus&&x.block){x.entered=true;while(!x.release)std::this_thread::yield();}
        std::lock_guard<std::mutex> hold(x.lock);*v=x.reg(off);return 0;}
    static int write(void *p,uint32_t off,uint32_t v){auto &x=*(Model *)p;int rc=x.hit();if(rc)return rc;
        std::lock_guard<std::mutex> hold(x.lock);x.writes++;
        if(x.stuck)return 0;
        if(off==EldenMsiStatus){x.status&=~v;x.status|=x.after_ack;x.after_ack=0;}else x.reg(off)=v;return 0;}
    static int attach(void *p,uint32_t id,void(*fn)(void *),void *cookie,uint32_t *flags,uint64_t *router){auto &x=*(Model *)p;int rc=x.hit();if(rc)return rc;
        assert(id==173);x.handler=fn;x.cookie=cookie;*flags=x.bad_flags?0xa007:0xa003;*router=0;return 0;}
    static int mask_irq(void *p,uint32_t id,bool value){auto &x=*(Model *)p;int rc=x.hit();if(rc)return rc;assert(id==173);x.masked=value;return 0;}
    static void wake(void *p){((Model *)p)->wakes++;}
    static uint64_t clock(void *p){return ((Model *)p)->now;}
    static void delay(void *p,unsigned us){((Model *)p)->now+=us;std::this_thread::yield();}
    int prepare(){return elden_pcie_msi_prepare(&m,0x10000000,0);}
    int arm(){return elden_pcie_msi_arm(&m);}
    void raise(uint32_t value){status=value;assert(handler);handler(cookie);}
};
int main(){
    unsigned count=0;
    {Model x;CHECK(x.prepare()==0&&x.m.state==EldenMsiPrepared&&x.masked&&x.enable==0);
     CHECK(x.lo==0x10000000&&x.hi==0);CHECK(x.arm()==0&&x.m.state==EldenMsiArmed&&x.enable==~0u&&x.mask==0&&!x.masked);count=x.calls;
     x.after_ack=8;x.raise(5);CHECK(elden_pcie_msi_pending(&x.m)==5&&x.status==8);x.handler(x.cookie);
     CHECK(elden_pcie_msi_pending(&x.m)==8&&x.status==0&&x.wakes==2);CHECK(elden_pcie_msi_pending(&x.m)==0);
     x.drained=false;CHECK(elden_pcie_msi_stop(&x.m,1000)==-16&&!x.m.stop_attempted&&!x.masked);
     x.raise(1u<<31);CHECK(elden_pcie_msi_pending(&x.m)==1u<<31);
     x.drained=true;CHECK(elden_pcie_msi_stop(&x.m,1000)==0&&x.m.state==EldenMsiStopped&&x.masked&&x.enable==0&&x.mask==~0u);
     unsigned accesses=x.calls;x.handler(x.cookie);CHECK(x.calls==accesses);CHECK(elden_pcie_msi_stop(&x.m,1000)==0&&x.calls==accesses);
     CHECK(x.prepare()==-16);}
    for(unsigned i=1;i<=count;i++){Model x;x.fail_at=i;int rc=x.prepare();if(!rc)rc=x.arm();CHECK(rc==-123);
        CHECK(x.m.state==EldenMsiHeld||x.m.state==EldenMsiRefused);CHECK(x.m.error==-123);}
    {Model x;x.enable=1;x.mask=0;CHECK(x.prepare()==-16&&x.writes==0&&x.m.state==EldenMsiRefused);}
    {Model x;x.status=3;CHECK(x.prepare()==0&&x.status==0);}
    {Model x;x.stuck=true;x.mask=0;CHECK(x.prepare()==-71&&x.m.state==EldenMsiHeld);}
    {Model x;x.bad_flags=true;CHECK(x.prepare()==-71&&x.masked);}
    {Model x;CHECK(elden_pcie_msi_prepare(&x.m,0x10000001,0)==-22&&x.calls==0);}
    {Model x;CHECK(x.prepare()==0&&x.arm()==0);x.fail_at=x.calls+2;x.raise(7);
     CHECK(__atomic_load_n(&x.m.irq_error,__ATOMIC_ACQUIRE)==-123&&x.masked&&x.status==7);CHECK(elden_pcie_msi_pending(&x.m)==0);}
    {Model x;CHECK(x.prepare()==0&&x.arm()==0);for(unsigned i=0;i<128;i++)x.raise(0);
     CHECK(__atomic_load_n(&x.m.irq_error,__ATOMIC_ACQUIRE)==-5&&x.masked);}
    {Model x;CHECK(x.prepare()==0&&x.arm()==0);unsigned writes=x.writes;
     CHECK(elden_pcie_msi_stop(&x.m,99)==-110&&x.writes==writes&&!x.m.stop_attempted);}
    {Model x;CHECK(x.prepare()==0&&x.arm()==0);x.fail_at=x.calls+2;
     CHECK(elden_pcie_msi_stop(&x.m,1000)==-123&&x.m.state==EldenMsiHeld);unsigned writes=x.writes;
     CHECK(elden_pcie_msi_stop(&x.m,10000)==-123&&x.writes==writes);}
    {Model x;CHECK(x.prepare()==0&&x.arm()==0);x.block=true;x.status=2;
     std::thread irq([&]{x.handler(x.cookie);});while(!x.entered)std::this_thread::yield();
     CHECK(elden_pcie_msi_stop(&x.m,130)==-110&&x.m.state==EldenMsiHeld&&x.masked);
     x.release=true;irq.join();CHECK(__atomic_load_n(&x.m.irq_calls,__ATOMIC_SEQ_CST)==0);}
    printf("%u MSI receiver scenarios / %u checks passed; MMIO/GIC modeled, no hardware acceptance\n",scenarios,checks);
}
