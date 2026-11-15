/* SPDX-License-Identifier: GPL-2.0-only */
/* Runs the real Linux-facing callback through native WLAN/core/QMP recorder. */
static struct device *consumer=(struct device *)0x5678;
static struct pwrseq_qcom_wcn_pmu_param pmu(const char *name,unsigned wake=900,unsigned sleep=820){
    struct pwrseq_qcom_wcn_pmu_param p={};CHECK(strlen(name)<sizeof(p.pin_name));
    memcpy(p.pin_name,name,strlen(name));p.wake_volt_valid=1;p.sleep_volt_valid=1;p.wake_volt=wake;p.sleep_volt=sleep;return p;
}
static void reenter_qmi(){
    auto param=pmu("VDDD_AON_0P9");unsigned before=active->qmp_calls;
    CHECK(elden_wlan_qmi_unbind(consumer,identity.provider,wlan_epoch)==-11);
    CHECK(pwrseq_qcom_wcn_set_ol_cpr(consumer,&param,1)==-11);
    CHECK(active->qmp_calls==before);
}
static void qmi_cases(){
    reset();auto param=pmu("VDDD_AON_0P9");uint64_t epoch=0;
    CHECK(pwrseq_qcom_wcn_set_ol_cpr(consumer,&param,1)==-19);
    CHECK(elden_wlan_qmi_bind(consumer,identity.provider,1)==-11);
    CHECK(!elden_wlan_power_acquire(&identity,&epoch));
    CHECK(elden_wlan_qmi_bind(consumer,(void *)0x9999,epoch)==-11);
    CHECK(!elden_wlan_qmi_bind(consumer,identity.provider,epoch));
    CHECK(!elden_wlan_qmi_bind(consumer,identity.provider,epoch));
    CHECK(elden_wlan_qmi_bind((struct device *)0x9999,identity.provider,epoch)==-16);
    unsigned q=active->qmp_calls;
    CHECK(pwrseq_qcom_wcn_set_ol_cpr(nullptr,&param,1)==-22);
    CHECK(pwrseq_qcom_wcn_set_ol_cpr(consumer,nullptr,1)==-22);
    CHECK(pwrseq_qcom_wcn_set_ol_cpr(consumer,&param,0)==-22);
    CHECK(pwrseq_qcom_wcn_set_ol_cpr(consumer,&param,17)==-22);
    CHECK(pwrseq_qcom_wcn_set_ol_cpr((struct device *)0x9999,&param,1)==-19);
    CHECK(active->qmp_calls==q);
    param.wake_volt_valid=7;param.sleep_volt_valid=2;qmp_hook=reenter_qmi;
    CHECK(!pwrseq_qcom_wcn_set_ol_cpr(consumer,&param,1));qmp_hook=nullptr;
    CHECK(active->qmp_calls==q+2&&strstr(active->qmp_messages[q],"upval: 914")&&strstr(active->qmp_messages[q+1],"dwnval: 814"));
    q=active->qmp_calls;param.wake_volt=UINT32_MAX;
    CHECK(pwrseq_qcom_wcn_set_ol_cpr(consumer,&param,1)==-22&&active->qmp_calls==q);
    memset(param.pin_name,'A',sizeof(param.pin_name));param.wake_volt=900;
    CHECK(pwrseq_qcom_wcn_set_ol_cpr(consumer,&param,1)==-19&&active->qmp_calls==q);
    param.pin_name[0]=0;
    CHECK(pwrseq_qcom_wcn_set_ol_cpr(consumer,&param,1)==-22&&active->qmp_calls==q);
    auto all=pmu("VDDD_AON_0P9");struct pwrseq_qcom_wcn_pmu_param max[16];
    for(unsigned i=0;i<16;i++){max[i]=all;max[i].wake_volt+=i*4;}
    CHECK(!pwrseq_qcom_wcn_set_ol_cpr(consumer,max,16));
    CHECK(strstr(active->qmp_messages[active->qmp_calls-2],"upval: 974"));
    CHECK(elden_wlan_qmi_unbind(consumer,identity.provider,epoch+1)==-19);
    CHECK(!elden_wlan_power_stop(identity.provider,epoch));q=active->qmp_calls;
    CHECK(pwrseq_qcom_wcn_set_ol_cpr(consumer,&all,1)==-11&&active->qmp_calls==q);
    CHECK(!elden_wlan_qmi_unbind(consumer,identity.provider,epoch));
    CHECK(!elden_wlan_power_acquire(&identity,&epoch)&&epoch==2);
    CHECK(!elden_wlan_qmi_bind(consumer,identity.provider,epoch));
    CHECK(!pwrseq_qcom_wcn_set_ol_cpr(consumer,&all,1));
    CHECK(!elden_wlan_qmi_unbind(consumer,identity.provider,epoch));scenarios++;
    for(unsigned at=1;at<=8;at++){
        reset();CHECK(!elden_wlan_power_acquire(&identity,&epoch));
        CHECK(!elden_wlan_qmi_bind(consumer,identity.provider,epoch));
        struct pwrseq_qcom_wcn_pmu_param four[]={pmu("VDDD_AON_0P9"),pmu("VDDD_WLMX_0P9"),pmu("VDDA_RFA_1P9",1900,1800),pmu("VDDA_RFA_1P3",1300,1200)};
        active->qmp_fail_at=active->qmp_calls+at;
        CHECK(pwrseq_qcom_wcn_set_ol_cpr(consumer,four,4)==-5);
        CHECK(active->shared.held&&active->qmp_calls==active->qmp_fail_at);
        q=active->qmp_calls;CHECK(pwrseq_qcom_wcn_set_ol_cpr(consumer,four,4)==-11&&active->qmp_calls==q);
        CHECK(!elden_wlan_qmi_unbind(consumer,identity.provider,epoch));scenarios++;
    }
}
