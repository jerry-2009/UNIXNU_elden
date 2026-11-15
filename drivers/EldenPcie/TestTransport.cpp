/* SPDX-License-Identifier: GPL-2.0-only */
#include "Root.h"
#include "Endpoint.h"
#include "Config.h"
#include "Msi.h"
#include "TransportNative.h"
#include "DmaNative.h"
#include <cstdio>
#include <cstring>
#include <cassert>
static unsigned checks,cases,calls,fail_at,binds,wakes,dma_stops;
static bool powered=true,in_irq=false,bad_router=false;
static uint64_t clock_us=100;
static uint32_t cfg[1024],dbi[1024];
static void(*irq_handler)(void *);static void *irq_cookie;static bool irq_masked;
static unsigned stop_requested,stopped;
#define CHECK(x) do{++checks;assert(x);}while(0)
static int hit(){return ++calls==fail_at?-123:0;}
struct Region {
    uintptr_t va=1;uint32_t *data=nullptr;
    int read(uint32_t off,uint32_t *v){assert(!(off&3)&&off<4096);int rc=hit();if(!rc)*v=data[off/4];return rc;}
    int write(uint32_t off,uint32_t v){assert(!(off&3)&&off<4096);int rc=hit();if(rc)return rc;
        if(data==dbi&&off==EldenMsiStatus)data[off/4]&=~v;
        else if(data==cfg&&(off==4||off==0x48||off==0x50))data[off/4]=(data[off/4]&0xffff0000u&~v)|(v&0xffff);
        else data[off/4]=v;return 0;}
};
struct Context {
    Region maps[EldenPcieWindowCount],bar0_map;
    EldenPcieRoot root={};EldenPcieEndpoint endpoint={};uint64_t wlan_epoch=7;
    bool endpoint_confirmed=true,transport_requested=true,transport_ready=false,transport_cleanup=false;
    EldenPcieConfigAccess config={};EldenPcieMsi msi={};
    unsigned transport_stage=0,transport_wake=0,transport_gate=0;int transport_result=-11;
};
static Context context,*active=&context;
static bool ml_at_interrupt_context(){return in_irq;}
static int admit(void *p,uint64_t epoch){int rc=hit();return rc?rc:p==active&&epoch==7&&powered&&!stop_requested?0:-11;}
static int elden_wlan_power_ready(const void *p,uint64_t e){return p==active&&e==7&&powered?0:-11;}
static int elden_wifi_smmu_ready(){return !dma_stops;}
extern "C" int elden_wifi_dma_bind(const void *p,uint64_t e){int rc=hit();if(rc)return rc;CHECK(p==active&&e==7);binds++;return 0;}
extern "C" int elden_wifi_dma_msi_sink(uint64_t *p){int rc=hit();if(!rc)*p=0x10000000;return rc;}
extern "C" int elden_wifi_dma_status(EldenWifiDmaStatus *s){int rc=hit();if(rc)return rc;*s={};s->version=1;s->run=2;s->epoch=7;s->stopping=dma_stops;return 0;}
extern "C" void elden_wifi_dma_stop_begin(){dma_stops++;}
static int armcpu_spi_attach(uint32_t id,bool edge,void(*handler)(void *),void *cookie,uint32_t *flags,uint64_t *router){
    int rc=hit();if(rc)return rc;CHECK(id==173&&!edge);irq_handler=handler;irq_cookie=cookie;*flags=0xa003;*router=bad_router?1:0;return 0;
}
static int armcpu_spi_mask(uint32_t id,bool mask){int rc=hit();if(rc)return rc;CHECK(id==173);irq_masked=mask;return 0;}
using event_t=void *;
static void thread_wakeup(event_t){wakes++;}
static uint64_t now(void *){return clock_us;}
static void delay(void *,unsigned us){clock_us+=us;}
static void IOSleep(unsigned ms){clock_us+=(uint64_t)ms*1000;}
static void log(const char *,...){}
#include "TransportNativeRuntime.inc"
static void reset(){
    ++cases;context={};active=&context;
    context.maps[EldenPcieConfig].data=cfg;context.maps[EldenPcieDbi].data=dbi;
    context.root.clocks_ready=context.root.perst_high=true;context.endpoint.epoch=7;
    memset(cfg,0,sizeof cfg);memset(dbi,0,sizeof dbi);
    cfg[0]=0x110e17cb;cfg[1]=0xa5000002;cfg[0x34/4]=0x40;cfg[0x40/4]=0x8010;
    cfg[0x80/4]=5|(5u<<17)|(1u<<23)|(1u<<24);cfg[0x48/4]=0x003f0000;
    dbi[EldenMsiMask/4]=~0u;clock_us=100;calls=fail_at=binds=wakes=dma_stops=stop_requested=stopped=0;
    powered=true;in_irq=bad_router=false;irq_handler=nullptr;irq_cookie=nullptr;irq_masked=true;
}
static int allow_master(void *){return 0;}
int main(){
    reset();transport_run(active);CHECK(!active->transport_result&&active->transport_ready&&binds==1);
    CHECK(active->config.pcie_cap==0x40&&active->config.msi_cap==0x80&&active->msi.state==EldenMsiArmed);
    unsigned setup_calls=calls;CHECK((cfg[1]&7)==2);
    EldenPcieTransportStatus s={};CHECK(!transport_snapshot(active,&s)&&s.ready&&!s.master_attempted);
    dbi[EldenMsiStatus/4]=5;in_irq=true;irq_handler(irq_cookie);in_irq=false;
    CHECK(dbi[EldenMsiStatus/4]==0&&wakes==1&&elden_pcie_msi_pending(&active->msi)==5);
    CHECK(elden_pcie_cfg_master(&active->config,true)==-95&&(cfg[1]&7)==2);
    stop_requested=1;powered=false;CHECK(transport_stop(active,clock_us+10000)==0);
    CHECK(active->msi.state==EldenMsiStopped&&irq_masked&&dma_stops==1);
    CHECK(!transport_snapshot(active,&s)&&!s.ready);CHECK((cfg[1]&0xffff0000u)==0xa5000000u);
    for(unsigned i=1;i<=setup_calls;i++){
        reset();fail_at=i;transport_run(active);CHECK(active->transport_result==-123&&!active->transport_ready);
        CHECK((cfg[1]&7)==2);
    }
    reset();active->endpoint_confirmed=false;transport_run(active);CHECK(active->transport_result==-19&&binds==0);
    reset();bad_router=true;transport_run(active);CHECK(active->transport_result==-71&&irq_masked);
    reset();cfg[0x80/4]|=0x8000;transport_run(active);CHECK(active->transport_result==-71&&!irq_handler);
    reset();transport_run(active);uint32_t value=0;
    CHECK(elden_pcie_cfg_read(&active->config,(int)0x80000008,2,&value,false)==0&&value==0);
    CHECK(elden_pcie_cfg_write(&active->config,(int)0x80000008,2,0x1000,false)==0);
    CHECK(cfg[0x48/4]==0x003f1000); // W1C status not accidentally copied back
    CHECK(elden_pcie_cfg_write(&active->config,4,2,6,false)==-1&&(cfg[1]&7)==2);
    CHECK(elden_pcie_cfg_write(&active->config,0x84,4,0x18000000,false)==-1);
    CHECK(elden_pcie_cfg_write(&active->config,0x84,4,0x10000000,false)==0);
    CHECK(elden_pcie_cfg_write(&active->config,0x80,4,cfg[0x80/4]|(5u<<20)|(1u<<16),false)==0);
    active->config.io.master_ready=allow_master;CHECK(elden_pcie_cfg_master(&active->config,true)==0&&(cfg[1]&7)==6);
    active->transport_cleanup=true;CHECK(elden_pcie_cfg_master(&active->config,false)==0&&(cfg[1]&7)==2);
    CHECK((cfg[1]&0xffff0000u)==0xa5000000u);CHECK(transport_quiesced(active)==-95); // no invented MHI-drain proof
    CHECK(elden_pcie_cfg_write(&active->config,0x80,4,cfg[0x80/4]&~(1u<<16),true)==0);
    CHECK(elden_pcie_cfg_write(&active->config,0x84,4,0x10000000,true)==-1);
    reset();transport_run(active);active->transport_gate=1;CHECK(transport_snapshot(active,&s)==-11);
    unsigned before=calls;stop_requested=1;CHECK(transport_stop(active,clock_us+1000)==-110&&calls==before);
    active->transport_gate=0;CHECK(transport_stop(active,clock_us+1000)==0);
    printf("%u native transport/config/MSI scenarios / %u checks passed; physical services and DMA provider modeled\n",cases,checks);
}
