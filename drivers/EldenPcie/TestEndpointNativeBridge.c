/* SPDX-License-Identifier: GPL-2.0-only */
#define pcie_test_create root_test_create
#define pcie_test_read root_test_read
#define pcie_test_write root_test_write
#include "TestNativeBridge.c"
#undef pcie_test_create
#undef pcie_test_read
#undef pcie_test_write
static const uint32_t bar_masks[6]={0xffe00004,0xffffffff,0xffff8000,0,0,0};
static bool probing[6];static unsigned ep_fault;static uint32_t remap_value;
static void (*ep_stop)(void);
void *pcie_test_create(void){
    NativeHardware *h=root_test_create();memset(probing,0,sizeof(probing));ep_fault=0;remap_value=0;ep_stop=NULL;
    REG(&h->model,EldenPcieConfig,0x10)=4;return h;
}
void pcie_ep_fault(unsigned fault){ep_fault=fault;}
void pcie_ep_stop(void (*f)(void)){ep_stop=f;}
int pcie_test_read(void *p,unsigned w,unsigned o,uint32_t *v){
    int rc=root_test_read(p,w,o,v);if(rc)return rc;
    if(w==EldenPcieConfig&&o>=0x10&&o<0x28&&probing[(o-0x10)/4])*v=bar_masks[(o-0x10)/4];
    return 0;
}
int pcie_test_write(void *p,unsigned w,unsigned o,uint32_t v,bool gcc_owned){
    NativeHardware *h=p;
    if(w==EldenPcieConfig&&o==4)CHECK(!(v&5));
    int rc=root_test_write(p,w,o,v,gcc_owned);if(rc)return rc;
    if(w==EldenPcieConfig&&o>=0x10&&o<0x28){
        unsigned i=(o-0x10)/4;CHECK(!(REG(&h->model,EldenPcieConfig,4)&7));
        probing[i]=v==UINT32_MAX;
        if(!probing[i])REG(&h->model,w,o)=(v&bar_masks[i])|(i==0?4:0);
    }
    return 0;
}
int pcie_ep_bar_read(void *p,unsigned off,uint32_t *v){
    NativeHardware *h=p;CHECK((REG(&h->model,EldenPcieConfig,4)&7)==2);
    CHECK(REG(&h->model,EldenPcieConfig,0x10)==0x40400004);
    if(off==0x3278)*v=remap_value;
    else{
        CHECK(off==0x80000&&remap_value==0x40000036);
        *v=ep_fault==1?0x300:0x210;
        if(ep_stop){void (*f)(void)=ep_stop;ep_stop=NULL;f();}
    }
    return 0;
}
int pcie_ep_bar_write(void *p,unsigned off,uint32_t v){
    NativeHardware *h=p;CHECK((REG(&h->model,EldenPcieConfig,4)&7)==2);CHECK(off==0x3278);
    if(ep_fault==2)return -5;
    remap_value=v;return 0;
}
