/* SPDX-License-Identifier: GPL-2.0-only */
#include "Power.h"
#include <string.h>
static uint64_t bcm_div(uint64_t value,uint32_t divisor){
    /* Exact bcm-voter.c rule: truncate, except a nonzero sub-unit vote is1. */
    return value&&value<divisor?1:value/divisor;
}
static int arc(const Sm8750CmdDb *db,const char *name,unsigned minimum,Sm8750RpmhArc *out,uint32_t *index){
    unsigned count=0;int rc=Sm8750CmdDbArc(db,name,&out->addr,out->vlvl,&count);if(rc)return rc;
    if(count<2||count>16||out->vlvl[0])return -71;
    for(unsigned i=1;i<count;i++)if(out->vlvl[i]<=out->vlvl[i-1])return -71;
    out->count=(uint8_t)count;out->present=1;
    rc=Sm8750RpmhArcTop(out,index);if(rc)return rc;
    return out->vlvl[*index]>=minimum?0:-34;
}
int elden_pcie_power_plan(const Sm8750CmdDb *db,const EldenPcieRail before[2],const uint16_t retained[2],unsigned max_gen,unsigned policy,EldenPciePowerPlan *out){
    if(!db||!before||!out||max_gen<1||max_gen>3)return -22;
    if(policy!=EldenPciePowerFullOnDiagnostic)return -95;
    EldenPciePowerPlan plan={0};Sm8750RpmhArc mx={0},cx={0};
    uint32_t vrm[2]={0},sn4=0,sh1=0,shunit=0;uint16_t shwidth=0;
    const unsigned minimum[2]={880,1200},maximum[2]={920,1256};
    const char *names[2]={"ldof1","ldog3"};int rc;
    /* Validate all physical samples and every resource before returning a plan. */
    for(unsigned i=0;i<2;i++){
        const EldenPcieRail *r=&before[i];
        if(r->type!=4||r->subtype!=0xad||r->mode==0xee||r->mv>maximum[i]||
           ((r->enable&0x80)&&!(r->status&0x80)))return -19;
        plan.rail_mv[i]=(uint16_t)(r->mv>minimum[i]?r->mv:minimum[i]);
        if(retained){
            if(retained[i]&&(retained[i]<minimum[i]||retained[i]>maximum[i]))return -22;
            if(retained[i]>plan.rail_mv[i])plan.rail_mv[i]=retained[i];
        }
        if((rc=Sm8750CmdDbVrm(db,names[i],&vrm[i])))return rc;
    }
    unsigned level=max_gen==3?256:64;
    if((rc=arc(db,"mx.lvl",level,&mx,&plan.mx_index))||(rc=arc(db,"cx.lvl",level,&cx,&plan.cx_index)))return rc;
    plan.mx_level=mx.vlvl[plan.mx_index];plan.cx_level=cx.vlvl[plan.cx_index];
    if((rc=Sm8750CmdDbBcm(db,"SN4",&sn4,&plan.sn4_unit,&plan.sn4_width,&plan.sn4_vcd))||
       (rc=Sm8750CmdDbBcm(db,"SH1",&sh1,&shunit,&shwidth,&plan.sh1_vcd)))return rc;
    if(!plan.sn4_unit||!plan.sn4_width)return -71;
    uint32_t addresses[]={mx.addr,cx.addr,vrm[0],vrm[1],sn4,sh1};
    for(unsigned i=0;i<6;i++)for(unsigned j=0;j<i;j++)if(addresses[i]==addresses[j])return -71;
    uint32_t kbps=max_gen==3?2000000:max_gen==2?1000000:500000;
    uint64_t scaled=bcm_div((uint64_t)kbps*plan.sn4_width,8);
    uint64_t vote=bcm_div(scaled*1000,plan.sn4_unit);
    plan.sn4_minimum=vote>0x3fff?0x3fff:(uint32_t)vote;
    plan.sn4_applied=0x3fff; /* explicit full-on floor, not an invented boot vote */
    plan.commands[0]=(Sm8750RpmhCmd){mx.addr,plan.mx_index};
    plan.commands[1]=(Sm8750RpmhCmd){cx.addr,plan.cx_index};
    for(unsigned i=0;i<2;i++){
        plan.commands[2+3*i]=(Sm8750RpmhCmd){vrm[i],plan.rail_mv[i]};
        plan.commands[3+3*i]=(Sm8750RpmhCmd){vrm[i]+8,7};
        plan.commands[4+3*i]=(Sm8750RpmhCmd){vrm[i]+4,1};
    }
    plan.commands[8]=(Sm8750RpmhCmd){sn4,Sm8750BcmCommand(1,1,plan.sn4_applied,plan.sn4_applied)};
    plan.commands[9]=(Sm8750RpmhCmd){sh1,Sm8750BcmCommand(1,1,0,1)};
    plan.count=10;plan.wait_mask=0x3ff;plan.max_gen=max_gen;*out=plan;return 0;
}
