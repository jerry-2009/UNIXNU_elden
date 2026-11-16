/* SPDX-License-Identifier: GPL-2.0-only */
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
typedef uint32_t u32;typedef uint16_t u16;typedef uint8_t u8;
#define PCI_IRQ_MSI 2
struct device {const char *name;uint64_t dma_mask;};
struct pci_bus {unsigned number;};
struct pci_dev {u16 vendor,device,subsystem_vendor,subsystem_device;struct device dev;unsigned msi_cap,nvec;struct pci_bus *bus;u32 irq;int msi_enabled;};
struct pci_device_id {unsigned vendor,device;};
struct pci_driver {const struct pci_device_id *id_table;int(*probe)(struct pci_dev *,const struct pci_device_id *);void(*remove)(struct pci_dev *);};
struct msi_desc {struct {u32 address_lo,address_hi,data;} msg;struct {struct {u8 is_64;} msi_attrib;} pci;};
struct nw_board {u16 device_id,msi_cap;int irq_base;int(*cfg_read)(int,int,u32 *);int(*cfg_write)(int,int,u32);int(*msi_target)(u32 *,u32 *,u32 *);};
static struct pci_driver *g_drv;static struct pci_dev g_dev;static struct msi_desc g_msi[32];static struct pci_bus g_bus={1};
static u32 sub_ctl_after,config[64];static unsigned calls,fail_at,checks,cases,binds,probes,removes,unbinds,masters;
static int bind_error,probe_error,unbind_error,master_error;static bool bound;
static char order[32];static unsigned events;
#define CHECK(x) do{++checks;assert(x);}while(0)
static void event(char e){assert(events<sizeof(order)-1);order[events++]=e;}
static int io(){return ++calls==fail_at?-123:0;}
static void device_initialize(struct device *d){assert(d==&g_dev.dev);}
static void lx_log(int level,const char *fmt,...){(void)level;(void)fmt;}
static unsigned offset(int off){return ((u32)off&0x80000000u)?0x48:(unsigned)off;}
static int read_config(int off,int size,u32 *v){int rc=io();if(rc)return rc;unsigned o=offset(off);assert(o<256);*v=config[o/4];if(size==2)*v=(*v>>((o&2)*8))&0xffff;return 0;}
static int write_config(int off,int size,u32 v){int rc=io();if(rc)return rc;unsigned o=offset(off);assert(o<256);if(size==2){unsigned shift=(o&2)*8;config[o/4]=(config[o/4]&~(0xffffu<<shift))|(v<<shift);}else config[o/4]=v;return 0;}
static int target(u32 *lo,u32 *hi,u32 *data){*lo=0x10000000;*hi=0;*data=0;return 0;}
static struct nw_board board={0x110e,0x80,1000,read_config,write_config,target};static const struct nw_board *nw_board=&board;
int elden_wifi_runtime_bind(void *p){CHECK(p==&g_dev.dev);event('B');binds++;if(bind_error)return bind_error;CHECK(!bound);bound=true;return 0;}
int elden_wifi_runtime_unbind(void *p){CHECK(p==&g_dev.dev&&bound);event('U');unbinds++;if(unbind_error)return unbind_error;bound=false;return 0;}
int elden_wifi_runtime_enable_master(void){CHECK(bound);event('M');masters++;return master_error;}
// @MSI@
// @LIFECYCLE@
static int probe(struct pci_dev *d,const struct pci_device_id *id){CHECK(bound&&d==&g_dev&&id->device==0x110e);event('P');probes++;if(probe_error)return probe_error;int rc=pci_alloc_irq_vectors(d,1,32,2);return rc<0?rc:0;}
static void remove_device(struct pci_dev *d){CHECK(bound&&d==&g_dev);event('R');removes++;pci_free_irq_vectors(d);}
static const struct pci_device_id ids[]={{0x17cb,0x110e},{0,0}};
static struct pci_driver driver={ids,probe,remove_device};
static void reset(void){
    cases++;g_drv=0;memset(&g_dev,0,sizeof(g_dev));memset(g_msi,0,sizeof(g_msi));memset(config,0,sizeof(config));memset(order,0,sizeof(order));
    config[0x2c/4]=0x123417cb;config[0x48/4]=0x7000;config[0x80/4]=5|(5u<<17)|(1u<<23);
    calls=fail_at=binds=probes=removes=unbinds=masters=events=0;bind_error=probe_error=unbind_error=master_error=0;bound=false;
}
int main(void){
    reset();CHECK(!pci_register_driver(&driver));unsigned count=calls;
    CHECK(!strcmp(order,"BPM")&&g_drv==&driver&&bound&&g_dev.nvec==32);
    pci_unregister_driver(&driver);CHECK(!strcmp(order,"BPMRU")&&!g_drv&&!bound&&!g_dev.msi_enabled);
    pci_unregister_driver(&driver);CHECK(removes==1&&unbinds==1);
    for(unsigned n=1;n<=count;n++){
        reset();fail_at=n;CHECK(pci_register_driver(&driver)==-123);CHECK(!g_drv&&!bound);
        if(n<=4)CHECK(!binds&&!probes&&!masters);else CHECK(binds==1&&probes==1&&unbinds==1);
    }
    reset();bind_error=-19;CHECK(pci_register_driver(&driver)==-19&&!strcmp(order,"B")&&!g_drv);
    reset();probe_error=-5;CHECK(pci_register_driver(&driver)==-5&&!strcmp(order,"BPU")&&!g_drv&&!bound);
    reset();master_error=-95;CHECK(pci_register_driver(&driver)==-95&&!strcmp(order,"BPMU")&&!g_drv&&!bound&&!g_dev.msi_enabled);
    reset();probe_error=-5;unbind_error=-11;CHECK(pci_register_driver(&driver)==-5&&bound&&!g_drv&&unbinds==1);
    reset();CHECK(!pci_register_driver(&driver));unbind_error=-11;pci_unregister_driver(&driver);CHECK(!g_drv&&bound&&removes==1&&unbinds==1);
    printf("%u actual PCI lifecycle scenarios / %u checks passed; native binding/master callbacks modeled\n",cases,checks);
}
