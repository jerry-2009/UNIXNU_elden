/* SPDX-License-Identifier: BSD-3-Clause-Clear */
#include "DmaInspect.h"
static unsigned elden_ce3_inspected;
static void elden_ce3_inspect(struct ath12k_base *ab,u32 cmd_id)
{
    struct ath12k_ce_ring *ring;
    struct hal_srng *srng;
    u32 values[18], before, after;
    unsigned i, slot, pending;
    static const u32 offsets[]={0,4,8,0xc,0x10,0x1c,0x20,0x30,0x34,
        0x38,0x3c,0x40,0x44,0x48,0x50,0x400,0x404,0x4c};
    if(__atomic_exchange_n(&elden_ce3_inspected,1u,__ATOMIC_ACQ_REL))return;
    if(!ab||ab->hw_rev!=ATH12K_HW_PEACH_HW20||!ab->mem||!ab->hw_params||
       ab->hw_params->ce_count<=3||(ring=ab->ce.ce_pipe[3].src_ring)==NULL||
       ring->hal_ring_id>=HAL_SRNG_RING_ID_MAX||ring->nentries!=32||
       ring->nentries_mask!=31||ring->sw_index>=32||ring->write_index>=32)return;
    srng=&ab->hal.srng_list[ring->hal_ring_id];
    if(!srng->initialized||srng->ring_dir!=HAL_SRNG_DIR_SRC||
       srng->entry_size!=4||srng->ring_size!=128||
       srng->hwreg_base[0]!=0x1b86000U||srng->hwreg_base[1]!=0x1b86400U||
       !srng->ring_base_vaddr||!srng->u.src_ring.tp_addr)return;
    before=READ_ONCE(*srng->u.src_ring.tp_addr);
    for(i=0;i<18;i++)values[i]=ath12k_hif_read32(ab,0x1b86000U+offsets[i]);
    after=READ_ONCE(*srng->u.src_ring.tp_addr);
    ath12k_warn(ab,"ELDEN_CE3_INSPECT command=%x sw=%u write=%u hp=%u dma=%u/%u flags=%x\n",
        cmd_id,ring->sw_index,ring->write_index,srng->u.src_ring.hp,before,after,srng->flags);
    for(i=0;i<18;i+=3)
        ath12k_warn(ab,"ELDEN_CE3_REG off=%x/%x/%x val=%x/%x/%x\n",
            offsets[i],offsets[i+1],offsets[i+2],values[i],values[i+1],values[i+2]);
    pending=(ring->write_index-ring->sw_index)&31;
    if(pending>4)pending=4;
    for(i=0;i<pending;i++){
        struct sk_buff *skb;
        const volatile u32 *desc;
        u32 words[4],headers[4]={0};
        u64 addr;
        EldenWifiDmaInspect inspected={0};
        int rc;
        slot=(ring->sw_index+i)&31;skb=ring->skb[slot];
        desc=(const volatile u32 *)(srng->ring_base_vaddr+slot*4);
        words[0]=le32_to_cpu(desc[0]);words[1]=le32_to_cpu(desc[1]);
        words[2]=le32_to_cpu(desc[2]);words[3]=le32_to_cpu(desc[3]);
        addr=(u64)words[0]|((u64)(words[1]&255)<<32);
        if(!skb||!skb->data||skb->len<16||skb->len>4096)continue;
        rc=elden_wifi_dma_inspect(skb->data,ATH12K_SKB_CB(skb)->paddr,skb->len,&inspected);
        if(!rc){
            /* Fixed HTC/WMI/TLV headers only. No command values, frame data,
             * MAC/SSID/key/firmware bytes are read or logged. */
            const volatile u32 *h=(const volatile u32 *)skb->data;
            headers[0]=le32_to_cpu(h[0]);headers[1]=le32_to_cpu(h[1]);
            headers[2]=le32_to_cpu(h[2]);headers[3]=le32_to_cpu(h[3]);
        }
        ath12k_warn(ab,"ELDEN_CE3_DESC slot=%u words=%x/%x/%x/%x match=%u len=%u\n",
            slot,words[0],words[1],words[2],words[3],addr==ATH12K_SKB_CB(skb)->paddr,skb->len);
        ath12k_warn(ab,"ELDEN_CE3_MAP slot=%u rc=%d bus=%llx pa=%llx want=%llx par=%llx/%llx live=%u fault=%u/%u\n",
            slot,rc,(unsigned long long)inspected.mapped_bus,(unsigned long long)inspected.physical,
            (unsigned long long)inspected.expected_physical,(unsigned long long)inspected.par_read,
            (unsigned long long)inspected.par_write,inspected.live,inspected.smmu_fault,inspected.dma_error);
        ath12k_warn(ab,"ELDEN_CE3_HDR slot=%u htc=%x ctrl=%x command=%x tlv=%x\n",
            slot,headers[0],headers[1],headers[2],headers[3]);
    }
}
