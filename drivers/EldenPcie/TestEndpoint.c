/* SPDX-License-Identifier: GPL-2.0-only */
/* Actual transaction; all MMIO/time/mapping callbacks below are models. */
#include "Endpoint.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { checks++; if(!(x)){fprintf(stderr,"line%d: %s\n",__LINE__,#x);abort();} } while(0)
static unsigned checks,scenarios;
typedef struct {
    EldenPcieRoot root;
    EldenPcieEndpoint endpoint;
    uint32_t cfg[1024],atu[1024],dbi[1024],masks[6],attrs[6],window,version;
    bool probe[6],mapped,stall_atu,bad_delay,drop_bar,drop_command,drop_remap,epoch_on_map,reset_on_map;
    unsigned calls,fail_at,write_count,maps,bar_reads,bar_writes;
    uint64_t clock;
} Model;
static int step(Model *m){return ++m->calls==m->fail_at?-5:0;}
static int admit_model(void *p,uint64_t epoch){Model *m=p;CHECK(epoch==17);return step(m);}
static int read_model(void *p,unsigned w,uint32_t o,uint32_t *v){
    Model *m=p;int rc=step(m);if(rc)return rc;
    CHECK(!(o&3)&&o<0x1000);
    if(w==EldenPcieConfig){
        if(o>=0x10&&o<0x28&&m->probe[(o-0x10)/4])*v=m->masks[(o-0x10)/4];
        else *v=m->cfg[o/4];
    }else if(w==EldenPcieAtu)*v=m->atu[o/4];
    else {CHECK(w==EldenPcieDbi);*v=m->dbi[o/4];}
    return 0;
}
static int write_model(void *p,unsigned w,uint32_t o,uint32_t v){
    Model *m=p;int rc=step(m);if(rc)return rc;m->write_count++;
    if(w==EldenPcieConfig){
        if(o==4){
            CHECK(!(v&0xffff0005u)); /* no W1C, IO or bus master */
            if(!m->drop_command)m->cfg[1]=(m->cfg[1]&0xffff0000u)|v;
        }else{
            CHECK(o>=0x10&&o<0x28&&!(o&3));CHECK(!(m->cfg[1]&7));
            unsigned i=(o-0x10)/4;
            if(v==UINT32_MAX)m->probe[i]=true;
            else{
                m->probe[i]=false;
                if(!m->drop_bar)m->cfg[o/4]=(v&m->masks[i])|m->attrs[i];
            }
        }
    }else if(w==EldenPcieAtu){
        CHECK(o>=0x200&&o<=0x220&&!(o&3));
        if(!(m->stall_atu&&o==0x204))m->atu[o/4]=v;
    }else{CHECK(w==EldenPcieDbi&&o==0x20);m->dbi[o/4]=v;}
    return 0;
}
static uint64_t now_model(void *p){return ((Model *)p)->clock;}
static void delay_model(void *p,unsigned us){Model *m=p;if(!m->bad_delay)m->clock+=us;}
static int map_model(void *p,uint64_t address,uint32_t bytes){
    Model *m=p;int rc=step(m);if(rc)return rc;
    CHECK(address==0x40400000&&bytes==0x200000);CHECK(!(m->cfg[1]&7));
    CHECK(m->cfg[0x10/4]==(0x40400000|m->attrs[0])&&m->cfg[0x14/4]==0);
    CHECK(m->cfg[0x18/4]==(0x40600000|m->attrs[2]));
    CHECK(m->atu[0x204/4]==0x80000000&&m->atu[0x200/4]==0);
    CHECK(m->atu[0x208/4]==0x40300000&&m->atu[0x210/4]==0x406fffff);
    CHECK(m->dbi[0x20/4]==0x40604030);
    m->mapped=true;m->maps++;if(m->epoch_on_map)m->root.epoch++;
    if(m->reset_on_map)m->cfg[4]=4;
    return 0;
}
static int bar_read_model(void *p,uint32_t o,uint32_t *v){
    Model *m=p;int rc=step(m);if(rc)return rc;
    CHECK(m->mapped&&(m->cfg[1]&7)==2);m->bar_reads++;
    if(o==0x3278)*v=m->window;
    else{CHECK(o==0x80000);CHECK(m->window==0x50000036);*v=m->version;}
    return 0;
}
static int bar_write_model(void *p,uint32_t o,uint32_t v){
    Model *m=p;int rc=step(m);if(rc)return rc;
    CHECK(m->mapped&&(m->cfg[1]&7)==2&&o==0x3278);m->bar_writes++;
    CHECK(v==0x50000036||v==0x10000009);
    if(!m->drop_remap)m->window=v;
    return 0;
}
static void init(Model *m){
    memset(m,0,sizeof(*m));scenarios++;
    m->cfg[0]=0x110e17cb;m->cfg[1]=0x00100400; /* caps status and unrelated command flag */
    m->cfg[4]=4;m->masks[0]=0xffe00004;m->attrs[0]=4;m->masks[1]=UINT32_MAX;
    m->masks[2]=0xffff8000;m->version=0x12340210;m->window=0x10000009;
    m->root=(EldenPcieRoot){.epoch=17,.state=EldenPcieRootEndpointVisible,
        .root_id=0x011c17cb,.endpoint_id=0x110e17cb,.clocks_ready=true,.perst_high=true};
    m->root.io=(EldenPcieRootIo){.context=m,.admit=admit_model,.read=read_model,.write=write_model,
        .now_us=now_model,.delay_us=delay_model};
    m->endpoint=(EldenPcieEndpoint){.root=&m->root,.io={m,map_model,bar_read_model,bar_write_model}};
}
static void rejects(Model *m){
    CHECK(elden_pcie_endpoint_identify(&m->endpoint)<0);
    CHECK(m->endpoint.state==EldenEndpointRefused||m->endpoint.state==EldenEndpointHeld);
    CHECK(!(m->cfg[1]&5));
    unsigned before=m->calls;CHECK(elden_pcie_endpoint_identify(&m->endpoint)==-11);CHECK(m->calls==before);
}
int main(void){
    Model m;init(&m);CHECK(elden_pcie_endpoint_identify(&m.endpoint)==0);
    CHECK(m.endpoint.state==EldenEndpointIdentified&&m.endpoint.stage==EldenEndpointComplete);
    CHECK(m.endpoint.command==0x402&&m.endpoint.chip_version==m.version);
    CHECK(m.endpoint.remap_restored&&m.window==0x10000009&&m.maps==1&&m.bar_writes==2);
    CHECK(m.endpoint.bars[0].wide&&m.endpoint.bars[0].bytes==0x200000);
    CHECK(m.endpoint.bars[2].bytes==0x8000&&m.cfg[1]==0x00100402);
    unsigned calls=m.calls;
    /* Fail each callback, including admission after a successful write/map. */
    for(unsigned i=1;i<=calls;i++){init(&m);m.fail_at=i;rejects(&m);}
    init(&m);m.root.epoch=0;rejects(&m);CHECK(!m.write_count);
    init(&m);m.cfg[0]=0x110d17cb;rejects(&m);CHECK(!m.write_count);
    init(&m);m.cfg[1]|=2;rejects(&m);CHECK(!m.write_count);
    init(&m);m.cfg[3]=0x00010000;rejects(&m);CHECK(!m.write_count);
    init(&m);m.cfg[0x30/4]=1;rejects(&m);CHECK(!m.write_count);
    init(&m);m.atu[0x204/4]=0x80000000;rejects(&m);CHECK(!m.write_count);
    init(&m);m.masks[1]=0;rejects(&m);CHECK(!m.maps); /* truncated64 sizing */
    init(&m);m.masks[0]=0xffa00004;rejects(&m);CHECK(!m.maps); /* non-contiguous mask */
    init(&m);m.masks[2]=0;rejects(&m);CHECK(!m.maps);
    init(&m);m.masks[4]=0xfffff000;rejects(&m);CHECK(!m.maps); /* unexpected resource */
    init(&m);m.cfg[4]=1;rejects(&m);CHECK(!m.maps); /* IO BAR refused */
    init(&m);m.cfg[4]=2;rejects(&m);CHECK(!m.maps); /* obsolete memory type */
    init(&m);m.version=UINT32_MAX;rejects(&m);CHECK(m.endpoint.remap_restored);
    init(&m);m.version=0;rejects(&m);CHECK(m.endpoint.remap_restored);
    init(&m);m.version=0x310;rejects(&m);CHECK(m.endpoint.remap_restored);
    init(&m);m.stall_atu=true;rejects(&m);CHECK(!m.maps&&m.clock==1000);
    init(&m);m.stall_atu=true;m.bad_delay=true;rejects(&m);CHECK(!m.maps&&m.clock==0);
    init(&m);m.drop_bar=true;rejects(&m);CHECK(!m.maps);
    init(&m);m.drop_command=true;rejects(&m);CHECK(!m.bar_reads);
    init(&m);m.drop_remap=true;rejects(&m);CHECK(m.bar_reads==2);
    init(&m);m.epoch_on_map=true;rejects(&m);CHECK(!m.bar_reads&&!(m.cfg[1]&7));
    init(&m);m.reset_on_map=true;rejects(&m);CHECK(!m.bar_reads&&!(m.cfg[1]&7));
    init(&m);m.cfg[6]=4;m.attrs[2]=4;m.masks[2]|=4;m.masks[3]=UINT32_MAX;
    CHECK(elden_pcie_endpoint_identify(&m.endpoint)==0);CHECK(m.endpoint.bars[2].wide);
    init(&m);m.cfg[4]=0;m.attrs[0]=0;m.masks[0]&=~4u;m.masks[1]=0;
    CHECK(elden_pcie_endpoint_identify(&m.endpoint)==0);CHECK(!m.endpoint.bars[0].wide);
    init(&m);m.cfg[1]|=4;CHECK(elden_pcie_endpoint_identify(&m.endpoint)<0);CHECK(!m.write_count);
    init(&m);m.cfg[1]|=1;CHECK(elden_pcie_endpoint_identify(&m.endpoint)<0);CHECK(!m.write_count);
    printf("%u scenarios / %u checks passed; physical hardware modeled\n",scenarios,checks);
    return 0;
}
