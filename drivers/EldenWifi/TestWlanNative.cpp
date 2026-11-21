/* SPDX-License-Identifier: GPL-2.0-only */
/* Production native helper/export bodies. Kernel/map/transport services below
 * are deterministic host fixtures; no radio or physical MMIO is accessed. */
#include "WlanPower.h"
#include "WlanGpio.h"
#include "WcnSharedPower.h"
#include "EldenWifiResources.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(ELDEN_TEST_ROOT_POWER)
#include "Power.h"
#include "TestPowerDb.h"
#endif
#if defined(ELDEN_TEST_QMI)
#include "QmiPowerBinding.h"
extern "C" {
#include <linux/pwrseq/qcom_wcn.h>
}
#endif
static unsigned checks,scenarios;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"line%d: %s\n",__LINE__,#x);exit(1);}}while(0)
static uint64_t clock_us;
static int native_owner_data_status,elden_init_exec_accepted=1;
static bool armed=true,map_ok=true;
static unsigned boot_enable=1,creates,destroys,full_on_enable;
static int quiesce_result;
static bool quiesce_late;
static void (*qmp_hook)();
static int elden_recovery_armed(){return armed;}
static void IOSleep(unsigned n){clock_us+=n*1000ull;}
static void PE_parse_boot_argn(const char *s,unsigned *v,size_t){
    if(!strcmp(s,"elden-pcie-full-on")){*v=full_on_enable;return;}
    CHECK(!strcmp(s,"elden-wlan-power"));*v=boot_enable;
}
static uint64_t now_us(void *){return clock_us;}
static void delay(void *,unsigned n){clock_us+=n;}
struct Ignored{void *ctx=nullptr;template<typename... T>Ignored(void *p,T...):ctx(p){} Ignored()=default;};
struct Region{
    uint32_t regs[3]={0,0,0};unsigned writes=0,calls=0,fail_at=0,read_calls=0,fail_read=0;bool stuck=false;
    uint32_t read(unsigned off){calls++;read_calls++;return calls==fail_at||read_calls==fail_read?UINT32_MAX:regs[off/4];}
    void write(unsigned off,uint32_t v){
        calls++;writes++;if(calls==fail_at)return;
        regs[off/4]=v;
        if(!stuck&&(regs[0]&0x200u))regs[1]=(regs[1]&~1u)|((regs[1]>>1)&1u);
    }
};
struct Context{
    Region wlan;
    Ignored spmi,aoss_io,ipcc_io,qmp;
#if defined(ELDEN_TEST_ROOT_POWER)
    Sm8750CmdDb db={};Sm8750RpmhIo rpmh={};bool spmi_uncertain=false,rsc_uncertain=false;
    EldenPcieRail root_rails[2]={{880,4,0xad,0x87,0x80,7},{1200,4,0xad,0x87,0x80,7}};
    unsigned root_reads=0,root_fail_read=0,root_sends=0,root_fail_step=0;bool root_bad_after=false;
#else
    Ignored rpmh;
#endif
    EldenWcnSharedPower shared={};EldenWcnPower &power=shared.supply;
    EldenWlanGpio wlan_gpio={};uint64_t bt_epoch=0;unsigned bt_state=0;
    EldenWcnRailState rails[6];bool bt=false;unsigned bt_writes=0,qmp_calls=0,quiesces=0,qmp_fail_at=0;
    char qmp_messages[64][64]={};
    Context(){creates++;for(unsigned i=0;i<6;i++)rails[i]={elden_wcn_rail_specs[i].minimum,0x80,0x80,3};
#if defined(ELDEN_TEST_ROOT_POWER)
        test_power_db(&db);
#endif
    }
    ~Context(){destroys++;}
    bool map(){return map_ok;}
};
static Context *active;
static uint32_t core_read(void *,uint32_t){return 0;}
static uint32_t owner_read(void *,uint32_t){return 0;}
static uint32_t obs_read(void *,uint32_t){return 0;}
static void obs_write(void *,uint32_t,uint32_t){}
static uint32_t chan_read(void *,unsigned,uint32_t){return 0;}
static void chan_write(void *,unsigned,uint32_t,uint32_t){}
static uint32_t rsc_read(void *,uint32_t){return 0;}
static void rsc_write(void *,uint32_t,uint32_t){}
static uint32_t aoss_read(void *,uint32_t){return 0;}
static void aoss_write(void *,uint32_t,uint32_t){}
static uint32_t ipcc_read(void *,uint32_t){return 0;}
static void ipcc_write(void *,uint32_t,uint32_t){}
static void Sm8750AossQmpInit(Ignored *,Ignored *,unsigned,Ignored *){}
static int preflight(void *){return 0;}
static int rail_read(void *p,EldenWcnRail i,EldenWcnRailState *s){*s=static_cast<Context *>(p)->rails[i];return 0;}
static int rail_vote(void *p,EldenWcnRail i,uint16_t mv,uint8_t mode,bool en){CHECK(en&&mode==7);static_cast<Context *>(p)->rails[i]={mv,0x80,0x80,mode};return 0;}
static int qmp_send(void *p,const char *message){
    auto c=static_cast<Context *>(p);CHECK(c->qmp_calls<64&&strlen(message)<64);
    strcpy(c->qmp_messages[c->qmp_calls++],message);
    if(qmp_hook)qmp_hook();
    return c->qmp_calls==c->qmp_fail_at?-5:0;
}
static int bt_get(void *p,bool *v){*v=static_cast<Context *>(p)->bt;return 0;}
static int bt_set(void *p,bool v){auto c=static_cast<Context *>(p);c->bt=v;c->bt_writes++;return 0;}
static int wlan_get(void *p,bool *v){auto c=static_cast<Context *>(p);uint32_t io=c->wlan.read(4);if(io==UINT32_MAX)return -5;*v=io&1u;return 0;}
static int parents(void *,uint32_t *a,uint32_t *b){*a=600000000;*b=300000000;return 0;}
#include "WlanPowerNative.inc"
#include "WlanPowerExports.inc"
#if defined(ELDEN_TEST_ROOT_POWER)
#include "TestPowerNative.inc"
#include "PowerNative.inc"
#include "PowerExports.inc"
#endif
static int quiesce(const void *p,uint64_t epoch,uint64_t deadline){
    CHECK(active&&active->wlan.regs[1]&1u);
    CHECK(elden_wlan_power_check(p,epoch)==-11); /* revoked before callback */
    active->quiesces++;
    if(quiesce_late)clock_us=deadline;
    return quiesce_result;
}
static EldenWlanIdentity identity={(void *)0x1234,0x17cb,0x110e,0x100,0x1401,quiesce};
static void reset(){
    delete active;active=nullptr;clock_us=0;native_owner_data_status=0;elden_init_exec_accepted=1;
    armed=map_ok=true;boot_enable=1;quiesce_result=0;quiesce_late=false;
    platform_init_state=platform_io_busy=platform_stopping=wlan_api_busy=0;
    wlan_provider=nullptr;wlan_quiesce=nullptr;wlan_epoch=wlan_next_epoch=wlan_endpoint_epoch=0;creates=destroys=0;qmp_hook=nullptr;
    full_on_enable=0;
#if defined(ELDEN_TEST_ROOT_POWER)
    root_power_epoch=0;root_power_held=false;root_power_plan={};fresh_fault=0;
#endif
}
static void native_cases(){
    for(unsigned first=0;first<2;first++){
        reset();uint64_t epoch=0;Context *c=nullptr;
        if(!first){CHECK(!platform_get(&c));CHECK(!bt_power_acquire(c,1));}
        CHECK(!elden_wlan_power_acquire(&identity,&epoch)&&epoch==1);c=active;
        CHECK(c->wlan.regs[0]==0x3c3&&c->wlan.regs[1]==3&&creates==1&&destroys==0);
        CHECK(!elden_wlan_power_check(identity.provider,epoch));
        CHECK(elden_wlan_power_ready(identity.provider,epoch)==-11);
        EldenWcnPmuParam early={"VDDD_AON_0P9",900,820,true,true};
        CHECK(elden_wlan_power_cpr(identity.provider,epoch,&early,1)==-11);
        CHECK(elden_wlan_power_confirm_endpoint(identity.provider,epoch,UINT32_MAX,2)==-19);
        CHECK(elden_wlan_power_confirm_endpoint(identity.provider,epoch,0x110e17cb,1)==-19);
        CHECK(!elden_wlan_power_confirm_endpoint(identity.provider,epoch,0x110e17cb,2));
        CHECK(!elden_wlan_power_ready(identity.provider,epoch));
        unsigned q=c->qmp_calls;
        if(first)CHECK(!bt_power_acquire(c,1));
        CHECK(c->qmp_calls==q&&c->bt);
        CHECK(!elden_wcn_shared_check(&c->shared,0,1));
        CHECK(!bt_power_stop(c,1)&&!bt_power_finish(c,1));
        CHECK(!elden_wlan_power_check(identity.provider,epoch)&&c->wlan.regs[1]==3);
        EldenWcnPmuParam pmu={"VDDD_AON_0P9",900,820,true,true};
        CHECK(!elden_wlan_power_cpr(identity.provider,epoch,&pmu,1));
        CHECK(c->qmp_calls==q+2);unsigned writes=c->wlan.writes;
        CHECK(elden_wlan_power_stop((void *)0x9999,epoch)==-11&&c->wlan.writes==writes);
        CHECK(!elden_wlan_power_stop(identity.provider,epoch)&&c->quiesces==1&&!(c->wlan.regs[1]&1u));
        CHECK(creates==1&&destroys==0&&elden_wlan_power_check(identity.provider,epoch)==-11);
        CHECK(!elden_wlan_power_acquire(&identity,&epoch)&&epoch==2&&c->qmp_calls==q+2);
        CHECK(elden_wlan_power_ready(identity.provider,epoch)==-11);
        __atomic_store_n(&platform_stopping,1,__ATOMIC_RELEASE);
        CHECK(!wlan_shutdown(clock_us+9000000)&&c->quiesces==2);
        CHECK(elden_wlan_power_acquire(&identity,&epoch)==-11);scenarios++;
    }
    for(unsigned kind=0;kind<8;kind++){
        reset();auto id=identity;uint64_t epoch=0xbeef;
        if(kind==0)id.expected_vendor++;if(kind==1)id.expected_device++;if(kind==2)id.rid++;
        if(kind==3)id.sid++;if(kind==4)id.quiesce=nullptr;
        if(kind==5)boot_enable=0;if(kind==6)armed=false;if(kind==7)native_owner_data_status=1;
        CHECK(elden_wlan_power_acquire(&id,&epoch)<0&&epoch==0xbeef&&creates==0);scenarios++;
    }
    for(unsigned fail=0;fail<2;fail++){
        reset();uint64_t epoch=0;CHECK(!elden_wlan_power_acquire(&identity,&epoch));
        quiesce_result=fail?-5:0;quiesce_late=!fail;unsigned writes=active->wlan.writes;
        CHECK(elden_wlan_power_stop(identity.provider,epoch)==(fail?-5:-110));
        CHECK(active->wlan.writes==writes&&(active->wlan.regs[1]&1u)&&!wlan_epoch);
        CHECK(wlan_shutdown(clock_us+9000000)<0&&destroys==0);scenarios++;
    }
    reset();uint64_t epoch=0;map_ok=false;CHECK(elden_wlan_power_acquire(&identity,&epoch)==-12&&creates==1&&destroys==1);scenarios++;
}
static void gpio_cases(){
    for(unsigned kind=0;kind<7;kind++){
        reset();Context c;c.wlan_gpio={&c,wlan_read,wlan_write,delay,false,false};
        if(kind==0)c.wlan.regs[0]=4;if(kind==1)c.wlan.regs[0]=0x800;
        if(kind==2)c.wlan.regs[1]=1;if(kind==3)c.wlan.regs[2]=1;
        if(kind<4)CHECK(elden_wlan_gpio_set(&c.wlan_gpio,false)==-19&&c.wlan.writes==0);
        else{
            c.wlan.regs[0]=kind==4?0x1800:0x2000;
            CHECK(!elden_wlan_gpio_set(&c.wlan_gpio,false));
            CHECK((c.wlan.regs[0]&~0x3ffu)==(kind==4?0x1800u:0x2000u));
            if(kind==5)c.wlan.stuck=true;
            if(kind==6)c.wlan.regs[0]^=0x40;
            CHECK(elden_wlan_gpio_set(&c.wlan_gpio,true)==(kind==5?-110:kind==6?-71:0));
            if(kind>4){unsigned calls=c.wlan.calls;CHECK(elden_wlan_gpio_set(&c.wlan_gpio,false)==-71&&calls==c.wlan.calls);}
        }
        scenarios++;
    }
    unsigned read_count=0;
    for(unsigned at=0;;at++){
        reset();Context c;c.wlan_gpio={&c,wlan_read,wlan_write,delay,false,false};c.wlan.fail_read=at;
        int rc=elden_wlan_gpio_set(&c.wlan_gpio,false);
        if(!rc)rc=elden_wlan_gpio_set(&c.wlan_gpio,true);
        if(!rc)rc=elden_wlan_gpio_set(&c.wlan_gpio,false);
        if(!at){CHECK(!rc);read_count=c.wlan.read_calls;}
        else{
            CHECK(rc==-5);
            if(c.wlan_gpio.held){unsigned writes=c.wlan.writes;CHECK(elden_wlan_gpio_set(&c.wlan_gpio,false)==-71&&writes==c.wlan.writes);}
            scenarios++;
        }
        if(at==read_count)break;
    }
}
#if defined(ELDEN_TEST_QMI)
#include "TestQmiPower.inc"
#endif
#if defined(ELDEN_TEST_ROOT_POWER)
#include "TestPowerCases.inc"
#endif
int main(){
    native_cases();gpio_cases();
#if defined(ELDEN_TEST_QMI)
    qmi_cases();
#endif
#if defined(ELDEN_TEST_ROOT_POWER)
    power_cases();
#endif
    reset();printf("%u native component scenarios, %u checks passed\n",scenarios,checks);
}
