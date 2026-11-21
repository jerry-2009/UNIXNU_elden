/* SPDX-License-Identifier: BSD-3-Clause-Clear */
#include "ModeResponse.h"
#include "hif.h"
#include "wifi7/hal.h"
enum {EmrResponse=0x5253504d,EmrRefused=0x52454655,EmrRingActual=0x52494e47,
      EmrRingExpected=0x45585043,EmrPointer=0x50545253,EmrCpuMap=0x4350554d};
static void emr_event(struct ath12k_base *ab,struct sk_buff *skb,u32 id)
{
    if(id!=WMI_PDEV_SET_HW_MODE_RESP_EVENTID)return;
    EldenWifiModeResponse result={};
    int rc=skb->len<sizeof(struct wmi_cmd_hdr)?-71:
        emr_parse(skb->data+sizeof(struct wmi_cmd_hdr),skb->len-sizeof(struct wmi_cmd_hdr),
                  WMI_TAG_PDEV_SET_HW_MODE_RESPONSE_EVENT,&result);
    if(rc)elden_wifi_ce3_flow_note(ab,EcfWmiRequest,skb->len,result.tag,EmrRefused,result.length,result.reason);
    else elden_wifi_ce3_flow_note(ab,EcfWmiRequest,result.status,result.configured_mode,
                                  EmrResponse,result.pdev,result.mappings);
}
static u64 emr_par(uintptr_t address)
{
#ifdef EMR_HOST_TEST
    return emr_host_par(address);
#else
    u64 daif,saved,result;
    __asm__ volatile("mrs %0,daif\n\tmsr daifset,#2\n\tmrs %1,par_el1\n\tat s1e1r,%3\n\tisb\n\tmrs %2,par_el1\n\tmsr par_el1,%1\n\tmsr daif,%0"
        :"=&r"(daif),"=&r"(saved),"=&r"(result):"r"(address):"memory");
    return result;
#endif
}
static void emr_ring(struct ath12k_base *ab)
{
    if(!ab||!ab->mem||!ab->hw_params||ab->hw_params->ce_count<=3||!ab->ce.ce_pipe[3].src_ring)return;
    u32 id=ab->ce.ce_pipe[3].src_ring->hal_ring_id;
    if(id>=HAL_SRNG_RING_ID_MAX)return;
    struct hal_srng *ring=&ab->hal.srng_list[id];struct ath12k_hal *hal=&ab->hal;
    u32 base=ring->hwreg_base[HAL_SRNG_REG_GRP_R0];
    if(!ring->initialized||ring->ring_dir!=HAL_SRNG_DIR_SRC||!ring->u.src_ring.tp_addr||
       !hal->rdp.vaddr||(base&3)||base>0xffffffffU-0x1000U)return;
    u32 offsets[]={0,(u32)HAL_TCL1_RING_BASE_MSB_OFFSET(hal),(u32)HAL_TCL1_RING_MISC_OFFSET(hal),
        (u32)HAL_TCL1_RING_ID_OFFSET(hal),(u32)HAL_TCL1_RING_TP_ADDR_LSB_OFFSET(hal),
        (u32)HAL_TCL1_RING_TP_ADDR_MSB_OFFSET(hal)};
    for(unsigned i=0;i<6;i++)if((offsets[i]&3)||offsets[i]>0x100U)return;
    u32 low=ath12k_hif_read32(ab,base);
    u32 high=ath12k_hif_read32(ab,base+offsets[1]);
    u32 misc=ath12k_hif_read32(ab,base+offsets[2]);
    u32 ident=ath12k_hif_read32(ab,base+offsets[3]);
    u32 tp_low=ath12k_hif_read32(ab,base+offsets[4]);
    u32 tp_high=ath12k_hif_read32(ab,base+offsets[5]);
    elden_wifi_ce3_flow_note(ab,EcfWmiRequest,low,high,EmrRingActual,misc,ident);
    u32 expected_high=u32_encode_bits((u64)ring->ring_base_paddr>>HAL_ADDR_MSB_REG_SHIFT,
        HAL_TCL1_RING_BASE_MSB_RING_BASE_ADDR_MSB)|
        u32_encode_bits(ring->entry_size*ring->num_entries,HAL_TCL1_RING_BASE_MSB_RING_SIZE);
    elden_wifi_ce3_flow_note(ab,EcfWmiRequest,ring->ring_base_paddr,
        expected_high,EmrRingExpected,u32_encode_bits(ring->entry_size,HAL_REO1_RING_ID_ENTRY_SIZE),base);
    u64 expected_tp=hal->rdp.paddr+((uintptr_t)ring->u.src_ring.tp_addr-(uintptr_t)hal->rdp.vaddr);
    elden_wifi_ce3_flow_note(ab,EcfWmiRequest,tp_low,tp_high,EmrPointer,expected_tp,HAL_TCL1_RING_MISC_SRNG_ENABLE);
    uintptr_t shadow=(uintptr_t)ring->u.src_ring.hp_addr;
    if(shadow>=(uintptr_t)ab->mem&&shadow-(uintptr_t)ab->mem<0x80000)
        elden_wifi_ce3_flow_note(ab,EcfWmiRequest,emr_par(shadow),shadow,EmrCpuMap,
            shadow-(uintptr_t)ab->mem,0);
}
