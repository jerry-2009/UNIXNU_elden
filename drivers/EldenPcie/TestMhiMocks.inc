/* SPDX-License-Identifier: GPL-2.0-only */
#include <cstdlib>
static void *IOMalloc(size_t n){return malloc(n);}
static void IOFree(void *p,size_t){free(p);}
static void IODelay(unsigned us){clock_us+=us;}
static unsigned fw_loaded,fw_stops,step_calls,scan_calls,stop_calls,irq_bits,preempt_depth;
static unsigned shutdown_dma_calls;static int shutdown_dma_error;
static int fw_error,start_error;static bool hang_reset,bad_bar,hold_transactions;
static uint64_t reset_due;static uint32_t mhi_bar[1024];
static int fake_device;
static const lx_platform *platform_api;static const nw_board *board_api;
extern "C" {
int elden_wifi_runtime_bind(void *);int elden_wifi_runtime_unbind(void *);int elden_wifi_runtime_enable_master(void);
int elden_wlan_power_cpr(const void *,uint64_t,const EldenWcnPmuParam *,size_t){return -95;}
int elden_wifi_firmware_bind(const void *p,uint64_t e){CHECK(p==active&&e==7);return 0;}
void elden_wifi_firmware_stop_begin(){fw_stops++;}
int elden_wifi_firmware_get(const char *,const uint8_t **data,size_t *bytes){
    static const uint8_t payload[16]={};if(fw_error)return fw_error;fw_loaded++;*data=payload;*bytes=sizeof(payload);return 0;
}
int elden_wifi_firmware_status(EldenWifiFirmwareStatus *s){*s={};s->version=1;s->run=2;s->loaded=fw_loaded;s->epoch=7;s->stopping=fw_stops;return 0;}
struct nw_wifi_stats nw_wifi_stats;
void nw_wifi_set_platform(const lx_platform *p){platform_api=p;}
void nw_wifi_irq_mode(int){}
void nw_wifi_irq_pending(uint32_t bits){irq_bits|=bits;}
void nw_wifi_poll(void){}
unsigned nw_wifi_wait_ms(unsigned){return 1;}
int nw_wifi_scan(const uint8_t *,size_t){scan_calls++;return 0;}
int nw_wifi_bss_count(void){return 3;}
void nw_wifi_stop(void){
    stop_calls++;
    if(active->runtime_stack_started){
#ifndef ELDEN_EXPECT_OLD_STOP
        CHECK(!elden_pcie_dma_cleanup_admit(active,active->wlan_epoch));
        CHECK(elden_pcie_dma_cleanup_admit(&fake_device,active->wlan_epoch)==-19);
        CHECK(elden_pcie_dma_cleanup_admit(active,active->wlan_epoch+1)==-19);
        active->msi.irq_error=-5;CHECK(elden_pcie_dma_cleanup_admit(active,active->wlan_epoch)==-5);active->msi.irq_error=0;
        bool wrong_thread=false;std::thread foreign([&]{wrong_thread=elden_pcie_dma_cleanup_admit(active,active->wlan_epoch)==-19;});
        foreign.join();CHECK(wrong_thread);
        uint64_t deadline=active->runtime_cleanup_deadline;active->runtime_cleanup_deadline=clock_us;
        CHECK(elden_pcie_dma_cleanup_admit(active,active->wlan_epoch)==-19);active->runtime_cleanup_deadline=deadline;
#endif
        uint64_t bus=0;void *packet=platform_api->dma_alloc(256,&bus);
        if(!packet){shutdown_dma_error=-12;return;}
        CHECK(platform_api->dma_map(packet,256,1)==bus);platform_api->dma_sync(bus,256,1);
        platform_api->dma_free(256,packet,bus);shutdown_dma_calls++;
    }
    if(active->runtime_consumer){
        CHECK(!board_api->cfg_write(0x80,4,cfg[0x80/4]&~(1u<<16)));
        CHECK(!elden_wifi_runtime_unbind(&fake_device));
    }
}
int nw_wifi_start(const lx_platform *p,const nw_board *b){
    CHECK(p==platform_api&&b->device_id==0x110e&&b->bar_len==0x200000);board_api=b;
    CHECK(p->now_ns&&p->boottime_ns&&p->preempt_disable&&p->preempt_enable);
    p->preempt_disable();p->preempt_enable();void *heap=p->alloc(31);CHECK(heap);p->free(heap);
    if(start_error){nw_wifi_stop();return start_error;}
    CHECK(!elden_wifi_runtime_bind(&fake_device));uint32_t lo,hi,data;
    CHECK(!b->msi_target(&lo,&hi,&data));CHECK(!b->cfg_write(0x84,4,lo));CHECK(!b->cfg_write(0x88,4,hi));
    CHECK(!b->cfg_write(0x8c,2,data));CHECK(!b->cfg_write(0x80,4,cfg[0x80/4]|(5u<<20)|(1u<<16)));
    CHECK(!elden_wifi_runtime_enable_master());CHECK((cfg[1]&7)==6);
    uint64_t bus=0;void *dma=p->dma_alloc(4096,&bus);CHECK(dma&&bus==0x10001000);p->dma_sync(bus,4096,1);
    mhi_bar[0x38/4]=0x200;mhi_bar[0x48/4]=0x201;cfg[0x48/4]|=32u<<16;
    dbi[EldenMsiStatus/4]=3;in_irq=true;irq_handler(irq_cookie);in_irq=false;
    nw_wifi_stats.stage=4;return 0;
}
/* powered models public WLAN admission here; the register model remains on
 * until successful native quiescence, just as WlanPower's callback contract. */
int nw_wifi_step(void){platform_api->poll();if(++step_calls==2){stop_requested=1;powered=false;elden_wifi_dma_close_admission();}return 0;}
}
static void _disable_preemption(){preempt_depth++;}
static void _enable_preemption(){CHECK(preempt_depth);preempt_depth--;}
[[noreturn]] static void panic(const char *text){fprintf(stderr,"unexpected panic: %s\n",text);abort();}
static unsigned elden_recovery_deadline_remaining(){return 300;}
