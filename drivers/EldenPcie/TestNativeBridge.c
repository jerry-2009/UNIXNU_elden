/* SPDX-License-Identifier: GPL-2.0-only */
#define main root_fixture_main
#include "TestRoot.c"
#undef main
typedef struct {
    Model model;EldenPcieRoot unused;
    uint32_t pins[0x2000/4];
    unsigned pin_calls,fail_pin,stop_at;
    void (*stop_hook)(void);
} NativeHardware;
void *pcie_test_create(void){
    NativeHardware *h=calloc(1,sizeof(*h));CHECK(h);setup(&h->model,&h->unused);
    h->pins[0]=0x201;h->pins[1]=3;h->pins[0x1000/4]=7;return h;
}
void pcie_test_destroy(void *p){NativeHardware *h=p;dispose(&h->model);free(h);}
void pcie_test_stop_hook(void *p,unsigned at,void (*hook)(void)){NativeHardware *h=p;h->stop_at=at;h->stop_hook=hook;}
void pcie_test_fail_pin(void *p,unsigned at){((NativeHardware *)p)->fail_pin=at;}
void pcie_test_fault(void *p,int fault){((NativeHardware *)p)->model.fault=fault;}
unsigned pcie_test_calls(void *p){return ((NativeHardware *)p)->model.calls;}
int pcie_test_power(void *p){NativeHardware *h=p;CHECK(!h->model.perst_high);h->model.powered=true;return 0;}
static void hook(NativeHardware *h){if(h->stop_hook&&h->model.calls>=h->stop_at){void (*f)(void)=h->stop_hook;h->stop_hook=NULL;f();}}
int pcie_test_read(void *p,unsigned window,unsigned offset,uint32_t *v){
    NativeHardware *h=p;int rc=read_model(&h->model,window,offset,v);hook(h);return rc;
}
int pcie_test_write(void *p,unsigned window,unsigned offset,uint32_t value,bool gcc_owned){
    NativeHardware *h=p;h->model.gate=gcc_owned;int rc=write_model(&h->model,window,offset,value);hook(h);return rc;
}
uint64_t pcie_test_now(void *p){return ((NativeHardware *)p)->model.now;}
void pcie_test_delay(void *p,unsigned us){delay_model(&((NativeHardware *)p)->model,us);}
int pcie_test_pin_read(void *p,unsigned offset,uint32_t *v){
    NativeHardware *h=p;if(++h->pin_calls==h->fail_pin)return -5;
    CHECK(offset<0x2000&&!(offset&3u));*v=h->pins[offset/4];return 0;
}
int pcie_test_pin_write(void *p,unsigned offset,uint32_t v){
    NativeHardware *h=p;if(++h->pin_calls==h->fail_pin)return -5;
    CHECK(offset==0||offset==4||offset==0x1000);h->pins[offset/4]=v;
    if(h->pins[0]&0x200u){
        h->pins[1]=(h->pins[1]&~1u)|((h->pins[1]>>1)&1u);
        bool high=(h->pins[1]&1u)!=0;
        if(high!=h->model.perst_high){int rc=pins_model(&h->model,high);CHECK(!rc);}
    }
    return 0;
}
int pcie_test_wlan_read(void *p,uint32_t *v){*v=((NativeHardware *)p)->model.powered?1:0;return 0;}
