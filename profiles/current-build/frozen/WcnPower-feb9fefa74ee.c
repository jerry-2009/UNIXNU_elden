/* SPDX-License-Identifier: GPL-2.0-only */
/* Sequence/OL-CPR adapted from pinned TB322FC pwrseq-qcom-wcn and DTS6f97250e.
 * Physical primitives and the shared resource/epoch ledger remain board-owned.
 */
#include "WcnPower.h"
#include <string.h>
const EldenWcnRailSpec elden_wcn_rail_specs[EldenWcnRailCount]={
    {"smpf5",0x5a7,876,1000},{"ldof3",0x5c3,1800,1800},
    {"ldof2",0x5c2,1200,1200},{"smpd4",0x3a4,876,1036},
    {"smpi7",0x8ad,1312,1340},{"smpg3",0x6a1,1860,2000}
};
static const char *const initial[]={
    "{class: wlan_pdc, ss: rf, res: s5f.m, enable: 1}",
    "{class: wlan_pdc, ss: rf, res: s5f.v, enable: 1}",
    "{class: wlan_pdc, ss: rf, res: s5f.v, upval: 876}",
    "{class: wlan_pdc, ss: rf, res: s5f.v, dwnval: 876}"
};
static int fail(EldenWcnPower *p,int error,bool uncertain){
    p->error=error;p->quarantined|=uncertain;p->state=EldenWcnPowerFailed;return error;
}
static int delay(EldenWcnPower *p,unsigned us){
    uint64_t before=p->io.now_us(p->io.context);
    p->io.delay_us(p->io.context,us);
    uint64_t after=p->io.now_us(p->io.context);
    if(after<before||after-before<us)return fail(p,EldenWcnPowerTimeout,true);
    return 0;
}
static int parents(EldenWcnPower *p){
    uint32_t main=0,even=0;int rc=p->io.parents(p->io.context,&main,&even);
    if(rc||main!=600000000||even!=300000000)return rc?rc:EldenWcnPowerIdentity;
    return 0;
}
static int rails(EldenWcnPower *p){
    for(unsigned i=0;i<EldenWcnRailCount;i++){
        EldenWcnRailState s={0};int rc=p->io.rail_read(p->io.context,(EldenWcnRail)i,&s);
        if(rc||(s.enable&0x80)==0||(s.status&0x80)==0||s.mode==0xee||
           (s.mode&7)!=7||s.mv<p->target[i]||s.mv>elden_wcn_rail_specs[i].maximum)
            return rc?rc:EldenWcnPowerIdentity;
    }
    return parents(p);
}
int elden_wcn_power_acquire(EldenWcnPower *p,uint64_t epoch){
    if(!p||!epoch||!p->io.preflight||!p->io.rail_read||!p->io.rail_vote||!p->io.qmp||
       !p->io.bt_set||!p->io.bt_get||!p->io.wlan_get||!p->io.parents||
       !p->io.now_us||!p->io.delay_us||p->quarantined||
       (p->state!=EldenWcnPowerIdle&&p->state!=EldenWcnPowerClosed))
        return EldenWcnPowerArgument;
    p->stage=1;p->error=0;
    int rc=p->io.preflight(p->io.context);if(rc)return rc;
    if((rc=parents(p)))return rc;
    /* Every voltage range is qualified before the first PDC/control write. */
    for(unsigned i=0;i<EldenWcnRailCount;i++){
        const EldenWcnRailSpec *r=&elden_wcn_rail_specs[i];
        if((rc=p->io.rail_read(p->io.context,(EldenWcnRail)i,&p->before[i])))return rc;
        const EldenWcnRailState *s=&p->before[i];
        if(s->mv>r->maximum||s->mode==0xee||((s->enable&0x80)&&!(s->status&0x80)))
            return EldenWcnPowerIdentity;
        p->target[i]=s->mv>r->minimum?s->mv:r->minimum;
    }
    bool wlan=false,bt=false;
    if((rc=p->io.wlan_get(p->io.context,&wlan))||(rc=p->io.bt_get(p->io.context,&bt)))return rc;
    p->epoch=epoch;p->state=EldenWcnPowerPreparing;p->control_started=true;
    p->stage=2;
    for(unsigned i=0;i<4;i++){
        if((rc=p->io.qmp(p->io.context,initial[i])))return fail(p,rc,true);
        p->qmp_messages++;
    }
    /* Like the Linux probe's GPIOD_OUT_LOW, hold the chip in reset before
     * external power configuration; repeat the timed low after votes. */
    p->bt_changed=true;
    if((rc=p->io.bt_set(p->io.context,false)))return fail(p,rc,true);
    p->stage=3;
    for(unsigned i=0;i<EldenWcnRailCount;i++){
        if((rc=p->io.rail_vote(p->io.context,(EldenWcnRail)i,p->target[i],7,true)))
            return fail(p,rc,true);
        p->rail_votes++;p->baseline_votes_retained=true;
    }
    if((rc=rails(p)))return fail(p,rc,true);
    p->stage=4;
    if((rc=p->io.bt_set(p->io.context,false))||delay(p,50000))return fail(p,rc?rc:p->error,true);
    if((rc=p->io.wlan_get(p->io.context,&wlan)))return fail(p,rc,true);
    if(!wlan&&delay(p,100000))return p->error;
    if((rc=rails(p)))return fail(p,rc,true);
    p->stage=5;
    if((rc=p->io.bt_set(p->io.context,true))||delay(p,50000))return fail(p,rc?rc:p->error,true);
    if((rc=p->io.bt_get(p->io.context,&bt))||!bt||(rc=rails(p)))
        return fail(p,rc?rc:EldenWcnPowerIdentity,true);
    p->state=EldenWcnPowerReady;p->stage=6;return 0;
}
int elden_wcn_power_stop(EldenWcnPower *p,uint64_t epoch){
    if(!p||epoch!=p->epoch||p->quarantined||p->state!=EldenWcnPowerReady)return EldenWcnPowerAgain;
    p->stage=7;int rc=p->io.bt_set(p->io.context,false);
    if(rc||delay(p,100000))return fail(p,rc?rc:p->error,true);
    bool high=true;if((rc=p->io.bt_get(p->io.context,&high))||high)
        return fail(p,rc?rc:EldenWcnPowerIdentity,true);
    p->state=EldenWcnPowerStopped;return 0;
}
int elden_wcn_power_finish(EldenWcnPower *p,uint64_t epoch){
    if(!p||p->epoch!=epoch||p->quarantined||p->state!=EldenWcnPowerStopped)return EldenWcnPowerAgain;
    /* Boot consumers are not yet registered for all these shared supplies.
     * Retain their validated votes; no global regulator enable=0 or lowering.
     * M8 must replace this boot guard with qualified low-power references. */
    p->state=EldenWcnPowerClosed;p->stage=8;return 0;
}
int elden_wcn_power_check(const EldenWcnPower *p,uint64_t epoch,unsigned op){
    if(!p||!epoch||p->epoch!=epoch||p->quarantined)return EldenWcnPowerAgain;
    if(op==3)return p->state==EldenWcnPowerStopped?0:EldenWcnPowerAgain;
    if(op==1||op==2)return p->state==EldenWcnPowerReady?0:EldenWcnPowerAgain;
    return EldenWcnPowerArgument;
}
int elden_wcn_parent_decode(uint32_t mode,uint32_t opmode,uint32_t l,uint32_t alpha,
    uint32_t user,uint32_t *main,uint32_t *even){
    if(!main||!even)return EldenWcnPowerArgument;
    /* Taycan uses lucid-evo vote-run (USER_CTL bit25). In that mode the
     * firmware vote can keep the PLL locked while OPMODE remains STANDBY.
     * Only main/even outputs are needed; the third output is not a parent.
     * Observe only: never retune the shared PLL or create a clock vote here. */
    bool vote_run=(user&(1u<<25))!=0;
    if((mode&0x80000001u)!=0x80000001u||opmode>1||(!vote_run&&opmode!=1)||
       (user&3u)!=3u||
       ((user>>10)&15u)!=1u)return EldenWcnPowerIdentity;
    uint64_t hz=19200000ULL*(l&65535u)+(19200000ULL*(alpha&65535u)>>16);
    if(hz!=600000000ULL)return EldenWcnPowerIdentity;
    *main=(uint32_t)hz;*even=(uint32_t)(hz/2);return 0;
}
typedef struct {const char *pin;unsigned rail;} PinMap;
static const PinMap map[]={
    {"VDDD_AON_0P9",0},{"VDDA_RFA_1P9",2},{"VDDA_RFA_1P3",3},
    {"VDDA_RFA_0P9",0},{"VDDD_WLMX_0P9",1},{"VDDD_WLCX_0P9",0},
    {"VDDD_BTCX_0P9",0},{"VDDD_BTCMX_0P9",0},{"VDDA_PCIE_1P2",3},{"VDDA_PCIE_0P9",3}
};
static const char *const cpr_rails[]={"s5f","s4d","s3g","s7i"};
static const char *const cpr_pdcs[]={"rf","bb","rf","rf"};
const char *elden_wcn_cpr_rail_name(unsigned i){return i<4?cpr_rails[i]:NULL;}
const char *elden_wcn_cpr_pdc_name(unsigned i){return i<4?cpr_pdcs[i]:NULL;}
int elden_wcn_cpr_adjust(uint32_t value,unsigned ir,uint32_t *out){
    if(!out)return EldenWcnPowerArgument;
    if(value>UINT32_MAX-3)return EldenWcnPowerArgument;
    uint32_t rounded=(value+3)&~3u;
    if(rounded<16||rounded-16>UINT32_MAX-ir)return EldenWcnPowerArgument;
    *out=rounded-16+ir;return 0;
}
int elden_wcn_cpr_plan_details(const EldenWcnPmuParam *params,size_t count,EldenWcnPdcVote out[4],EldenWcnCprCounts *details){
    if(!params||!out||!count||count>16)return EldenWcnPowerArgument;
    EldenWcnPdcVote votes[4]={{0}};unsigned valid=0,mapped=0;
    for(size_t i=0;i<count;i++){
        const EldenWcnPmuParam *p=&params[i];size_t length=0;
        while(length<sizeof(p->pin)&&p->pin[length])length++;
        if(!length||length==sizeof(p->pin))return EldenWcnPowerArgument;
        if(!p->wake_valid&&!p->sleep_valid)continue;
        valid++;int rail=-1;
        for(unsigned n=0;n<sizeof(map)/sizeof(map[0]);n++)if(!strcmp(p->pin,map[n].pin))rail=(int)map[n].rail;
        if(rail<0)continue;
        uint32_t wake=0,sleep=0;
        if((p->wake_valid&&elden_wcn_cpr_adjust(p->wake,30,&wake))||
           (p->sleep_valid&&elden_wcn_cpr_adjust(p->sleep,10,&sleep)))return EldenWcnPowerArgument;
        if(p->wake_valid){votes[rail].wake_valid=true;if(wake>votes[rail].wake)votes[rail].wake=wake;}
        if(p->sleep_valid){votes[rail].sleep_valid=true;if(sleep>votes[rail].sleep)votes[rail].sleep=sleep;}
        mapped++;
    }
    if(valid&&!mapped)return EldenWcnPowerIdentity;
    memcpy(out,votes,sizeof(votes));
    if(details)*details=(EldenWcnCprCounts){valid,mapped,valid-mapped};
    return 0;
}
int elden_wcn_cpr_plan(const EldenWcnPmuParam *params,size_t count,EldenWcnPdcVote out[4]){
    return elden_wcn_cpr_plan_details(params,count,out,NULL);
}
static int message(char out[64],unsigned rail,bool wake,uint32_t value){
    if(rail>=4)return EldenWcnPowerArgument;
    const char *parts[]={"{class: wlan_pdc, ss: ",cpr_pdcs[rail],", res: ",cpr_rails[rail],".v, ",wake?"upval: ":"dwnval: "};
    char digits[10];unsigned count=0;do{digits[count++]=(char)('0'+value%10);value/=10;}while(value&&count<10);
    size_t n=0;
    for(unsigned i=0;i<sizeof(parts)/sizeof(parts[0]);++i){
        const char *part=parts[i];while(*part)out[n++]=*part++;
    }
    if(n+count+2>=64)return EldenWcnPowerArgument;
    while(count)out[n++]=digits[--count];
    out[n++]='}';out[n]=0;return 0;
}
int elden_wcn_power_cpr(EldenWcnPower *p,uint64_t epoch,const EldenWcnPmuParam *params,size_t count){
    if(elden_wcn_power_check(p,epoch,2))return EldenWcnPowerAgain;
    EldenWcnPdcVote votes[4];int rc=elden_wcn_cpr_plan(params,count,votes);if(rc)return rc;
    char commands[8][64];unsigned commands_count=0;
    for(unsigned i=0;i<4;i++){
        if(votes[i].wake_valid&&votes[i].wake){
            if((rc=message(commands[commands_count],i,true,votes[i].wake)))return rc;
            commands_count++;
        }
        if(votes[i].sleep_valid&&votes[i].sleep){
            if((rc=message(commands[commands_count],i,false,votes[i].sleep)))return rc;
            commands_count++;
        }
    }
    for(unsigned i=0;i<commands_count;i++){
        if((rc=p->io.qmp(p->io.context,commands[i])))return fail(p,rc,true);
        p->qmp_messages++;
    }
    return 0;
}
