/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Bounded metadata only: no addresses, SSIDs, keys, attributes or frame bytes.
 * Existing callbacks own packet lifetime; the trace never retains a pointer.
 */
#include "ControlTraceApi.h"
static unsigned wifi_trace_rows,wifi_trace_snapshots;
static uint32_t wifi_trace_u32(const uint8_t *p){return p[0]|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24;}
static unsigned wifi_trace_u16(const uint8_t *p){return p[0]|unsigned(p[1])<<8;}
static void wifi_trace_meta(const char *where,unsigned unit,int error,const void *data,size_t bytes){
    if(__atomic_fetch_add(&wifi_trace_rows,1u,__ATOMIC_RELAXED)>=96)return;
    unsigned kind=0,op=0,seq=0,status=0,valid=0;
    if(data&&bytes>=40&&bytes<=65536){
        const uint8_t *p=static_cast<const uint8_t *>(data);
        if(wifi_trace_u32(p)==0x3143574e&&wifi_trace_u16(p+4)==1&&wifi_trace_u16(p+10)==0&&wifi_trace_u32(p+16)==bytes){
            valid=1;kind=wifi_trace_u16(p+6);op=wifi_trace_u16(p+8);seq=wifi_trace_u32(p+12);status=wifi_trace_u32(p+20);
        }
    }
    log("\nELDEN_WIFI_CTL where=%s unit=%u rc=%d bytes=%llu header=%u kind=%u op=%u seq=%u status=%u\n",where,unit,error,(unsigned long long)bytes,valid,kind,op,seq,status);
}
static void wifi_trace_snapshot(unsigned unit){
    if(__atomic_fetch_add(&wifi_trace_snapshots,1u,__ATOMIC_RELAXED)>=16)return;
    nw_control_stats s={};nw_wifi_control_stats_get(&s);
    log("\nELDEN_WIFI_CTL stats unit=%u accepted=%llu dispatched=%llu replies=%llu events=%llu malformed=%llu stale=%llu rxfull=%llu txfull=%llu retry=%llu rxitems=%u txitems=%u op=%u status=%u\n",
        unit,(unsigned long long)s.accepted,(unsigned long long)s.dispatched,(unsigned long long)s.replies,(unsigned long long)s.events,
        (unsigned long long)s.malformed,(unsigned long long)s.stale_sessions,(unsigned long long)s.rx_full,(unsigned long long)s.tx_full,
        (unsigned long long)s.send_retries,s.rx_items,s.tx_items,s.last_operation,s.last_status);
}
