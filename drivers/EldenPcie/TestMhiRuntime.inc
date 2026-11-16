/* SPDX-License-Identifier: GPL-2.0-only */
static void reset_runtime(){
    reset();runtime_context=nullptr;fw_loaded=fw_stops=step_calls=scan_calls=stop_calls=irq_bits=preempt_depth=0;
    fw_error=start_error=0;hang_reset=bad_bar=hold_transactions=false;reset_due=0;
    memset(mhi_bar,0,sizeof(mhi_bar));active->bar0_map.data=mhi_bar;active->bar0_map.va=(uintptr_t)mhi_bar;
    active->endpoint.bars[0].bytes=0x200000;active->endpoint.bars[0].address=0x40400000;nw_wifi_stats={};platform_api=nullptr;board_api=nullptr;
}
int main(){
    reset_runtime();transport_run(active);CHECK(active->transport_ready);
    CHECK(elden_wifi_runtime_enable_master()==-19);runtime_run(active);
    CHECK(active->runtime_entered&&active->runtime_returned&&active->runtime_quiesced&&active->runtime_stage==6);
    CHECK(!active->runtime_error&&!active->runtime_consumer&&active->msi.state==EldenMsiStopped);
    CHECK(active->mhi_stop.reset_requested&&active->mhi_stop.reset_observed&&active->mhi_stop.master_off&&active->mhi_stop.transactions_idle);
    CHECK((cfg[1]&7)==2&&(cfg[1]&0xffff0000u)==0xa5000000u&&stop_calls==1&&scan_calls==1&&irq_bits==3&&!preempt_depth);
    CHECK(!active->transport_ready&&elden_wifi_runtime_enable_master()==-19);
    EldenPcieTransportStatus snapshot={};CHECK(!transport_snapshot(active,&snapshot)&&!snapshot.ready);
    powered=false;CHECK(transport_stop(active,clock_us+10000)==0);
    reset_runtime();transport_run(active);fw_error=-74;runtime_run(active);
    CHECK(active->runtime_error==-74&&!active->runtime_entered&&!active->config.master_attempted&&(cfg[1]&7)==2);
    reset_runtime();transport_run(active);start_error=-5;runtime_run(active);
    CHECK(active->runtime_start_error==-5&&active->runtime_error==-5&&stop_calls==1&&!active->config.master_attempted&&active->runtime_quiesced);
    reset_runtime();transport_run(active);hang_reset=true;runtime_run(active);
    CHECK(active->runtime_stop_error==-110&&!active->runtime_quiesced&&active->msi.state!=EldenMsiStopped);
    CHECK(transport_stop(active,clock_us+10000)!=0);
    reset_runtime();transport_run(active);bad_bar=true;runtime_run(active);
    CHECK(active->runtime_stop_error==-5&&!active->runtime_quiesced);
    reset_runtime();transport_run(active);hold_transactions=true;runtime_run(active);
    CHECK(active->runtime_stop_error==-110&&!active->runtime_quiesced&&active->mhi_stop.master_off==0);
    CHECK((cfg[1]&7)==2); // PCI master disabled, but still no whole-stop acceptance
    printf("%u native MHI runtime scenarios / %u checks passed; actual QMI binding/config/MSI/reset code, Linux runtime and hardware modeled\n",cases,checks);
}
