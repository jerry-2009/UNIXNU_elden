/* SPDX-License-Identifier: GPL-2.0-only */
#include "Root.c"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks,scenarios;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"line%u %s\n",__LINE__,#x);exit(1);}}while(0)
typedef struct {
    uint32_t *regs[EldenPcieWindowCount];uint64_t now,perst_at;
    unsigned calls,fail_at,endpoint_polls,bus_accesses;int fault;
    bool powered,perst_high,gate;
} Model;
#define REG(m,w,o) ((m)->regs[(w)][(o)/4])
static int call(Model *m){return ++m->calls==m->fail_at?-5:0;}
static int admit_model(void *v,uint64_t epoch){Model *m=v;CHECK(!epoch||(m->powered&&epoch==7));return call(m);}
static int pins_model(void *v,bool high){
    Model *m=v;int rc=call(m);if(rc)return rc;
    if(high){CHECK(m->now-m->perst_at>=100000);CHECK(REG(m,EldenPciePhyWindow,0x444)==3);}
    else m->perst_at=m->now;
    m->perst_high=high;return 0;
}
static int power_model(void *v,unsigned gen,uint64_t *epoch){
    Model *m=v;CHECK(!m->perst_high&&gen>=1&&gen<=3);int rc=call(m);if(rc)return rc;
    m->powered=true;*epoch=m->fault==8?0:7;return 0;
}
static int gate_model(void *v,bool take){
    Model *m=v;CHECK(m->gate!=take);int rc=call(m);if(!rc)m->gate=take;return rc;
}
static void hardware(Model *m){
    if(!(REG(m,EldenPcieGcc,0x5214c)&5)&&m->fault!=1){
        REG(m,EldenPcieGcc,0x6b008)|=1u<<16;REG(m,EldenPcieGcc,0x6c004)|=1u<<16;
    }
    if((REG(m,EldenPcieGcc,0x52008)&Vote8)==Vote8&&(REG(m,EldenPcieGcc,0x52000)&Vote0)==Vote0){
        if(m->fault!=2){REG(m,EldenPcieGcc,0x6b084)&=~1u;REG(m,EldenPcieGcc,0x6b068)&=~1u;}
        for(unsigned i=0;i<sizeof(branches)/sizeof(branches[0]);i++){
            if(branches[i].skip||branches[i].hwcg)continue;
            if(m->fault==3&&branches[i].halt==0x6b044)continue;
            REG(m,EldenPcieGcc,branches[i].halt)&=~(1u<<31);
        }
    }
    if(REG(m,EldenPciePhyWindow,0x444)==3&&m->fault!=4)REG(m,EldenPciePhyWindow,0x414)=0;
    if(m->perst_high&&(REG(m,EldenPcieParf,0x1b0)&256)&&m->fault!=5){
        REG(m,EldenPcieDbi,0x728)=0x11;REG(m,EldenPcieDbi,0x72c)=16;
        REG(m,EldenPcieDbi,0x80)=(2u<<20)|((REG(m,EldenPcieDbi,0xa0)&15u)<<16);
    }
}
static void bus_gate(Model *m,unsigned w){
    if(w==EldenPcieGcc||w==EldenPcieTcsr)return;
    m->bus_accesses++;
    CHECK((REG(m,EldenPcieGcc,0x6b008)&(1u<<16))&&(REG(m,EldenPcieGcc,0x6c004)&(1u<<16)));
    CHECK((REG(m,EldenPcieGcc,0x52008)&Vote8)==Vote8&&(REG(m,EldenPcieGcc,0x52000)&Vote0)==Vote0);
    CHECK(REG(m,EldenPcieTcsr,8)&1u);
}
static int read_model(void *v,unsigned w,uint32_t o,uint32_t *value){
    Model *m=v;CHECK(w<EldenPcieWindowCount&&o<lengths[w]&&!(o&3u));int rc=call(m);if(rc)return rc;
    hardware(m);bus_gate(m,w);
    if(w==EldenPcieConfig&&o==0){
        CHECK(m->perst_high&&REG(m,EldenPcieAtu,4)==0x80000000u);
        m->endpoint_polls++;*value=(m->fault==6||m->endpoint_polls<3)?UINT32_MAX:m->fault==7?0x110717cb:0x110e17cb;
    }else *value=REG(m,w,o);
    return 0;
}
static int write_model(void *v,unsigned w,uint32_t o,uint32_t value){
    Model *m=v;CHECK(w<EldenPcieWindowCount&&o<lengths[w]&&!(o&3u));
    if(w==EldenPcieGcc)CHECK(m->gate);
    bus_gate(m,w);int rc=call(m);if(rc)return rc;
    if(w==EldenPciePhyWindow&&(o==0x400||o==0x444))CHECK((REG(m,EldenPcieGcc,0x6b080)&3u)==0);
    if((w==EldenPcieDbi||w==EldenPcieConfig)&&o==4){
        uint32_t old=REG(m,w,o);REG(m,w,o)=(value&0xffffu)|(old&~(value&0xffff0000u)&0xffff0000u);
    }else REG(m,w,o)=value;
    hardware(m);return 0;
}
static uint64_t now_model(void *v){return ((Model *)v)->now;}
static void delay_model(void *v,unsigned n){Model *m=v;if(m->fault!=9)m->now+=n;}
static void setup(Model *m,EldenPcieRoot *r){
    memset(m,0,sizeof(*m));memset(r,0,sizeof(*r));m->perst_high=true;
    for(unsigned w=0;w<EldenPcieWindowCount;w++){m->regs[w]=calloc(1,lengths[w]);CHECK(m->regs[w]);}
    REG(m,EldenPcieGcc,0x5214c)=0xa5;
    /* Bit31 alone is deliberately ON, so wrong GDSC status selection fails the test. */
    REG(m,EldenPcieGcc,0x6b004)=REG(m,EldenPcieGcc,0x6c000)=1u<<31;
    REG(m,EldenPcieGcc,0x52008)=0x80000000u;REG(m,EldenPcieGcc,0x52000)=0x40000000u;
    REG(m,EldenPcieGcc,0x6b088)=REG(m,EldenPcieGcc,0x6b06c)=0xd00000;
    for(unsigned i=0;i<sizeof(branches)/sizeof(branches[0]);i++)REG(m,EldenPcieGcc,branches[i].halt)=(1u<<31)|(branches[i].hwcg?2u:0);
    REG(m,EldenPciePhyWindow,0x400)=1;REG(m,EldenPciePhyWindow,0x414)=0x40;
    REG(m,EldenPcieDbi,0)=0x011c17cb;REG(m,EldenPcieDbi,0x34)=0x70;REG(m,EldenPcieDbi,0x70)=0x10;
    REG(m,EldenPcieDbi,4)=0xf9000000u;REG(m,EldenPcieConfig,4)=0xf9000007u;
    r->io=(EldenPcieRootIo){m,admit_model,pins_model,power_model,gate_model,read_model,write_model,now_model,delay_model};
}
static void dispose(Model *m){for(unsigned w=0;w<EldenPcieWindowCount;w++)free(m->regs[w]);}
int main(void){
    Model m;EldenPcieRoot r;unsigned length=0;
    for(unsigned gen=1;gen<=3;gen++){
        setup(&m,&r);CHECK(!elden_pcie_root_start(&r,gen));
        CHECK(r.state==EldenPcieRootEndpointVisible&&!r.gcc_held&&r.phy.state==EldenPciePhyReady);
        CHECK(r.endpoint_id==0x110e17cb&&m.endpoint_polls==3&&((r.link_status>>16)&15)==gen);
        CHECK(REG(&m,EldenPcieGcc,0x5214c)==0xa0);
        CHECK(REG(&m,EldenPcieGcc,0x52008)==(0x80000000u|Vote8));CHECK(REG(&m,EldenPcieGcc,0x52000)==(0x40000000u|Vote0));
        CHECK((REG(&m,EldenPcieGcc,0x6b088)&RcgMask)==1&&
            (REG(&m,EldenPcieGcc,0x6b06c)&RcgMask)==(gen==3?0x605u:1u));
        CHECK(REG(&m,EldenPcieParf,0x2000+4*0x15)==0x01000100);
        CHECK(REG(&m,EldenPcieConfig,4)==0xf9000000u&&REG(&m,EldenPcieDbi,4)==0xf9000006u);
        length=m.calls;
        uint32_t got=0;CHECK(!elden_pcie_config_read32(&r,0,&got)&&got==0x110e17cb);
        unsigned before=m.calls;CHECK(elden_pcie_root_start(&r,gen)==-11&&before==m.calls);
        CHECK(elden_pcie_config_read32(&r,0x1000,&got)==-22);dispose(&m);scenarios++;
    }
    for(unsigned at=1;at<=length;at++){
        setup(&m,&r);m.fail_at=at;CHECK(elden_pcie_root_start(&r,3)==-5);
        CHECK(r.state==EldenPcieRootHeld||r.state==EldenPcieRootRefused);
        CHECK(r.gcc_held==m.gate);unsigned before=m.calls;
        CHECK(elden_pcie_root_start(&r,3)==-11&&before==m.calls);dispose(&m);scenarios++;
    }
    for(int fault=1;fault<=9;fault++){
        setup(&m,&r);m.fault=fault;CHECK(elden_pcie_root_start(&r,3)<0&&r.state==EldenPcieRootHeld);
        if(fault<=3)CHECK(!m.bus_accesses&&r.stage==EldenPcieStageClocks);
        if(fault==4)CHECK(r.stage==EldenPcieStagePhy);
        if(fault==5)CHECK(r.stage==EldenPcieStageLink);
        if(fault==6||fault==7)CHECK(r.stage==EldenPcieStageConfig);
        if(fault==8)CHECK(r.stage==EldenPcieStagePower);
        dispose(&m);scenarios++;
    }
    setup(&m,&r);REG(&m,EldenPcieDbi,0x70)=0x7010;CHECK(elden_pcie_root_start(&r,3)==-71);dispose(&m);scenarios++;
    setup(&m,&r);REG(&m,EldenPcieGcc,0x6b084)=1;CHECK(elden_pcie_root_start(&r,3)==-16&&!m.bus_accesses);dispose(&m);scenarios++;
    CHECK(!elden_pcie_window_base(99)&&!elden_pcie_window_bytes(99));
    printf("%u root+PHY transaction scenarios / %u checks passed\n",scenarios,checks);return 0;
}
