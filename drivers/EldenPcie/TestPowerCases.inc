/* SPDX-License-Identifier: GPL-2.0-only */
static void power_cases(){
    for(int fault=1;fault<=6;fault++){
        reset();uint64_t epoch=0;CHECK(!elden_wlan_power_acquire(&identity,&epoch));full_on_enable=1;fresh_fault=fault;
        CHECK(elden_wlan_root_power(identity.provider,epoch,3)==-11&&!active->root_reads&&!active->root_sends);scenarios++;
    }
    reset();uint64_t epoch=0;CHECK(!elden_wlan_power_acquire(&identity,&epoch));
    CHECK(elden_wlan_root_power(identity.provider,epoch,3)==-11&&!active->root_reads&&!active->root_sends);
    full_on_enable=1;CHECK(!elden_wlan_root_power(identity.provider,epoch,3));
    CHECK(root_power_epoch==epoch&&active->root_sends==1&&root_power_plan.mx_level==384&&root_power_plan.cx_level==384);
    CHECK(root_power_plan.sn4_minimum==2000&&root_power_plan.sn4_applied==16383);
    CHECK(!elden_wlan_root_power(identity.provider,epoch,3)&&active->root_sends==1);
    CHECK(elden_wlan_root_power(identity.provider,epoch,2)==-22);
    CHECK(elden_wlan_root_power((void *)0x9999,epoch,3)==-11&&active->root_sends==1);scenarios++;
    active->spmi_uncertain=true;CHECK(elden_wlan_root_power(identity.provider,epoch,3)==-71&&active->root_sends==1);scenarios++;
    for(unsigned at=1;at<=28;at++){
        reset();CHECK(!elden_wlan_power_acquire(&identity,&epoch));full_on_enable=1;active->root_fail_read=at;
        CHECK(elden_wlan_root_power(identity.provider,epoch,3)==-5&&!root_power_epoch);
        CHECK(active->root_sends==(at>14?1u:0u));
        unsigned sends=active->root_sends;CHECK(elden_wlan_root_power(identity.provider,epoch,3)<0&&sends==active->root_sends);scenarios++;
    }
    const unsigned steps[]={Sm8750RpmhStepSelect,Sm8750RpmhStepProgram,Sm8750RpmhStepPoll};
    for(unsigned step:steps){
        reset();CHECK(!elden_wlan_power_acquire(&identity,&epoch));full_on_enable=1;active->root_fail_step=step;
        CHECK(elden_wlan_root_power(identity.provider,epoch,3)==-110&&!root_power_epoch);
        CHECK(root_power_held==(step>=Sm8750RpmhStepProgram));scenarios++;
    }
    reset();CHECK(!elden_wlan_power_acquire(&identity,&epoch));full_on_enable=1;active->root_bad_after=true;
    CHECK(elden_wlan_root_power(identity.provider,epoch,3)==-19&&root_power_held&&!root_power_epoch);scenarios++;
    reset();CHECK(!elden_wlan_power_acquire(&identity,&epoch));full_on_enable=1;fresh_fault=8;
    CHECK(elden_wlan_root_power(identity.provider,epoch,3)==-11&&root_power_held&&!root_power_epoch&&active->root_sends==1);scenarios++;
    reset();CHECK(!elden_wlan_power_acquire(&identity,&epoch));
    EldenPciePowerPlan plan;memset(&plan,0xa5,sizeof(plan));EldenPciePowerPlan saved=plan;
    CHECK(elden_pcie_power_plan(&active->db,active->root_rails,nullptr,3,0,&plan)==-95&&!memcmp(&plan,&saved,sizeof(plan)));
    for(unsigned kind=0;kind<5;kind++){
        test_power_db(&active->db);auto old=active->root_rails[0];
        if(kind==0)active->db.snapshot[4]=0;
        if(kind==1)active->root_rails[0].mv=921;
        if(kind==2)active->root_rails[0].subtype=0;
        if(kind==3)fixture16(active->db.snapshot+144+0x800+6,128);
        if(kind==4)fixture32(active->db.snapshot+144+0x300+16,0x30100);
        CHECK(elden_pcie_power_plan(&active->db,active->root_rails,nullptr,3,1,&plan)<0&&!memcmp(&plan,&saved,sizeof(plan)));
        active->root_rails[0]=old;scenarios++;
    }
    test_power_db(&active->db);uint16_t retained[]={920,1256};
    active->db.snapshot[144+0xa00+6]=255;
    CHECK(!elden_pcie_power_plan(&active->db,active->root_rails,retained,3,1,&plan));
    CHECK(plan.rail_mv[0]==920&&plan.rail_mv[1]==1256&&plan.commands[2].data==920&&plan.commands[5].data==1256&&plan.sn4_vcd==255);scenarios++;
}
