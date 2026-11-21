/* SPDX-License-Identifier: GPL-2.0-only */
/* Ordering follows Sheng WifiProbe bringUp / Linux qmp_pcie_power_on;
 * register data is the exact TB322FC stock sequence, checked against6f97250e. */
#include "Phy.h"
#include <stddef.h>
#include "PhySequence.inc"
enum {Count=sizeof(elden_pcie_phy_sequence)/sizeof(elden_pcie_phy_sequence[0])};
_Static_assert(Count==127,"Reviewed stock sequence changed");

static int failed(EldenPciePhy *p,int rc){
    p->error=rc;p->state=p->state==EldenPciePhyProgramming?EldenPciePhyHeld:EldenPciePhyRefused;return rc;
}
static int read_reg(EldenPciePhy *p,uint16_t off,uint32_t *v){
    int rc=p->io.admit(p->io.context,p->epoch);if(rc)return rc;
    rc=p->io.read(p->io.context,off,v);return rc?rc:*v==UINT32_MAX?-5:0;
}
static int write_index(EldenPciePhy *p,unsigned index){
    const EldenPciePhyWrite *w=&elden_pcie_phy_sequence[index];p->last_index=index;
    int rc=p->io.admit(p->io.context,p->epoch);if(rc)return rc;
    /* Even the first failed write may have reached the PHY. */
    p->state=EldenPciePhyProgramming;
    rc=p->io.write(p->io.context,w->offset,w->value);if(rc)return rc;
    p->writes++;
    if(w->delay_us)p->io.delay_us(p->io.context,w->delay_us);
    return 0;
}
int elden_pcie_phy_start(EldenPciePhy *p,uint64_t epoch){
    if(!p||!epoch||!p->io.admit||!p->io.read||!p->io.write||!p->io.pipe_to_phy||!p->io.now_us||!p->io.delay_us)return -22;
    if(p->state!=EldenPciePhyIdle)return -11;
    p->epoch=epoch;uint32_t reset=0,start=0;int rc=read_reg(p,0x400,&reset);
    if(!rc)rc=read_reg(p,0x444,&start);
    if(rc)return failed(p,rc);
    if(!(reset&1u)||(start&3u))return failed(p,-19);
    for(unsigned i=0;i<Count-2;i++)if((rc=write_index(p,i)))return failed(p,rc);
    /* Sheng switches PIPE from TCXO to the PHY before its reset is released.
     * The owner keeps PERST# low throughout this transaction. */
    if((rc=p->io.admit(p->io.context,epoch))||(rc=p->io.pipe_to_phy(p->io.context)))return failed(p,rc);
    if((rc=write_index(p,Count-2))||(rc=write_index(p,Count-1)))return failed(p,rc);
    if((rc=read_reg(p,0x400,&reset))||(rc=read_reg(p,0x444,&start)))return failed(p,rc);
    if((reset&1u)||(start&3u)!=3u)return failed(p,-71);
    uint64_t began=p->io.now_us(p->io.context);
    for(unsigned n=0;n<1001;n++){
        uint64_t now=p->io.now_us(p->io.context);
        if(now<began||now-began>=10000)return failed(p,-110);
        if((rc=read_reg(p,0x414,&p->status)))return failed(p,rc);
        p->polls++;
        if(!(p->status&0x40u)){
            now=p->io.now_us(p->io.context);
            if(now<began||now-began>=10000)return failed(p,-110);
            p->state=EldenPciePhyReady;return 0;
        }
        p->io.delay_us(p->io.context,10);
    }
    return failed(p,-110); /* also bounds a nonadvancing counter */
}
