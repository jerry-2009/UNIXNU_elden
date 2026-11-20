/* SPDX-License-Identifier: BSD-3-Clause-Clear */
/* Passive bounded timeline of CE3 setup/state. Not a firmware response trace. */
#include "Ce3Timeline.h"
static unsigned elden_ce3_timeline_count;
void elden_ce3_timeline(struct ath12k_base *ab,u32 stage,int32_t result)
{
    struct ath12k_ce_ring *ring;
    struct hal_srng *s;
    u32 base,size,id,misc,hp,tp,window,wake,scratch;
    if(!ab||ab->hw_rev!=ATH12K_HW_PEACH_HW20||!ab->mem||!ab->hw_params||
       ab->hw_params->ce_count<=3||!ab->ce.ce_pipe[3].src_ring)return;
    if(__atomic_fetch_add(&elden_ce3_timeline_count,1u,__ATOMIC_ACQ_REL)>=16)return;
    ring=ab->ce.ce_pipe[3].src_ring;
    if(ring->hal_ring_id>=HAL_SRNG_RING_ID_MAX)return;
    s=&ab->hal.srng_list[ring->hal_ring_id];
    if(!s->initialized||s->entry_size!=4||s->ring_size!=128||
       s->hwreg_base[0]!=0x1b86000||s->hwreg_base[1]!=0x1b86400)return;
    wake=ath12k_hif_read32(ab,0x3004);scratch=ath12k_hif_read32(ab,0x1e04040);
    base=ath12k_hif_read32(ab,0x1b86000);size=ath12k_hif_read32(ab,0x1b86004);
    id=ath12k_hif_read32(ab,0x1b86008);misc=ath12k_hif_read32(ab,0x1b86010);
    hp=ath12k_hif_read32(ab,0x1b86400);tp=ath12k_hif_read32(ab,0x1b86404);
    /* Read only the always-accessible remap control as an address witness. */
    window=ath12k_hif_read32(ab,0x3278);
    ath12k_warn(ab,"ELDEN_CE3_TIME stage=%u rc=%d base=%x size=%x id=%x misc=%x hw=%x/%x win=%x wake=%x/%x sw=%u/%u\n",
        stage,result,base,size,id,misc,hp,tp,window,wake,scratch,s->u.src_ring.hp,
        READ_ONCE(*s->u.src_ring.tp_addr));
}
