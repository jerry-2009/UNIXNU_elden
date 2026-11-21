/* SPDX-License-Identifier: GPL-2.0-only */
/* In the shared WCN native namespace, using its existing serialized SPMI/RSC. */
static EldenPciePowerPlan root_power_plan;
static uint64_t root_power_epoch;
static bool root_power_held;
static bool root_power_fresh(uint32_t expected=0,uint32_t *epoch=nullptr){
    if(ml_at_interrupt_context()||!elden_recovery_rpc_ready()||elden_recovery_deadline_remaining()<60||!elden_charge_policy_ready())return false;
    int temperature=0;uint32_t e=0,cycle=0;
    if(!elden_battery_temperature_get(&temperature,&e,&cycle)||!e||!cycle||temperature<500||temperature>3800||(expected&&expected!=e))return false;
    if(epoch)*epoch=e;return true;
}
static int read_root_rail(Context *c,unsigned i,EldenPcieRail *out){
    static const unsigned ppid[2]={0x5c1,0x6c3};
    static const uint8_t registers[]={4,5,8,0x40,0x41,0x45,0x46};
    if(i>=2||c->spmi_uncertain)return -71;
    int owner=-1,apid=pb_spmi_find(&c->spmi,ppid[i],&owner);if(apid<0)return apid;
    uint8_t values[7]={};
    for(unsigned n=0;n<7;n++){
        int rc=pb_spmi_read8(&c->spmi,apid,registers[n],&values[n]);
        if(rc){log("\nELDEN_PCIE_POWER read rail=%u ppid=%03x reg=%02x rc=%d\n",i,ppid[i],registers[n],rc);c->spmi_uncertain=true;return rc;}
    }
    *out={(uint16_t)(values[3]|(uint16_t)values[4]<<8),values[0],values[1],values[2],values[6],values[5]};
    return 0;
}
static int root_power_prepare(Context *c,uint64_t epoch,unsigned max_gen){
    uint32_t battery_epoch=0;if(!root_power_fresh(0,&battery_epoch))return -11;
    if(root_power_held||c->rsc_uncertain||c->spmi_uncertain)return -71;
    if(root_power_epoch==epoch)return root_power_plan.max_gen==max_gen?0:-22;
    /* Epoch changes are a new WLAN cold start, but retained votes/maps remain. */
    EldenPcieRail before[2]={};int rc;
    for(unsigned i=0;i<2;i++){
        if((rc=read_root_rail(c,i,&before[i])))return rc;
        log("\nELDEN_PCIE_POWER before rail=%u type=%02x/%02x mv=%u mode=%02x status=%02x enable=%02x\n",
            i,before[i].type,before[i].subtype,before[i].mv,before[i].mode,before[i].status,before[i].enable);
    }
    EldenPciePowerPlan plan={};
    rc=elden_pcie_power_plan(&c->db,before,root_power_epoch?root_power_plan.rail_mv:nullptr,max_gen,EldenPciePowerFullOnDiagnostic,&plan);
    if(rc){log("\nELDEN_PCIE_POWER plan rc=%d\n",rc);return rc;}
    if(!root_power_fresh(battery_epoch))return -11;
    Sm8750RpmhResult result={};
    rc=Sm8750RpmhWriteActive(&c->rpmh,plan.commands,plan.count,plan.wait_mask,&result);
    log("\nELDEN_PCIE_POWER result=%d stage=%u tcs=%u mx=%u/%u cx=%u/%u SN4=%u min=%u full-on=1\n",
        rc,result.step,result.tcs,plan.mx_index,plan.mx_level,plan.cx_index,plan.cx_level,plan.sn4_applied,plan.sn4_minimum);
    if(rc){if(result.step>=Sm8750RpmhStepProgram){c->rsc_uncertain=true;root_power_held=true;}return rc;}
    if(!root_power_fresh(battery_epoch)){root_power_held=true;return -11;}
    for(unsigned i=0;i<2;i++){
        EldenPcieRail after={};rc=read_root_rail(c,i,&after);
        if(!rc&&(after.type!=4||after.subtype!=0xad||!(after.status&0x80)||!(after.enable&0x80)||
                 (after.mode&7)!=7||after.mode==0xee||after.mv<plan.rail_mv[i]||after.mv>(i?1256:920)))rc=-19;
        log("\nELDEN_PCIE_POWER rail=%u rc=%d mv=%u mode=%02x status=%02x enable=%02x\n",i,rc,after.mv,after.mode,after.status,after.enable);
        if(rc){root_power_held=true;return rc;}
    }
    root_power_plan=plan;root_power_epoch=epoch;return 0;
}
