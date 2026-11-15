/* SPDX-License-Identifier: GPL-2.0-only */
/* Native bridge for the exact TB322FC Peach Linux QMI callback. The Linux
 * consumer pointer is an identity token, never interpreted as an XNU object.
 * No regulator computation or unconditional successful fallback lives here. */
#include <linux/pwrseq/qcom_wcn.h>
#include <stddef.h>
#include "QmiPowerBinding.h"
#include "WlanPower.h"

_Static_assert(PWRSEQ_QCOM_WCN_PMU_PIN_NAME_LEN==32,"PMU name ABI");
_Static_assert(PWRSEQ_QCOM_WCN_PMU_MAX_PARAMS==16,"PMU count ABI");
_Static_assert(sizeof(struct pwrseq_qcom_wcn_pmu_param)==48,"PMU item ABI");
_Static_assert(offsetof(struct pwrseq_qcom_wcn_pmu_param,wake_volt_valid)==32,"PMU wake-valid ABI");
_Static_assert(offsetof(struct pwrseq_qcom_wcn_pmu_param,wake_volt)==36,"PMU wake ABI");
_Static_assert(offsetof(struct pwrseq_qcom_wcn_pmu_param,sleep_volt_valid)==40,"PMU sleep-valid ABI");
_Static_assert(offsetof(struct pwrseq_qcom_wcn_pmu_param,sleep_volt)==44,"PMU sleep ABI");

static struct {
    struct device *consumer;
    const void *provider;
    uint64_t epoch;
    unsigned busy;
} binding;

static int enter(void){
    unsigned expected=0;
    return __atomic_compare_exchange_n(&binding.busy,&expected,1,false,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)?0:-11;
}
static int leave(int rc){__atomic_store_n(&binding.busy,0,__ATOMIC_RELEASE);return rc;}

int elden_wlan_qmi_bind(struct device *consumer,const void *provider,uint64_t epoch){
    if(!consumer||!provider||!epoch)return -22;
    int rc=enter();if(rc)return rc;
    if(binding.consumer&&(binding.consumer!=consumer||binding.provider!=provider||binding.epoch!=epoch))
        return leave(-16);
    rc=elden_wlan_power_ready(provider,epoch);
    if(!rc){binding.consumer=consumer;binding.provider=provider;binding.epoch=epoch;}
    return leave(rc);
}
int elden_wlan_qmi_unbind(struct device *consumer,const void *provider,uint64_t epoch){
    if(!consumer||!provider||!epoch)return -22;
    int rc=enter();if(rc)return rc;
    if(binding.consumer!=consumer||binding.provider!=provider||binding.epoch!=epoch)return leave(-19);
    binding.consumer=NULL;binding.provider=NULL;binding.epoch=0;return leave(0);
}
int pwrseq_qcom_wcn_set_ol_cpr(struct device *consumer,
                            const struct pwrseq_qcom_wcn_pmu_param *params,size_t count){
    if(!consumer||!params||!count||count>PWRSEQ_QCOM_WCN_PMU_MAX_PARAMS)return -22;
    int rc=enter();if(rc)return rc;
    if(binding.consumer!=consumer||!binding.provider||!binding.epoch)return leave(-19);
    rc=elden_wlan_power_ready(binding.provider,binding.epoch);
    if(rc)return leave(rc);
    EldenWcnPmuParam converted[PWRSEQ_QCOM_WCN_PMU_MAX_PARAMS]={0};
    for(size_t i=0;i<count;i++){
        for(size_t n=0;n<PWRSEQ_QCOM_WCN_PMU_PIN_NAME_LEN;n++)converted[i].pin[n]=(char)params[i].pin_name[n];
        converted[i].pin[PWRSEQ_QCOM_WCN_PMU_PIN_NAME_LEN]=0;
        converted[i].wake=params[i].wake_volt;converted[i].sleep=params[i].sleep_volt;
        converted[i].wake_valid=params[i].wake_volt_valid!=0;
        converted[i].sleep_valid=params[i].sleep_volt_valid!=0;
    }
    /* The native entry rechecks the lease under its own transaction gate, so
     * stop between the check above and dispatch cannot authorize stale I/O. */
    return leave(elden_wlan_power_cpr(binding.provider,binding.epoch,converted,count));
}
