/* SPDX-License-Identifier: GPL-2.0-only */
/* Method: Sheng endpointProbe; board/Peach fields: TB322FC Linux6f97250e.
 * Unlike the full networking path, this stage leaves endpoint bus-master OFF. */
#include "Endpoint.h"
#include <stddef.h>

#define MEM_BASE UINT64_C(0x40300000)
/* Stock allows 0x03d00000 bytes; fixed Linux has a larger 0x23d00000 range.
 * Use their intersection, never infer ownership of the additional aperture. */
#define MEM_END UINT64_C(0x44000000)
#define REMAP 0x3278u
#define VERSION 0x01b00000u

static int fail(EldenPcieEndpoint *e,int rc){
    e->error=rc;e->state=e->controls_started?EldenEndpointHeld:EldenEndpointRefused;return rc;
}
static int admit(EldenPcieEndpoint *e){
    EldenPcieRoot *r=e->root;
    if(r->state!=EldenPcieRootEndpointVisible||!r->clocks_ready||!r->perst_high||
       !e->epoch||r->epoch!=e->epoch||r->root_id!=0x011c17cb||r->endpoint_id!=0x110e17cb)return -11;
    return r->io.admit(r->io.context,e->epoch);
}
static int rd(EldenPcieEndpoint *e,unsigned w,uint32_t o,uint32_t *v,bool ff){
    if((w!=EldenPcieConfig&&w!=EldenPcieDbi&&w!=EldenPcieAtu)||(o&3)||o>=0x1000)return -22;
    int rc=admit(e);if(rc)return rc;*v=UINT32_MAX;
    e->last_window=w;e->last_offset=o;
    rc=e->root->io.read(e->root->io.context,w,o,v);e->last_value=*v;
    return rc?rc:(!ff&&*v==UINT32_MAX)?-5:admit(e);
}
static int wr(EldenPcieEndpoint *e,unsigned w,uint32_t o,uint32_t v){
    if((w!=EldenPcieConfig&&w!=EldenPcieDbi&&w!=EldenPcieAtu)||(o&3)||o>=0x1000)return -22;
    /* Never accidentally turn on endpoint IO/BM or write PCI W1C status. */
    if(w==EldenPcieConfig&&o==4&&(v&~0xfffau))return -22;
    int rc=admit(e);if(rc)return rc;e->controls_started=true;
    e->last_window=w;e->last_offset=o;e->last_value=v;
    rc=e->root->io.write(e->root->io.context,w,o,v);if(!rc)e->writes++;
    return rc?rc:admit(e);
}
static int exact(EldenPcieEndpoint *e,unsigned w,uint32_t o,uint32_t v){
    int rc=wr(e,w,o,v);if(rc)return rc;uint32_t got=0;
    rc=rd(e,w,o,&got,true);return rc?rc:got!=v?-71:0;
}
static int config_check(EldenPcieEndpoint *e,bool memory){
    uint32_t id=0,cmd=0,header=0,rom=0;int rc;
    if((rc=rd(e,EldenPcieConfig,0,&id,false))||(rc=rd(e,EldenPcieConfig,4,&cmd,false))||
       (rc=rd(e,EldenPcieConfig,0x0c,&header,false))||(rc=rd(e,EldenPcieConfig,0x30,&rom,false)))return rc;
    if(id!=0x110e17cb||((header>>16)&0xff)!=0||(cmd&7)!=(memory?2u:0u)||(rom&1))return -19;
    e->command=cmd&0xffffu;return 0;
}
static int size_bars(EldenPcieEndpoint *e){
    for(unsigned i=0;i<6;i++){
        EldenPcieBar *b=&e->bars[i];uint32_t o=0x10+4*i;int rc;
        if((rc=rd(e,EldenPcieConfig,o,&b->saved_low,false)))return rc;
        if((b->saved_low&1)||((b->saved_low&6)!=0&&(b->saved_low&6)!=4))return -95;
        b->wide=(b->saved_low&6)==4;
        if(b->wide){if(i==5)return -71;if((rc=rd(e,EldenPcieConfig,o+4,&b->saved_high,true)))return rc;}
        /* Decoders already disabled. Probe both halves of a 64-bit BAR. */
        if((rc=wr(e,EldenPcieConfig,o,UINT32_MAX)))return rc;
        if(b->wide&&(rc=wr(e,EldenPcieConfig,o+4,UINT32_MAX)))return rc;
        if((rc=rd(e,EldenPcieConfig,o,&b->mask_low,true)))return rc;
        if(b->wide&&(rc=rd(e,EldenPcieConfig,o+4,&b->mask_high,true)))return rc;
        if(b->wide&&(rc=exact(e,EldenPcieConfig,o+4,b->saved_high)))return rc;
        if((rc=exact(e,EldenPcieConfig,o,b->saved_low)))return rc;
        if(!b->mask_low&&!b->wide)continue;
        if((b->mask_low&15)!=(b->saved_low&15))return -71;
        uint64_t mask=(b->mask_low&~UINT64_C(15))|((uint64_t)b->mask_high<<32);
        b->bytes=b->wide?(~mask+1):UINT64_C(0x100000000)-mask;
        if(!b->bytes||(b->bytes&(b->bytes-1))||b->bytes<16||b->bytes>MEM_END-MEM_BASE)return -34;
        uint64_t canonical=~(b->bytes-1)&~UINT64_C(15);
        if(!b->wide)canonical&=UINT32_MAX;
        if(mask!=canonical)return -71;
        b->present=true;if(b->wide)i++;
    }
    /* Actual discovery must match this board's recorded two resources. */
    if(!e->bars[0].present||e->bars[0].bytes!=0x200000||
       !e->bars[2].present||e->bars[2].bytes!=0x8000)return -19;
    for(unsigned i=1;i<6;i++)if(i!=2&&e->bars[i].present)return -19;
    return config_check(e,false);
}
static int assign(EldenPcieEndpoint *e){
    uint64_t next=MEM_BASE;
    for(unsigned i=0;i<6;i++){
        EldenPcieBar *b=&e->bars[i];if(!b->present)continue;
        uint64_t address=(next+b->bytes-1)&~(b->bytes-1);
        if(address<MEM_BASE||address>MEM_END-b->bytes)return -34;
        b->address=address;next=address+b->bytes;
    }
    e->memory_base=(uint32_t)MEM_BASE;
    uint64_t end=(next+0xfffffu)&~UINT64_C(0xfffff);
    if(end>MEM_END)return -34;
    e->memory_limit=(uint32_t)(end-1);
    for(unsigned i=0;i<6;i++){
        EldenPcieBar *b=&e->bars[i];if(!b->present)continue;uint32_t o=0x10+4*i;int rc;
        if(b->wide&&(rc=exact(e,EldenPcieConfig,o+4,0)))return rc;
        if((rc=exact(e,EldenPcieConfig,o,(uint32_t)b->address|(b->saved_low&15))))return rc;
    }
    return 0;
}
static int assigned_check(EldenPcieEndpoint *e){
    for(unsigned i=0;i<6;i++){
        EldenPcieBar *b=&e->bars[i];if(!b->present)continue;
        uint32_t v=0,o=0x10+4*i;int rc=rd(e,EldenPcieConfig,o,&v,false);if(rc)return rc;
        if(v!=((uint32_t)b->address|(b->saved_low&15)))return -71;
        if(b->wide){rc=rd(e,EldenPcieConfig,o+4,&v,true);if(rc)return rc;if(v)return -71;}
    }
    return 0;
}
static int window(EldenPcieEndpoint *e){
    uint32_t control=0;int rc=rd(e,EldenPcieAtu,0x204,&control,false);if(rc)return rc;
    if(control)return -16; /* Do not take over an active/foreign outbound region. */
    const uint32_t values[][2]={{0x208,e->memory_base},{0x20c,0},{0x210,e->memory_limit},
        {0x214,e->memory_base},{0x218,0},{0x220,0},{0x200,0}};
    for(unsigned i=0;i<sizeof(values)/sizeof(values[0]);i++)
        if((rc=exact(e,EldenPcieAtu,values[i][0],values[i][1])))return rc;
    if((rc=wr(e,EldenPcieAtu,0x204,1u<<31)))return rc;
    uint64_t start=e->root->io.now_us(e->root->io.context);
    for(unsigned i=0;i<100;i++){
        uint64_t now=e->root->io.now_us(e->root->io.context);
        if(now<start||now-start>=1000)return -110;
        if((rc=rd(e,EldenPcieAtu,0x204,&control,false)))return rc;
        if(control==(1u<<31)){
            now=e->root->io.now_us(e->root->io.context);if(now<start||now-start>=1000)return -110;
            return exact(e,EldenPcieDbi,0x20,(e->memory_limit&0xfff00000)|((e->memory_base>>16)&0xfff0));
        }
        if(control)return -71;
        e->root->io.delay_us(e->root->io.context,10);
    }
    return -110;
}
static int bar_read(EldenPcieEndpoint *e,uint32_t o,uint32_t *v){
    if(!e->mapped||!e->decode_enabled||(o&3)||o>e->bars[0].bytes-4)return -22;
    int rc=admit(e);if(rc)return rc;*v=UINT32_MAX;
    e->last_window=EldenPcieWindowCount;e->last_offset=o;
    rc=e->io.read_bar0(e->io.context,o,v);e->last_value=*v;
    return rc?rc:*v==UINT32_MAX?-5:admit(e);
}
static int remap(EldenPcieEndpoint *e,uint32_t v){
    int rc=admit(e);if(rc)return rc;
    e->last_window=EldenPcieWindowCount;e->last_offset=REMAP;e->last_value=v;
    rc=e->io.write_bar0(e->io.context,REMAP,v);if(rc)return rc;e->writes++;
    uint32_t got=0;rc=bar_read(e,REMAP,&got);return rc?rc:got!=v?-71:0;
}
int elden_pcie_endpoint_identify(EldenPcieEndpoint *e){
    if(!e||!e->root||!e->root->io.admit||!e->root->io.read||!e->root->io.write||
       !e->root->io.now_us||!e->root->io.delay_us||!e->io.map_bar0||!e->io.read_bar0||!e->io.write_bar0)return -22;
    if(e->state!=EldenEndpointIdle)return -11;
    e->epoch=e->root->epoch;e->stage=EldenEndpointCheck;int rc=admit(e);if(rc)return fail(e,rc);
    e->state=EldenEndpointWorking;
    if((rc=config_check(e,false)))return fail(e,rc);
    uint32_t old_region=0;
    if((rc=rd(e,EldenPcieAtu,0x204,&old_region,false)))return fail(e,rc);
    if(old_region)return fail(e,-16);
    e->stage=EldenEndpointSize;if((rc=size_bars(e)))return fail(e,rc);
    e->stage=EldenEndpointAssign;if((rc=assign(e)))return fail(e,rc);
    e->stage=EldenEndpointWindow;if((rc=window(e)))return fail(e,rc);
    e->stage=EldenEndpointMap;if((rc=admit(e)))return fail(e,rc);
    if((rc=e->io.map_bar0(e->io.context,e->bars[0].address,(uint32_t)e->bars[0].bytes)))return fail(e,rc);
    e->mapped=true;if((rc=config_check(e,false))||(rc=assigned_check(e)))return fail(e,rc);
    e->stage=EldenEndpointDecode;
    if((rc=wr(e,EldenPcieConfig,4,e->command|2u))||(rc=config_check(e,true)))return fail(e,rc);
    e->decode_enabled=true;e->stage=EldenEndpointChip;
    if((rc=bar_read(e,REMAP,&e->remap_saved)))return fail(e,rc);
    uint32_t selected=(e->remap_saved&~0x3fu)|0x40000000u|((VERSION>>19)&63u);
    if((rc=remap(e,selected)))return fail(e,rc);
    int version_rc=bar_read(e,0x80000u+(VERSION&0x7ffffu),&e->chip_version);
    /* Restore the dynamic window only under the same live admission. */
    if((rc=remap(e,e->remap_saved)))return fail(e,rc);
    e->remap_restored=true;
    if(version_rc)return fail(e,version_rc);
    if(((e->chip_version>>8)&15)!=2)return fail(e,-19);
    if((rc=config_check(e,true))||(rc=assigned_check(e)))return fail(e,rc);
    e->stage=EldenEndpointComplete;e->state=EldenEndpointIdentified;return 0;
}
