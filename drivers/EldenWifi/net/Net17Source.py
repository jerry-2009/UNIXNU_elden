"""Derive the hardware-recorded Sheng iOS17 network bridge for Elden.

No PCIe, CE, firmware or credit behavior is changed. The draft newer-OS donor
next to this directory is retained. All non-delta lines come from upstream17.
"""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('Elden net17 source anchor changed: '+old[:100])
    return text.replace(old,new,1)


def source():
    manifest=json.loads((ROOT/'upstream17/source.json').read_text(encoding='utf-8'))
    for row in manifest['files']:
        data=(ROOT/'upstream17'/row['output']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('Frozen network donor changed')
    text=(ROOT/'upstream17/WifiNet.cpp').read_text(encoding='utf-8')
    text=replace(text,'#include "nw_abi.h"','#include "nw_abi.h"\n#include "EldenNet17.h"\n#include <sys/errno.h>')
    text=replace(text,'const struct nw_wifi_events gEvents = { on_scan_done, on_connect_done, on_link_lost, on_rx };',
        'const struct nw_wifi_events gEvents = { on_scan_done, on_connect_done, on_link_lost, on_rx, nullptr, nullptr, nullptr };')
    text=replace(text,'lck_mtx_t *gLock;',
        '''lck_mtx_t *gLock;
static unsigned gStopping=1,gInFlight;
struct NetCall {
  bool open=false;
  NetCall(){
    if(__atomic_load_n(&gStopping,__ATOMIC_ACQUIRE)||elden_wifi_net_admit())return;
    __atomic_add_fetch(&gInFlight,1u,__ATOMIC_ACQ_REL);
    if(__atomic_load_n(&gStopping,__ATOMIC_ACQUIRE)||elden_wifi_net_admit()){
      __atomic_sub_fetch(&gInFlight,1u,__ATOMIC_RELEASE);return;
    }
    open=true;
  }
  ~NetCall(){if(open)__atomic_sub_fetch(&gInFlight,1u,__ATOMIC_RELEASE);}
};''')
    text=replace(text,'struct { unsigned count, kicks, cleared, longest; bool kicked; } gStall;   // input thread stalls (check_input)   // frames handed to the stack, refused ones and the last refusal\n','')
    text=replace(text,'  if (!gIf || length < 14) return;',
        '  NetCall call; if (!gIf || !call.open || length < 14 || length > 65535) return;')
    text=replace(text,'void on_scan_done() {','void on_scan_done() { NetCall call;if(!call.open)return;')
    text=replace(text,'void on_connect_done(int result) {','void on_connect_done(int result) {\n  NetCall call;if(!call.open)return;')
    text=replace(text,'void on_link_lost(int reason) {','void on_link_lost(int reason) {\n  NetCall call;if(!call.open)return;')
    text=replace(text,'  size_t length = mbuf_pkthdr_len(m);',
        '  if(!m)return EINVAL;\n  NetCall call;if(!call.open){mbuf_freem(m);return ENETDOWN;}\n  size_t length = mbuf_pkthdr_len(m);')
    text=replace(text,'    uint8_t frame[2000]; mbuf_copydata(m, 0, length, frame);',
        '    uint8_t frame[2000]; if(mbuf_copydata(m, 0, length, frame)){mbuf_freem(m);return EFAULT;}')
    text=replace(text,'errno_t if_ioctl(ifnet_t, unsigned long cmd, void *data) {',
        'errno_t if_ioctl(ifnet_t, unsigned long cmd, void *data) {\n  NetCall call;if(!call.open)return ENETDOWN;\n  if(!data)return EINVAL;')
    text=replace(text,'    case kPower: { uint32_t in[6]; if (copy_in(rq, in, sizeof in)) return EFAULT; gUserJoin = true; gPower = in[2] != 0; log(6, "wifi-net: power set %u", in[2]); if (!gPower) nw_wifi_disconnect(); post_event(kEvPowerChanged, nullptr, 0); return 0; }',
        '    case kPower: { uint32_t in[6]; if(rq.req_len<sizeof in)return EINVAL; if (copy_in(rq, in, sizeof in)) return EFAULT; gUserJoin = true; gPower = in[2] != 0; log(6, "wifi-net: power set %u", in[2]); if (!gPower) nw_wifi_disconnect(); nw_wifi_power(gPower); sheng_wifi_wake(); post_event(kEvPowerChanged, nullptr, 0); return 0; }')
    text=replace(text,'      uint8_t buf[0x80]; if (copy_in(rq, buf, sizeof buf)) return EFAULT;',
        '      uint8_t buf[0x80]; if(rq.req_len<20)return EINVAL; if (copy_in(rq, buf, sizeof buf)) return EFAULT;')
    text=replace(text,'      uint32_t ssidLength; memcpy(&ssidLength, buf + 16, 4); const uint8_t *ssid = buf + 20;',
        '      uint32_t ssidLength; memcpy(&ssidLength, buf + 16, 4); const uint8_t *ssid = buf + 20;\n      if(ssidLength>32||rq.req_len<20+ssidLength)return EINVAL;')
    text=replace(text,'      gScanning = 1; gScanCursor = 0; gResultsShown = 0; nw_wifi_scan(ssidLength && ssidLength <= 32 ? ssid : nullptr, ssidLength <= 32 ? ssidLength : 0); return 0; }',
        '      int result=nw_wifi_scan(ssidLength?ssid:nullptr,ssidLength);\n      if(result)return EBUSY;\n      gScanning = 1; gScanCursor = 0; gResultsShown = 0; sheng_wifi_wake(); return 0; }')
    text=replace(text,'      assoc_request a; if (copy_in(rq, &a, sizeof a)) return EFAULT;\n      if (a.ssid_length > 32) return EINVAL;',
        '      assoc_request a; if(rq.req_len<sizeof a)return EINVAL; if (copy_in(rq, &a, sizeof a)) return EFAULT;\n      if (a.ssid_length > 32||!a.ssid_length||a.key_length>64||(a.key_length&&a.key_cipher!=6&&a.key_cipher!=10)||(a.key_cipher==6&&a.key_length!=32)) return EINVAL;')
    text=replace(text,'      return r ? EINVAL : 0; }','      if(!r)sheng_wifi_wake();\n      return r ? EINVAL : 0; }')
    text=replace(text,'    case kDisassociate: case kDeauth: gUserJoin = true; log(6, "wifi-net: leave"); nw_wifi_disconnect(); post_link(false); return 0;',
        '    case kDisassociate: case kDeauth: gUserJoin = true; log(6, "wifi-net: leave"); nw_wifi_disconnect(); sheng_wifi_wake(); post_link(false); return 0;')
    text=replace(text,'"nativewifi 1" : "WCN7850"','"nativewifi 1" : "Peach HW2.0"')
    start=text.index('      char text[200] = "?";');end=text.index('\n    }',start)
    text=text[:start]+'      (void)properties;log(6,"wifi-net: interface naming properties received");'+text[end:]
    # Avoid payload/identity/network-address logging. Counts remain useful.
    start=text.index('void note_frame(');end=text.index('void on_rx(',start)
    text=text[:start]+'''void note_frame(const uint8_t *e,size_t n,bool out){
  if(!e||n<14)return;Kinds &k=out?gKindsOut:gKindsIn;
  const unsigned type=(unsigned)e[12]<<8|e[13];
  if(type==0x0806){k.arp++;return;}if(type==0x86dd){k.ip6++;return;}
  if(type!=0x0800||n<34){k.other++;return;}k.ip4++;
  const uint8_t *ip=e+14;const unsigned ihl=(ip[0]&15)*4;
  if((ip[0]>>4)!=4||ihl<20||n<14+ihl+8||ip[9]!=17)return;
  const uint8_t *udp=ip+ihl;unsigned sp=(unsigned)udp[0]<<8|udp[1],dp=(unsigned)udp[2]<<8|udp[3];
  if((sp==67||sp==68)&&(dp==67||dp==68))k.dhcp++;
}
'''+text[end:]
    start=text.index('// en0\'s IPv4 addresses');end=text.index('}  // namespace',start)
    text=text[:start]+'''// Counts only; pump runs on the retained Wi-Fi worker, without new threads.
static void trafficLog(void){
  if(!gIf)return;
  struct ifnet_stats_param stats={};ifnet_stat(gIf,&stats);
  log(6,"wifi-net: packets in %llu out %llu delivered %u refused %u",(unsigned long long)stats.packets_in,
      (unsigned long long)stats.packets_out,gRxFrames,gRxErrors);
}
'''+text[end:]
    text=replace(text,'extern "C" void sheng_wifi_net_start(const uint8_t mac[6]) {\n  if (gIf) return;',
        'extern "C" int elden_wifi_net_start(const uint8_t mac[6]) {\n  if(gIf)return EBUSY;\n  if(!mac||mac[0]&1||!(mac[0]|mac[1]|mac[2]|mac[3]|mac[4]|mac[5]))return EINVAL;\n  int admission=elden_wifi_net_admit();if(admission)return admission;')
    text=replace(text,'  gGrp = lck_grp_alloc_init("sheng-wifi-net", LCK_GRP_ATTR_NULL); gLock = lck_mtx_alloc_init(gGrp, LCK_ATTR_NULL);',
        '  gGrp = lck_grp_alloc_init("elden-wifi-net", LCK_GRP_ATTR_NULL); if(!gGrp)return ENOMEM;\n  gLock = lck_mtx_alloc_init(gGrp, LCK_ATTR_NULL);if(!gLock){lck_grp_free(gGrp);gGrp=nullptr;return ENOMEM;}')
    text=replace(text,'  if (e || !ifp) { log(3, "wifi-net: ifnet allocation failed: %d", e); return; }',
        '  if (e || !ifp) { log(3, "wifi-net: ifnet allocation failed: %d", e); lck_mtx_free(gLock,gGrp);lck_grp_free(gGrp);gLock=nullptr;gGrp=nullptr;return e?e:ENOMEM; }')
    text=replace(text,'  if (e) { log(3, "wifi-net: ifnet attach failed: %d", e); ifnet_release(ifp); return; }',
        '  if (e) { log(3, "wifi-net: ifnet attach failed: %d", e); ifnet_release(ifp);lck_mtx_free(gLock,gGrp);lck_grp_free(gGrp);gLock=nullptr;gGrp=nullptr;return e; }')
    text=replace(text,'  gIf = ifp; ifnet_set_flags(ifp, IFF_UP, IFF_UP);',
        '  gIf = ifp; __atomic_store_n(&gStopping,0u,__ATOMIC_RELEASE); ifnet_set_flags(ifp, IFF_UP, IFF_UP);')
    start=text.index('  // sheng-wifi-aj=0');end=text.index('\n}',start)
    text=text[:start]+'''  log(6,"wifi-net: en0 attached; original factory identity supplied; capabilities 0x%x",ifnet_capabilities_enabled(ifp));
  return 0;'''+text[end:]
    text+='''
extern "C" int elden_wifi_net_station_ready(uint8_t mac[6]){
  if(!mac)return EINVAL;memset(mac,0,6);
  nw_wifi_status state={};nw_wifi_status_get(&state);
  if(nw_wifi_stats.stage<4||!state.channels)return EAGAIN;
  if(state.mac[0]&1||!(state.mac[0]|state.mac[1]|state.mac[2]|state.mac[3]|state.mac[4]|state.mac[5]))return EINVAL;
  memcpy(mac,state.mac,6);return 0;
}
extern "C" void elden_wifi_net_stop_begin(void){
  __atomic_store_n(&gStopping,1u,__ATOMIC_RELEASE);
  // Retain callbacks/services/interface storage until reset. Do not claim an
  // asynchronous ifnet detach is complete while callbacks can still execute.
}
extern "C" int elden_wifi_net_drain(void){
  if(!__atomic_load_n(&gStopping,__ATOMIC_ACQUIRE)||__atomic_load_n(&gInFlight,__ATOMIC_ACQUIRE))return EBUSY;
  if(gIf)ifnet_set_flags(gIf,0,IFF_UP|IFF_RUNNING);
  return 0;
}
extern "C" void elden_wifi_net_pump(uint64_t now_ms){
  NetCall call;if(!call.open)return;static uint64_t next;
  if(now_ms>=next){trafficLog();next=now_ms+10000;}
}
'''
    return text.encode('utf-8')
