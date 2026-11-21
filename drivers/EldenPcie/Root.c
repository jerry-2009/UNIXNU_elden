/* SPDX-License-Identifier: GPL-2.0-only */
/* Control order follows Sheng WifiProbe bringUp. Register semantics/constants
 * are checked against TB322FC Linux6f97250e and the stock FDT, not SM8550. */
#include "Root.h"
#include <stddef.h>
static const uint64_t bases[]={0x00100000,0x0f204000,0x01c00000,0x01c06000,0x40000000,0x40001000,0x40100000};
static const uint32_t lengths[]={0x80000,0x1000,0x3000,0x2000,0x1000,0x1000,0x1000};
uint64_t elden_pcie_window_base(unsigned w){return w<EldenPcieWindowCount?bases[w]:0;}
uint32_t elden_pcie_window_bytes(unsigned w){return w<EldenPcieWindowCount?lengths[w]:0;}
typedef struct {uint32_t halt;bool hwcg,skip;} Branch;
static const Branch branches[]={
    {0x6b020,true,false},{0x6b030,true,true},{0x6b040,true,false},{0x6b044,false,false},
    {0x6b054,false,true},{0x6b01c,false,false},{0x10058,true,false},{0x6b018,true,false},
    {0x10068,true,true},{0x1007c,true,true},{0x10050,true,false},{0x6b064,false,false}
};
enum {Vote8=0x7f,Vote0=(1u<<11)|(1u<<12)|(1u<<19)|(1u<<20)|(1u<<22),RcgMask=0x10371f};
static int failed(EldenPcieRoot *r,int rc){r->error=rc;r->state=r->controls_started?EldenPcieRootHeld:EldenPcieRootRefused;return rc;}
static int admit(EldenPcieRoot *r){return r->io.admit(r->io.context,r->epoch);}
static int access_ok(EldenPcieRoot *r,unsigned w,uint32_t o){
    if(w>=EldenPcieWindowCount||(o&3u)||o>lengths[w]-4)return -22;
    if(w!=EldenPcieGcc&&w!=EldenPcieTcsr&&!r->clocks_ready)return -11;
    return admit(r);
}
static int rd(EldenPcieRoot *r,unsigned w,uint32_t o,uint32_t *v,bool allow_ff){
    int rc=access_ok(r,w,o);if(rc)return rc;
    r->last_window=w;r->last_offset=o;*v=UINT32_MAX;
    rc=r->io.read(r->io.context,w,o,v);r->last_value=rc?0:*v;
    return rc?rc:(!allow_ff&&*v==UINT32_MAX)?-5:0;
}
static int wr(EldenPcieRoot *r,unsigned w,uint32_t o,uint32_t v){
    int rc=access_ok(r,w,o);if(rc)return rc;
    if(w==EldenPcieGcc&&!r->gcc_held)return -11;
    r->controls_started=true;r->last_window=w;r->last_offset=o;r->last_value=v;
    rc=r->io.write(r->io.context,w,o,v);if(!rc)r->writes++;return rc;
}
static int update(EldenPcieRoot *r,unsigned w,uint32_t o,uint32_t mask,uint32_t bits){
    uint32_t v=0;int rc=rd(r,w,o,&v,false);if(rc)return rc;
    rc=wr(r,w,o,(v&~mask)|(bits&mask));if(rc)return rc;
    rc=rd(r,w,o,&v,false);return rc?rc:(v&mask)!=(bits&mask)?-71:0;
}
static int wait_bits(EldenPcieRoot *r,unsigned w,uint32_t o,uint32_t mask,uint32_t bits,unsigned us){
    uint64_t began=r->io.now_us(r->io.context);
    for(unsigned n=0;n<=us/10;n++){
        uint64_t now=r->io.now_us(r->io.context);if(now<began||now-began>=us)return -110;
        uint32_t v=0;int rc=rd(r,w,o,&v,false);if(rc)return rc;
        if((v&mask)==bits){now=r->io.now_us(r->io.context);return now<began||now-began>=us?-110:0;}
        r->io.delay_us(r->io.context,10);
    }
    return -110;
}
static int clock_gate(EldenPcieRoot *r,bool take){
    int rc=r->io.gcc_gate(r->io.context,take);if(!rc)r->gcc_held=take;return rc;
}
static int rcg(EldenPcieRoot *r,uint32_t cmd,uint32_t cfg){
    uint32_t v=0;int rc=rd(r,EldenPcieGcc,cmd,&v,false);if(rc)return rc;if(v&1u)return -16;
    rc=update(r,EldenPcieGcc,cmd+4,RcgMask,cfg);if(rc)return rc;
    /* UPDATE may remain pending until branch votes, as in the shared RCG path. */
    return wr(r,EldenPcieGcc,cmd,v|1u);
}
static int reset_block(EldenPcieRoot *r,uint32_t offset){
    int rc=update(r,EldenPcieGcc,offset,1,1);if(rc)return rc;
    uint64_t before=r->io.now_us(r->io.context);
    r->io.delay_us(r->io.context,1000);
    uint64_t after=r->io.now_us(r->io.context);if(after<before||after-before<1000)return -110;
    rc=update(r,EldenPcieGcc,offset,1,0);if(rc)return rc;
    before=r->io.now_us(r->io.context);r->io.delay_us(r->io.context,1000);
    after=r->io.now_us(r->io.context);return after<before||after-before<1000?-110:0;
}
static int clocks(EldenPcieRoot *r){
    int rc=clock_gate(r,true);if(rc)return rc;
    /* gdsc_init: disable HW trigger/SW override, exact per-domain wait fields. */
    if((rc=update(r,EldenPcieGcc,0x6b004,0x00fff006,0x0022f000))||
       (rc=update(r,EldenPcieGcc,0x6c000,0x00fff006,0x00222000))||
       (rc=update(r,EldenPcieGcc,0x5214c,5,0)))return rc;
    /* POLL_CFG_GDSCR is set on BOTH SM8750 domains: use +4/bit16, not bit31. */
    if((rc=wait_bits(r,EldenPcieGcc,0x6b008,1u<<16,1u<<16,2000))||
       (rc=wait_bits(r,EldenPcieGcc,0x6c004,1u<<16,1u<<16,2000))||
       (rc=update(r,EldenPcieGcc,0x6b008,1u<<11,1u<<11))||
       (rc=update(r,EldenPcieGcc,0x6c004,1u<<11,1u<<11)))return rc;
    if((rc=rcg(r,0x6b084,1))||(rc=rcg(r,0x6b068,r->max_gen==3?0x605:1))||
       (rc=update(r,EldenPcieGcc,0x6b080,3,2))||
       (rc=update(r,EldenPcieGcc,0x52008,Vote8,Vote8))||
       (rc=update(r,EldenPcieGcc,0x52000,Vote0,Vote0))||
       (rc=update(r,EldenPcieTcsr,8,1,1)))return rc;
    r->io.delay_us(r->io.context,200);
    if((rc=wait_bits(r,EldenPcieGcc,0x6b084,1,0,1000))||(rc=wait_bits(r,EldenPcieGcc,0x6b068,1,0,1000)))return rc;
    for(unsigned i=0;i<sizeof(branches)/sizeof(branches[0]);i++){
        uint32_t v=0;rc=rd(r,EldenPcieGcc,branches[i].halt,&v,false);if(rc)return rc;
        if(branches[i].skip||(branches[i].hwcg&&(v&2u)))continue;
        if((rc=wait_bits(r,EldenPcieGcc,branches[i].halt,1u<<31,0,1000)))return rc;
    }
    if((rc=reset_block(r,0x6b000))||(rc=reset_block(r,0x6c01c)))return rc;
    rc=clock_gate(r,false);if(!rc)r->clocks_ready=true;return rc;
}
static int parf(EldenPcieRoot *r){
    const uint32_t writes[][2]={{0x1000,4},{0x350,0x40000000},{0x354,0},{0x634,0x40001000},{0x638,0},{0x358,0},{0x35c,0x80000000}};
    int rc;
    for(unsigned i=0;i<sizeof(writes)/sizeof(writes[0]);i++)if((rc=update(r,EldenPcieParf,writes[i][0],UINT32_MAX,writes[i][1])))return rc;
    if((rc=update(r,EldenPcieParf,0x40,1,0))||(rc=update(r,EldenPcieParf,0,1u<<29,0))||
       (rc=update(r,EldenPcieParf,0x174,1u<<4,1u<<4))||(rc=update(r,EldenPcieParf,0x20,1u<<5,0))||
       (rc=update(r,EldenPcieParf,0x1a8,1u<<31,1u<<31)))return rc;
    return 0;
}
static int phy_admit(void *p,uint64_t epoch){EldenPcieRoot *r=p;return !r->clocks_ready||r->perst_high||r->epoch!=epoch?-11:admit(r);}
static int phy_read(void *p,uint16_t o,uint32_t *v){return rd(p,EldenPciePhyWindow,o,v,false);}
static int phy_write(void *p,uint16_t o,uint32_t v){return wr(p,EldenPciePhyWindow,o,v);}
static uint64_t phy_now(void *p){EldenPcieRoot *r=p;return r->io.now_us(r->io.context);}
static void phy_delay(void *p,unsigned n){EldenPcieRoot *r=p;r->io.delay_us(r->io.context,n);}
static int phy_pipe(void *p){
    EldenPcieRoot *r=p;int rc=clock_gate(r,true);if(rc)return rc;
    rc=update(r,EldenPcieGcc,0x6b080,3,0);if(rc)return rc;return clock_gate(r,false);
}
static uint8_t bdf_hash(uint16_t bdf){
    uint8_t crc=0,bytes[2]={(uint8_t)(bdf>>8),(uint8_t)bdf};
    for(unsigned i=0;i<2;i++){crc^=bytes[i];for(unsigned bit=0;bit<8;bit++)crc=(uint8_t)((crc<<1)^((crc&0x80)?7:0));}
    return crc;
}
static int sid(EldenPcieRoot *r){
    int rc;
    /* This board has only RC0000/EP0100 on its exclusively owned PCIe0. */
    for(unsigned i=0;i<256;i++){
        uint32_t v=0;if((rc=wr(r,EldenPcieParf,0x2000+4*i,0))||
           (rc=rd(r,EldenPcieParf,0x2000+4*i,&v,false)))return rc;
        if(v)return -71;
    }
    if((rc=update(r,EldenPcieParf,0x2c00,1,0)))return rc;
    return update(r,EldenPcieParf,0x2000+4u*bdf_hash(0x100),UINT32_MAX,0x01000100);
}
static int root_config(EldenPcieRoot *r){
    int rc=rd(r,EldenPcieDbi,0,&r->root_id,false);if(rc)return rc;
    if(r->root_id!=0x011c17cb)return -19;
    uint32_t cap=0;rc=rd(r,EldenPcieDbi,0x34,&cap,false);if(rc)return rc;cap&=0xff;
    uint64_t seen=0;
    for(unsigned n=0;cap&&n<48;n++){
        if(cap<0x40||(cap&3u)||cap>0xfc||(seen&(1ull<<(cap/4))))return -71;
        seen|=1ull<<(cap/4);uint32_t value=0;
        if((rc=rd(r,EldenPcieDbi,cap,&value,false)))return rc;
        if((value&255u)==0x10){if(r->root_pcie_cap)return -71;r->root_pcie_cap=cap;}
        cap=(value>>8)&255u;
    }
    if(cap||!r->root_pcie_cap||r->root_pcie_cap>0xcc)return -19;
    uint32_t cmd=0,ctl2=0;
    if((rc=rd(r,EldenPcieDbi,4,&cmd,false))||(rc=wr(r,EldenPcieDbi,4,(cmd&0xffffu)|6u))||
       (rc=wait_bits(r,EldenPcieDbi,4,6,6,1000))||
       (rc=update(r,EldenPcieDbi,0x18,UINT32_MAX,0x00010100))||
       (rc=update(r,EldenPcieDbi,0xb40,UINT32_MAX,20))||
       (rc=rd(r,EldenPcieDbi,r->root_pcie_cap+0x30,&ctl2,false))||
       (rc=wr(r,EldenPcieDbi,r->root_pcie_cap+0x30,(ctl2&0xfff0u)|r->max_gen)))return rc;
    return wait_bits(r,EldenPcieDbi,r->root_pcie_cap+0x30,15,r->max_gen,1000);
}
static int release_perst(EldenPcieRoot *r){
    for(unsigned n=0;n<101;n++){
        uint64_t now=r->io.now_us(r->io.context);if(now<r->perst_low_us)return -110;
        if(now-r->perst_low_us>=100000){int rc=admit(r);if(rc)return rc;rc=r->io.pins(r->io.context,true);if(!rc)r->perst_high=true;return rc;}
        int rc=admit(r);if(rc)return rc;r->io.delay_us(r->io.context,1000);
    }
    return -110;
}
static int link_up(EldenPcieRoot *r){
    int rc=update(r,EldenPcieParf,0x1b0,1u<<8,1u<<8);if(rc)return rc;
    uint64_t began=r->io.now_us(r->io.context);
    for(unsigned n=0;n<1000;n++){
        uint64_t now=r->io.now_us(r->io.context);if(now<began||now-began>=1000000)return -110;
        uint32_t d0=0,d1=0;
        if((rc=rd(r,EldenPcieDbi,0x728,&d0,false))||(rc=rd(r,EldenPcieDbi,0x72c,&d1,false)))return rc;
        if((d0&63u)==0x11&&(d1&16u)){
            if((rc=rd(r,EldenPcieDbi,r->root_pcie_cap+0x10,&r->link_status,false)))return rc;
            unsigned speed=(r->link_status>>16)&15u,width=(r->link_status>>20)&63u;
            if(speed&&speed<=r->max_gen&&width&&width<=2){now=r->io.now_us(r->io.context);return now<began||now-began>=1000000?-110:0;}
        }
        r->io.delay_us(r->io.context,1000);
    }
    return -110;
}
static int config_window(EldenPcieRoot *r){
    /* One owned outbound CFG0 region; no BAR/MEM/DMA mappings yet. */
    const uint32_t writes[][2]={{4,0},{8,0x40100000},{12,0},{16,0x40100fff},{20,0x01000000},{24,0},{32,0},{0,4},{4,0x80000000}};
    int rc;for(unsigned i=0;i<sizeof(writes)/sizeof(writes[0]);i++)if((rc=wr(r,EldenPcieAtu,writes[i][0],writes[i][1])))return rc;
    if((rc=wait_bits(r,EldenPcieAtu,4,1u<<31,1u<<31,1000)))return rc;
    uint64_t began=r->io.now_us(r->io.context);
    for(unsigned n=0;n<1000;n++){
        uint64_t now=r->io.now_us(r->io.context);if(now<began||now-began>=1000000)return -110;
        if((rc=rd(r,EldenPcieConfig,0,&r->endpoint_id,true)))return rc;
        if(r->endpoint_id!=UINT32_MAX){
            now=r->io.now_us(r->io.context);if(now<began||now-began>=1000000)return -110;
            if(r->endpoint_id!=0x110e17cb)return -19;
            uint32_t cmd=0;
            if((rc=rd(r,EldenPcieConfig,4,&cmd,false))||
               (rc=wr(r,EldenPcieConfig,4,(cmd&0xffffu)&~7u)))return rc;
            return wait_bits(r,EldenPcieConfig,4,7,0,1000);
        }
        r->io.delay_us(r->io.context,1000);
    }
    return -110;
}
int elden_pcie_root_start(EldenPcieRoot *r,unsigned max_gen){
    if(!r||max_gen<1||max_gen>3||!r->io.admit||!r->io.pins||!r->io.power_up||!r->io.gcc_gate||!r->io.read||!r->io.write||!r->io.now_us||!r->io.delay_us)return -22;
    if(r->state!=EldenPcieRootIdle)return -11;
    r->max_gen=max_gen;r->stage=EldenPcieStagePins;int rc=admit(r);if(rc)return failed(r,rc);
    r->controls_started=true;r->state=EldenPcieRootWorking;
    if((rc=r->io.pins(r->io.context,false)))return failed(r,rc);
    r->perst_low_us=r->io.now_us(r->io.context);r->stage=EldenPcieStagePower;
    if((rc=r->io.power_up(r->io.context,max_gen,&r->epoch))||!r->epoch)return failed(r,rc?rc:-71);
    r->stage=EldenPcieStageClocks;if((rc=clocks(r)))return failed(r,rc);
    r->stage=EldenPcieStageParf;if((rc=parf(r)))return failed(r,rc);
    r->stage=EldenPcieStagePhy;
    r->phy.io=(EldenPciePhyIo){r,phy_admit,phy_read,phy_write,phy_pipe,phy_now,phy_delay};
    if((rc=elden_pcie_phy_start(&r->phy,r->epoch)))return failed(r,rc);
    r->stage=EldenPcieStageSid;if((rc=sid(r)))return failed(r,rc);
    r->stage=EldenPcieStageRoot;if((rc=root_config(r)))return failed(r,rc);
    r->stage=EldenPcieStagePerst;if((rc=release_perst(r)))return failed(r,rc);
    r->stage=EldenPcieStageLink;if((rc=link_up(r)))return failed(r,rc);
    r->stage=EldenPcieStageConfig;if((rc=config_window(r)))return failed(r,rc);
    r->stage=EldenPcieStageVisible;r->state=EldenPcieRootEndpointVisible;return 0;
}
int elden_pcie_config_read32(EldenPcieRoot *r,uint32_t offset,uint32_t *value){
    if(!r||!value||(offset&3)||offset>=0x1000)return -22;
    if(r->state!=EldenPcieRootEndpointVisible)return -11;
    uint32_t got=0;int rc=rd(r,EldenPcieConfig,offset,&got,false);if(!rc)*value=got;return rc;
}
