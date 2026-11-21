/* SPDX-License-Identifier: GPL-2.0-only */
#include "Native.h"
#include "Root.h"
#include "Pins.h"
#include "Power.h"
#include "WlanPower.h"
#include "EldenWifiResources.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern "C" {
void *pcie_test_create(void);void pcie_test_destroy(void *);
void pcie_test_stop_hook(void *,unsigned,void (*)(void));void pcie_test_fail_pin(void *,unsigned);void pcie_test_fault(void *,int);
unsigned pcie_test_calls(void *);int pcie_test_power(void *);
int pcie_test_read(void *,unsigned,unsigned,uint32_t *);int pcie_test_write(void *,unsigned,unsigned,uint32_t,bool);
uint64_t pcie_test_now(void *);void pcie_test_delay(void *,unsigned);
int pcie_test_pin_read(void *,unsigned,uint32_t *);int pcie_test_pin_write(void *,unsigned,uint32_t);
int pcie_test_wlan_read(void *,uint32_t *);
}
static unsigned assertions,cases;
#define CHECK(x) do{assertions++;if(!(x)){fprintf(stderr,"line%d %s\n",__LINE__,#x);exit(1);}}while(0)
using wait_result_t=int;using thread_t=void *;
static void *hw;static void (*queued)(void *,int);static void *queued_arg;
static unsigned root_enabled=1,wlan_enabled=1,full_on=1,selected_gen=3,map_fail=99,map_count,power_calls,terminated;
static bool ready=true;static const void *provider;static uint64_t provided_epoch;
static int (*saved_quiesce)(const void *,uint64_t,uint64_t);
volatile uint32_t sm8750_gcc_vote_owner;
static uint64_t now(void *){return pcie_test_now(hw);}
static void IODelay(unsigned n){pcie_test_delay(hw,n);}
static void IOSleep(unsigned n){pcie_test_delay(hw,n*1000);}
static void delay(void *,unsigned us){pcie_test_delay(hw,us);}
static int elden_recovery_armed(){return ready;}
static int elden_recovery_rpc_ready(){return ready;}
static unsigned elden_recovery_deadline_remaining(){return 300;}
static unsigned elden_charge_policy_ready(){return ready;}
static bool ml_at_interrupt_context(){return false;}
static bool elden_battery_temperature_get(int *t,uint32_t *e,uint32_t *c){*t=2500;*e=1;*c=1;return ready;}
static void log(const char *,...){}
static void *IOMalloc(size_t n){return malloc(n);}
static void IOFree(void *p,size_t){free(p);}
static thread_t current_thread(){return nullptr;}
static void thread_terminate(thread_t){terminated++;}
static void thread_deallocate(thread_t){}
enum {KERN_SUCCESS=0};
static int kernel_thread_start(void (*f)(void *,int),void *arg,thread_t *t){queued=f;queued_arg=arg;*t=(void *)1;return 0;}
static void PE_parse_boot_argn(const char *name,unsigned *v,size_t){
    if(!strcmp(name,"elden-pcie-root"))*v=root_enabled;
    else if(!strcmp(name,"elden-wlan-power"))*v=wlan_enabled;
    else if(!strcmp(name,"elden-pcie-full-on"))*v=full_on;
    else if(!strcmp(name,"elden-pcie-gen"))*v=selected_gen;
    else CHECK(false);
}
extern "C" int elden_wlan_power_acquire(const EldenWlanIdentity *id,uint64_t *epoch){
    CHECK(id->provider&&id->expected_vendor==0x17cb&&id->expected_device==0x110e&&id->rid==0x100&&id->sid==0x1401);
    provider=id->provider;saved_quiesce=id->quiesce;provided_epoch=7;*epoch=7;power_calls++;return pcie_test_power(hw);
}
extern "C" int elden_wlan_power_check(const void *p,uint64_t e){return p==provider&&e==provided_epoch?0:-11;}
extern "C" int elden_wlan_root_power(const void *p,uint64_t e,unsigned g){CHECK(p==provider&&e==7&&g==selected_gen);return 0;}
namespace {
constexpr uint32_t GccOwner=0x50434945;
static unsigned run,stop_requested,stopped;
static EldenPcieNativeStatus terminal;
struct Region {
    unsigned kind=99;uint32_t bytes=0;
    bool map(uint64_t pa,uint32_t length){
        unsigned index=map_count++;if(index==map_fail)return false;
        for(unsigned i=0;i<EldenPcieWindowCount;i++)if(pa==elden_pcie_window_base(i)&&length==elden_pcie_window_bytes(i)){kind=i;bytes=length;return true;}
        if(pa==0xf166000&&length==0x2000){kind=7;bytes=length;return true;}
        if(pa==0xf110000&&length==0x1000){kind=8;bytes=length;return true;}
        CHECK(false);return false;
    }
    int read(uint32_t off,uint32_t *v){
        if(!bytes||off>bytes-4||(off&3))return -14;
        if(kind==7)return pcie_test_pin_read(hw,off,v);
        if(kind==8)return pcie_test_wlan_read(hw,v);
        return pcie_test_read(hw,kind,off,v);
    }
    int write(uint32_t off,uint32_t value){
        if(!bytes||off>bytes-4||(off&3))return -14;
        if(kind==7)return pcie_test_pin_write(hw,off,value);
        CHECK(kind<7);return pcie_test_write(hw,kind,off,value,sm8750_gcc_vote_owner==GccOwner);
    }
};
#include "NativeRuntime.inc"
}
#include "NativeExports.inc"
static void reset(){
    delete active;active=nullptr;if(hw)pcie_test_destroy(hw);hw=pcie_test_create();
    run=stop_requested=stopped=0;terminal={};sm8750_gcc_vote_owner=0;
    queued=nullptr;queued_arg=nullptr;root_enabled=wlan_enabled=full_on=1;selected_gen=3;map_fail=99;
    map_count=power_calls=terminated=0;ready=true;provider=nullptr;provided_epoch=0;saved_quiesce=nullptr;
}
static void execute(){CHECK(queued);auto f=queued;auto a=queued_arg;queued=nullptr;f(a,0);CHECK(terminated==1);}
int main(){
    for(unsigned gen=1;gen<=3;gen++){
        reset();selected_gen=gen;elden_pcie_native_start();CHECK(run==1);EldenPcieNativeStatus report={};
        CHECK(elden_pcie_native_status(&report)==-11);execute();CHECK(!elden_pcie_native_status(&report));
        CHECK(!report.error&&report.state==EldenPcieRootEndpointVisible&&report.epoch==7&&report.endpoint_id==0x110e17cb);
        CHECK(map_count==9&&power_calls==1&&!sm8750_gcc_vote_owner);
        CHECK(saved_quiesce);provided_epoch=0;
        CHECK(!saved_quiesce(provider,7,now(nullptr)+9000000));
        CHECK(!elden_pcie_native_status(&report)&&report.stopped&&!report.perst_high);
        auto before=map_count;elden_pcie_native_start();CHECK(!queued&&map_count==before);cases++;
    }
    for(unsigned map=0;map<9;map++){
        reset();map_fail=map;elden_pcie_native_start();execute();CHECK(run==2&&terminal.error==-12&&!power_calls);cases++;
    }
    reset();root_enabled=0;elden_pcie_native_start();CHECK(!queued&&!map_count);cases++;
    reset();full_on=0;elden_pcie_native_start();CHECK(!queued&&!map_count);cases++;
    reset();elden_pcie_native_start();elden_pcie_native_stop_begin();execute();CHECK(terminal.error==-11&&!map_count&&!power_calls);cases++;
    reset();ready=false;elden_pcie_native_start();execute();CHECK(terminal.error==-11&&!map_count);cases++;
    reset();sm8750_gcc_vote_owner=0x1234;elden_pcie_native_start();execute();CHECK(terminal.error==-16&&sm8750_gcc_vote_owner==0x1234);cases++;
    reset();pcie_test_stop_hook(hw,30,elden_pcie_native_stop_begin);elden_pcie_native_start();execute();CHECK(terminal.error==-11&&terminal.gcc_held);cases++;
    reset();pcie_test_fail_pin(hw,6);elden_pcie_native_start();execute();CHECK(terminal.error&&terminal.stage==EldenPcieStagePins&&!power_calls);cases++;
    reset();elden_pcie_native_start();execute();provided_epoch=0;run=1;
    CHECK(saved_quiesce(provider,7,now(nullptr)+1000)==-110&&!stopped);run=2;cases++;
    delete active;active=nullptr;pcie_test_destroy(hw);hw=nullptr;
    printf("%u native root scenarios / %u checks passed\n",cases,assertions);return 0;
}
