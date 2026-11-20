/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Included in hash-bound ath12k/core.c. Original QMI firmware, MSI and native
 * lifecycle stay in place; only the explicit Peach trial selects this path.
 */
#include "PortableApi.h"
#include "nw_abi.h"
extern const struct lx_platform *lx_plat;
extern void nw_board_mac(u8 *);
static struct ath12k_base *elden_portable_owner;
static unsigned elden_portable_started,elden_portable_stopped;
static int elden_portable_error;
static uint64_t elden_portable_report_at;
static struct EldenPortableStatus elden_portable_state;
static void *elden_portable_cpu;
static uint64_t elden_portable_bus;

static u32 elden_portable_read(void *owner,u32 offset) {
    struct ath12k_base *ab=owner;
    if(ab!=elden_portable_owner)return UINT32_MAX;
    return ath12k_hif_read32(ab,offset);
}
static void elden_portable_write(void *owner,u32 offset,u32 value) {
    struct ath12k_base *ab=owner;
    if(ab!=elden_portable_owner)return;
    ath12k_hif_write32(ab,offset,value);
}
static void elden_portable_note(void *owner,int step,const char *what) {
    struct ath12k_base *ab=owner;
    if(ab==elden_portable_owner)
        ath12k_warn(ab,"ELDEN_PORTABLE step=%d %s\n",step,what);
}
int elden_wifi_portable_begin(void *owner) {
    struct ath12k_base *ab=owner;
    struct EldenPortableIo io;
    u8 mac[6];int rc;
    if(!elden_wifi_portable_requested()||!ab||ab->hw_rev!=ATH12K_HW_PEACH_HW20||
       ab->qmi.target.soc_id!=0x40210200||
       !ab->mem||ab->mem_len<0x100000||!lx_plat||!lx_plat->dma_alloc||
       !lx_plat->now_ms)return -19;
    if(elden_portable_owner)return -16;
    elden_portable_owner=ab;
    /* No QMI shadow table is advertised for the donor's direct CSR rings. */
    ab->qmi.ce_cfg.shadow_reg_v3=NULL;ab->qmi.ce_cfg.shadow_reg_v3_len=0;
    rc=ath12k_qmi_firmware_start(ab,ab->fw_mode);
    if(rc)goto fail;
    elden_portable_cpu=lx_plat->dma_alloc(4u<<20,&elden_portable_bus);
    if(!elden_portable_cpu){rc=-ENOMEM;goto fail;}
    nw_board_mac(mac);
    if(!is_valid_ether_addr(mac)){rc=-EINVAL;goto fail;}
    io=(struct EldenPortableIo){ab,elden_portable_read,elden_portable_write,elden_portable_note};
    rc=elden_wifi_portable_prepare(&io,elden_portable_cpu,elden_portable_bus,4u<<20,mac,lx_plat->now_ms());
    if(rc)goto fail;
    elden_portable_started=1;nw_wifi_stats.stage=3;
    ath12k_warn(ab,"ELDEN_PORTABLE begin=0 bytes=4194304 iova=%llx firmware=OEM direct-CE scan-only; no station/net claim\n",
                (unsigned long long)elden_portable_bus);
    return 0;
fail:
    elden_portable_error=rc;nw_wifi_stats.last_err=rc;
    ath12k_warn(ab,"ELDEN_PORTABLE begin=%d retained-to-reset\n",rc);
    return rc;
}
int elden_wifi_portable_bss_count(void) {
    return elden_portable_started?(int)elden_portable_state.bss:-1;
}
int elden_wifi_portable_runtime_step(void) {
    int rc;uint64_t now;
    if(!elden_portable_started||elden_portable_stopped)return 0;
    now=lx_plat->now_ms();
    rc=elden_wifi_portable_tick(elden_portable_owner,now,&elden_portable_state);
    if(rc){elden_portable_error=rc;nw_wifi_stats.last_err=rc;}
    if(now>=elden_portable_report_at){
        const struct EldenPortableStatus *s=&elden_portable_state;
        ath12k_warn(elden_portable_owner,"ELDEN_PORTABLE state=%d error=%d ready=%u commands=%u events=%u credits=%u wait=%u\n",
            s->step,rc?rc:s->error,s->ready,s->commands,s->events,s->credit_reports,s->credit_waits);
        ath12k_warn(elden_portable_owner,"ELDEN_PORTABLE scan=%u started=%u completed=%u bss=%u mgmt=%u htt=%u CE=%u/%u/%u dropped=%u\n",
            s->scans,s->started,s->completed,s->bss,s->management_frames,s->htt_announced,
            s->ce_sent,s->ce_received,s->ce_completions,s->ce_dropped);
        elden_portable_report_at=now+1000;
    }
    /* The original cfg80211/iPadOS bridge has no invented station. */
    nw_wifi_stats.bss_seen=elden_portable_state.bss;
    nw_wifi_stats.scans=elden_portable_state.completed;
    return !rc;
}
int elden_wifi_portable_runtime_stop(void) {
    uint64_t end;unsigned attempts=0;int result=0;
    if(!elden_portable_started||elden_portable_stopped)return 0;
    end=lx_plat->now_ms()+500;
    do {
        result=elden_wifi_portable_stop_tick(elden_portable_owner,lx_plat->now_ms());
        if(result)break;
        if(lx_plat->poll)lx_plat->poll();
        lx_plat->sleep_ms(1);
    }while(lx_plat->now_ms()<end&&++attempts<501);
    elden_wifi_portable_disable(elden_portable_owner);elden_portable_stopped=1;
    ath12k_warn(elden_portable_owner,"ELDEN_PORTABLE stop idle=%u rc=%d; DMA retained until actual platform fence/PERST/reset\n",
                result==1,result<0?result:result==1?0:-ETIMEDOUT);
    return result==1?0:result<0?result:-ETIMEDOUT;
}
