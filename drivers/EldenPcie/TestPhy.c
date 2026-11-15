/* SPDX-License-Identifier: GPL-2.0-only */
#include "Phy.c"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks,scenarios;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"line%u %s\n",__LINE__,#x);exit(1);}}while(0)
typedef struct {
    uint32_t regs[0x2000/4];uint64_t now;
    unsigned calls,fail_at,writes,pipes;int fault;
} Model;
static int call(Model *m){return ++m->calls==m->fail_at?-5:0;}
static int admit(void *v,uint64_t epoch){CHECK(epoch==7);return call(v);}
static int read_reg_model(void *v,uint16_t off,uint32_t *value){
    Model *m=v;CHECK(off==0x400||off==0x444||off==0x414);int rc=call(m);if(rc)return rc;
    if(off==0x414&&m->now>=30&&m->fault!=1)m->regs[off/4]=0;
    *value=m->regs[off/4];
    if(m->fault==2&&off==0x414)*value=UINT32_MAX;
    if(m->fault==3&&off==0x414){*value=0;m->now=10000;}
    if(m->fault==6&&off==0x414){*value=0;m->now=500;}
    if(m->fault==4&&m->pipes&&off==0x400)*value=1;
    return 0;
}
static int write_reg_model(void *v,uint16_t off,uint32_t value){
    Model *m=v;CHECK(m->writes<Count);CHECK(off==elden_pcie_phy_sequence[m->writes].offset&&value==elden_pcie_phy_sequence[m->writes].value);
    CHECK(m->writes<Count-2||m->pipes==1);int rc=call(m);if(rc)return rc;
    m->regs[off/4]=value;m->writes++;return 0;
}
static int pipe(void *v){Model *m=v;CHECK(m->writes==Count-2);int rc=call(m);if(!rc)m->pipes++;return rc;}
static uint64_t now(void *v){return ((Model *)v)->now;}
static void delay(void *v,unsigned us){Model *m=v;CHECK(us==10);if(m->fault!=5)m->now+=us;}
static void setup(Model *m,EldenPciePhy *p){
    memset(m,0,sizeof(*m));memset(p,0,sizeof(*p));m->regs[0x400/4]=1;m->regs[0x414/4]=0x40;
    p->io=(EldenPciePhyIo){m,admit,read_reg_model,write_reg_model,pipe,now,delay};
}
int main(void){
    Model m;EldenPciePhy p;setup(&m,&p);CHECK(!elden_pcie_phy_start(&p,7));
    CHECK(p.state==EldenPciePhyReady&&p.writes==127&&m.pipes==1&&p.polls==4);unsigned length=m.calls;scenarios++;
    for(unsigned at=1;at<=length;at++){
        setup(&m,&p);m.fail_at=at;CHECK(elden_pcie_phy_start(&p,7)==-5&&p.error==-5);
        CHECK(p.state==EldenPciePhyRefused||p.state==EldenPciePhyHeld);
        unsigned calls=m.calls;CHECK(elden_pcie_phy_start(&p,7)==-11&&calls==m.calls);scenarios++;
    }
    for(int fault=1;fault<=6;fault++){
        setup(&m,&p);m.fault=fault;if(fault==6)m.now=1000;
        CHECK(elden_pcie_phy_start(&p,7)<0&&p.state==EldenPciePhyHeld);scenarios++;
    }
    setup(&m,&p);m.regs[0x400/4]=0;CHECK(elden_pcie_phy_start(&p,7)==-19&&!m.writes);scenarios++;
    setup(&m,&p);m.regs[0x444/4]=3;CHECK(elden_pcie_phy_start(&p,7)==-19&&!m.writes);scenarios++;
    printf("%u PHY transaction scenarios / %u checks passed\n",scenarios,checks);return 0;
}
