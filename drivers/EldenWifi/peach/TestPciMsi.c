/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
#define PCI_IRQ_MSI 2
struct pci_dev {unsigned nvec;int msi_enabled;u32 irq;};
struct msi_desc {struct {u32 address_lo,address_hi,data;} msg;struct {struct {int is_64;} msi_attrib;} pci;};
struct nw_board {unsigned msi_cap;int irq_base;int(*cfg_read)(int,int,u32 *);int(*cfg_write)(int,int,u32);int(*msi_target)(u32 *,u32 *,u32 *);};
static struct msi_desc g_msi[32];
static u32 cfg[64],target_lo,target_hi,target_data;
static unsigned calls,fail_at,logs,checks,cases;
static int corrupt;
static struct pci_dev dev;
#define CHECK(x) do{++checks;assert(x);}while(0)
static void lx_log(int level,const char *text,int error){assert(level==3&&text&&error);logs++;}
static int read_cfg(int off,int size,u32 *v){
    assert(off>=0x40&&off<=0xfc&&(size==2||size==4));
    *v=size==2?(cfg[off/4]>>((off&2)*8))&0xffff:cfg[off/4];
    ++calls;if(corrupt==1&&calls>8&&off==0x40)*v^=1u<<20;
    if(corrupt==2&&calls==3)*v=0;
    return calls==fail_at?-123:0;
}
static int write_cfg(int off,int size,u32 v){
    assert(off>=0x40&&off<=0xfc&&(size==2||size==4));
    if(++calls==fail_at)return -123;
    if(size==4)cfg[off/4]=v;else {unsigned shift=(off&2)*8;cfg[off/4]=(cfg[off/4]&~(0xffffu<<shift))|(v<<shift);}
    return 0;
}
static int target(u32 *lo,u32 *hi,u32 *data){*lo=target_lo;*hi=target_hi;*data=target_data;return ++calls==fail_at?-123:0;}
static struct nw_board board={0x40,1000,read_cfg,write_cfg,target};
static const struct nw_board *nw_board=&board;
// @PCI_MSI_FUNCTIONS@
static void reset(int wide,int mask){
    ++cases;memset(&dev,0,sizeof dev);memset(g_msi,0,sizeof g_msi);memset(cfg,0,sizeof cfg);
    cfg[0x40/4]=5|0x7000|(5u<<17)|(wide?1u<<23:0)|(mask?1u<<24:0);
    cfg[(0x40+(wide?12:8))/4]=0xabcd0000;cfg[(0x40+(wide?16:12))/4]=~0u;
    target_lo=0x10000000;target_hi=target_data=0;calls=fail_at=logs=0;corrupt=0;
    board.irq_base=1000;
}
int main(void){
#if ORIGINAL
    reset(1,0);fail_at=3;CHECK(pci_alloc_irq_vectors(&dev,1,32,2)==32&&dev.msi_enabled);
    CHECK(cfg[0x44/4]!=target_lo); // old code silently accepts a refused target write
    reset(1,0);CHECK(pci_alloc_irq_vectors(&dev,1,3,2)==3&&((cfg[0x40/4]>>20)&7)==2);
    pci_free_irq_vectors(&dev);CHECK(!dev.msi_enabled&&(cfg[0x40/4]&(1u<<16))); // hardware still enabled
    printf("original false-success, vector-count mismatch and free-without-disable reproduced\n");
#else
    reset(1,1);CHECK(pci_alloc_irq_vectors(&dev,1,32,2)==32);unsigned steps=calls;
    CHECK(dev.msi_enabled&&dev.nvec==32&&dev.irq==1000&&g_msi[31].msg.data==31);
    CHECK(cfg[0x4c/4]==0xabcd0000&&cfg[0x50/4]==0); // data is a 16-bit field
    pci_free_irq_vectors(&dev);CHECK(!dev.msi_enabled&&!dev.nvec&&!(cfg[0x40/4]&(1u<<16)));
    for(unsigned i=1;i<=steps;i++){
        reset(1,1);fail_at=i;CHECK(pci_alloc_irq_vectors(&dev,1,32,2)==-123);
        CHECK(!dev.nvec&&!dev.msi_enabled&&g_msi[0].msg.address_lo==0);
    }
    for(unsigned i=1;i<=3;i++){
        reset(1,0);CHECK(pci_alloc_irq_vectors(&dev,1,32,2)==32);calls=0;fail_at=i;
        pci_free_irq_vectors(&dev);CHECK(dev.msi_enabled&&dev.nvec==32&&logs==1);
    }
    reset(1,1);CHECK(pci_alloc_irq_vectors(&dev,1,3,2)==2&&((cfg[0x40/4]>>20)&7)==1&&cfg[0x50/4]==~3u);
    reset(1,0);CHECK(pci_alloc_irq_vectors(&dev,3,3,2)==-ENOSPC&&!dev.msi_enabled);
    reset(0,0);CHECK(pci_alloc_irq_vectors(&dev,1,8,2)==8&&g_msi[0].pci.msi_attrib.is_64==0);
    reset(0,0);target_hi=1;CHECK(pci_alloc_irq_vectors(&dev,1,32,2)==-ERANGE);
    reset(1,0);target_data=1;CHECK(pci_alloc_irq_vectors(&dev,1,32,2)==-ERANGE);
    reset(1,0);cfg[0x40/4]|=1u<<16;CHECK(pci_alloc_irq_vectors(&dev,1,32,2)==-EBUSY);
    reset(1,0);cfg[0x40/4]|=0x7e;CHECK(pci_alloc_irq_vectors(&dev,1,32,2)==-EINVAL);
    reset(1,0);cfg[0x40/4]&=~(7u<<17);CHECK(pci_alloc_irq_vectors(&dev,2,32,2)==-ENOSPC);
    reset(1,0);CHECK(pci_alloc_irq_vectors(&dev,0,32,2)==-EINVAL);CHECK(pci_alloc_irq_vectors(&dev,1,32,4)==-ENOSPC);
    reset(1,1);corrupt=1;CHECK(pci_alloc_irq_vectors(&dev,1,32,2)==-EIO&&!dev.msi_enabled);
    reset(1,0);CHECK(pci_alloc_irq_vectors(&dev,1,32,2)==32);calls=0;corrupt=2;
    pci_free_irq_vectors(&dev);CHECK(dev.msi_enabled&&dev.nvec==32&&logs==1);
    reset(1,0);board.irq_base=-1;CHECK(pci_alloc_irq_vectors(&dev,1,32,2)==-EINVAL&&calls==0);
    printf("%u actual MSI config scenarios / %u checks passed; PCI callbacks modeled\n",cases,checks);
#endif
}
