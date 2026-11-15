/* SPDX-License-Identifier: GPL-2.0-only */
/* Only SPMI/RSC physical transactions/log output are modeled. */
static void log(const char *,...){}
static int fresh_fault;
static bool ml_at_interrupt_context(){return fresh_fault==1;}
static int elden_recovery_rpc_ready(){return fresh_fault!=2;}
static unsigned elden_recovery_deadline_remaining(){return fresh_fault==3?59:300;}
static unsigned elden_charge_policy_ready(){return fresh_fault!=4;}
static bool elden_battery_temperature_get(int *t,uint32_t *e,uint32_t *cycle){
    *t=fresh_fault==5?3801:2500;*e=fresh_fault==7?2:1;*cycle=1;return fresh_fault!=6;
}
static int pb_spmi_find(Ignored *,unsigned ppid,int *owner){*owner=0;return ppid==0x5c1?0:ppid==0x6c3?1:-19;}
static int pb_spmi_read8(Ignored *io,int apid,uint8_t reg,uint8_t *value){
    auto c=static_cast<Context *>(io->ctx);CHECK(apid==0||apid==1);
    if(++c->root_reads==c->root_fail_read)return -5;
    auto r=c->root_rails[apid];if(c->root_bad_after&&c->root_sends)r.mode=3;
    switch(reg){case 4:*value=r.type;break;case 5:*value=r.subtype;break;case 8:*value=r.status;break;
        case 0x40:*value=(uint8_t)r.mv;break;case 0x41:*value=(uint8_t)(r.mv>>8);break;
        case 0x45:*value=r.mode;break;case 0x46:*value=r.enable;break;default:CHECK(false);}
    return 0;
}
extern "C" int Sm8750RpmhWriteActive(const Sm8750RpmhIo *io,const Sm8750RpmhCmd *cmd,unsigned n,uint32_t waits,Sm8750RpmhResult *result){
    auto c=static_cast<Context *>(io->context);c->root_sends++;
    CHECK(n==10&&waits==0x3ff);
    CHECK(cmd[0].addr==0x30000&&cmd[0].data==3&&cmd[1].addr==0x30100&&cmd[1].data==3);
    CHECK(cmd[8].addr==0x50000&&cmd[8].data==0x6fffffff&&cmd[9].addr==0x50100&&cmd[9].data==0x60000001);
    result->step=c->root_fail_step?c->root_fail_step:unsigned(Sm8750RpmhStepDone);
    if(c->root_fail_step)return -110;
    if(fresh_fault==8)fresh_fault=7;
    for(unsigned i=0;i<2;i++){
        CHECK(cmd[2+3*i].addr==0x41000+i*0x100&&cmd[3+3*i].data==7&&cmd[4+3*i].data==1);
        c->root_rails[i].mv=(uint16_t)cmd[2+3*i].data;c->root_rails[i].mode=7;c->root_rails[i].status|=0x80;c->root_rails[i].enable|=0x80;
    }
    return 0;
}
