/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Portable protocol from the fixed hardware-tested Piano donor. This adapter
 * gives that protocol the existing Elden owner/IOVA and iOS17 network ABI.
 * No macOS private framework, new board voltage or firmware replacement.
 */
#include "StationApi.h"
#include "../../net/upstream17/nw_abi.h"
#include "../upstream/WifiLink.h"
#include "upstream/WifiSta.h"
#include "upstream/WifiDp.h"
#include "upstream/WifiNet.h"

namespace {
using namespace pianowifi;
static Ce ce;
static HttRx htt;
static Link link;
static Dp dp;
static Sta sta;
static StaEnv environment;
/* Empty aggregate braces make every slot including payload zero-initialized
 * in BSS; no C++ global constructor is allowed in the prelinked kernel. */
static NetQueue tx_queue{};
static NetKeys keys;
static Arena arena;
static EldenPortableIo owner_io;
static EldenStationPort port;
static nw_wifi_events callbacks;
static nw_wifi_status snapshot;
static EldenStationProfile profile;
static unsigned prepared,stopping,disabled,station_began,network_notified;
static bool profile_pending,profile_set,profile_sent,link_sent,leave_pending,query_pending,authorize_pending;
static bool scan_notice,scan_pending;
static uint64_t control_session,profile_revision,join_revision;
static uint32_t generation,message_sequence,rx_selection;
static uint64_t key_wait;
static uint32_t key_sent_index;
static KeyComplete key_answer;
static bool key_answered,live,told_up;
static bool group_completed;
static uint32_t authorize_seq,leave_seq;
static uint16_t leave_reason;
static uint8_t key_output[768];
static uint8_t eapol_frame[PIANO_WIFI_NET_FRAME_MAX];
static uint8_t packet_copy[PIANO_WIFI_NET_FRAME_MAX];

struct Reply {uint64_t session;uint32_t seq,type,generation,detail;int error;};
static Reply replies[16];
static unsigned reply_head,reply_tail;
static void lock(){port.lock(port.context);}
static void unlock(){port.unlock(port.context);}
static void wipe(void *p,uint32_t n){netdetail::wipe((volatile uint8_t *)p,n);}
static void notice(int step,const char *what){if(owner_io.note)owner_io.note(owner_io.owner,step,what);}
static void sta_notice(void *,int step,const char *what){notice(step,what);}
static void push_reply(uint32_t seq,uint32_t type,int error,uint32_t detail=0){
    const unsigned next=(reply_head+1)%16;
    if(next==reply_tail){leave_pending=true;leave_reason=15;return;}
    replies[reply_head]={control_session,seq,type,generation,detail,error};reply_head=next;
}
static int send_message(uint64_t session,const void *m,uint32_t bytes){
    if(!session||!bytes)return -11;
    return port.send(port.context,session,m,bytes);
}
static void protocol_status(EldenPortableStatus *s){
    if(s)*s={link.step,link.error,(uint32_t)link.ready.seen,link.commands,link.events,
        link.htc.creditReports,link.creditWaits,link.round+1,(uint32_t)link.scanStarted,
        (uint32_t)link.scanCompleted,link.scan.count,link.mgmtFrames,ce.sent,ce.received,
        ce.completions,ce.dropped,htt.announced};
}
static bool hook(void *,uint32_t id,const uint8_t *payload,uint32_t bytes,uint64_t now){
    if(id==kWmiEvtVdevInstallKeyComplete){
        KeyComplete value;
        if(assocParseKeyComplete(value,payload,bytes)){
            lock();if(keys.inFlight&&value.vdevId==0&&value.index==key_sent_index){key_answer=value;key_answered=true;}unlock();
        }
        return true;
    }
    return station_began&&staOnEvent(sta,id,payload,bytes,now);
}
static void publish_snapshot(){
    lock();
    snapshot.state=disabled||stopping?NW_STA_OFF:live&&sta.authorized?NW_STA_UP:
        live?NW_STA_KEYS:station_began&&sta.step>=kStaAuth&&sta.step<=kStaPeerAssoc?NW_STA_AUTH:
        link.step==kLinkHandOff?NW_STA_IDLE:NW_STA_SCANNING;
    snapshot.result=sta.error?NW_RES_FAILED:NW_RES_OK;
    for(unsigned i=0;i<6;i++){snapshot.mac[i]=link.vdevMac[i];snapshot.bssid[i]=live?sta.bssid[i]:0;}
    snapshot.ssid_len=station_began?sta.ssidLength:0;
    for(unsigned i=0;i<32;i++)snapshot.ssid[i]=i<snapshot.ssid_len?sta.ssid[i]:0;
    snapshot.freq_mhz=station_began?sta.choice.freq:0;
    snapshot.signal_dbm=station_began?(int8_t)sta.choice.rssi:0;
    snapshot.channels=link.chanList.count;
    snapshot.tx_rate_100kbps=live&&sta.authorized?60:0;
    unlock();
}
static void port_profile(){
    piano_wifi_8021x_profile p{};uint64_t session;
    lock();session=control_session;
    if(profile_set&&!profile_sent&&session){
        p.version=1;p.generation=generation;p.security=profile.security;
        p.ssid_len=profile.ssid_bytes;p.psk_len=profile.psk_bytes;
        for(unsigned i=0;i<32;i++)p.ssid[i]=profile.ssid[i];
        for(unsigned i=0;i<64;i++)p.psk[i]=profile.psk[i];
    }
    unlock();
    if(!p.ssid_len)return;
    uint8_t message[sizeof(p)+kNetHdrBytes];
    const uint32_t n=netBuildProfile(message,sizeof(message),++message_sequence,p);
    const int rc=send_message(session,message,n);
    if(!rc){lock();if(control_session==session)profile_sent=true;unlock();}
    wipe(&p,sizeof(p));wipe(message,sizeof(message));
}
static void port_link(){
    piano_wifi_8021x_link value{};uint64_t session;bool due;
    lock();session=control_session;due=query_pending||(live&&!link_sent);
    query_pending=false;unlock();if(!session||!due)return;
    value.version=1;value.state=live&&sta.authorized?2:live?1:0;value.generation=generation;
    for(unsigned i=0;i<6;i++){value.own[i]=link.vdevMac[i];value.bssid[i]=sta.bssid[i];}
    value.aid=sta.aid;value.freq=(uint16_t)sta.choice.freq;value.security=sta.rsn?1:0;
    value.pairwise=sta.pairwise;value.group=sta.groupCipher;value.akm=sta.akm;
    value.reason=(uint16_t)sta.disconnectReason;
    if(sta.rsn){
        const auto &net=sta.choice.net;
        value.ap_rsn_len=net.rsnElementLength<=sizeof(value.ap_rsn)?net.rsnElementLength:0;
        for(unsigned i=0;i<value.ap_rsn_len;i++)value.ap_rsn[i]=net.rsnElement[i];
        value.own_rsn_len=(uint8_t)netRsnElement(value.own_rsn,sizeof(value.own_rsn),sta.groupCipher,sta.pairwise,sta.akm);
    }
    uint8_t message[sizeof(value)+kNetHdrBytes];
    const uint32_t n=netBuildLink(message,sizeof(message),++message_sequence,value);
    const int rc=send_message(session,message,n);
    lock();if(control_session==session){if(!rc&&live)link_sent=true;else if(rc)query_pending=true;}unlock();
}
static void follow(uint64_t now){
    const bool current=sta.assocAnswered&&sta.assocStatus==0&&!sta.disconnect&&!sta.stopAsked&&
        sta.step>=kStaPeerAssoc&&sta.step<=kStaAssociated;
    if(current&&!live){live=true;link_sent=false;key_answered=false;key_wait=0;lock();netKeysReset(keys);group_completed=false;unlock();notice(800,"association accepted; controlled port closed");}
    if(current&&sta.vdevUp&&!dp.txReady){
        dpTxSetupPeer(dp,{owner_io.owner,owner_io.read,owner_io.write},link.options.vdevId,kDpPdevSingle,httPeerMapOf(htt,link.options.vdevId,sta.bssid));
    }
    if(!current&&live){
        live=false;dpTxStop(dp);link_sent=false;
        lock();query_pending=true;netKeysReset(keys);group_completed=false;netQueueClear(tx_queue);unlock();
        if(told_up&&callbacks.link_lost)callbacks.link_lost((int)sta.disconnectReason);
        told_up=false;network_notified=0;
    }
    if(current&&sta.authorized&&!told_up){
        told_up=true;publish_snapshot();
        if(callbacks.connect_done)callbacks.connect_done(NW_RES_OK);
        query_pending=true;notice(801,"WPA2 keys installed; controlled port opened");
    }
    (void)now;
}
static void receive(uint32_t kind,const uint8_t *frame,uint32_t bytes){
    if(!frame||bytes<14)return;
    if(kind==kDpRxEapol){
        if(!live||!stadetail::sameMac(frame+6,sta.bssid))return;
        uint64_t session;lock();session=control_session;unlock();
        if(!session)return;
        uint8_t message[PIANO_WIFI_8021X_MSG_MAX];
        const uint32_t n=netBuildEapolRx(message,sizeof(message),++message_sequence,generation,frame+6,frame+14,bytes-14);
        if(n)(void)send_message(session,message,n);
    }else if(live&&sta.authorized&&callbacks.rx){callbacks.rx(frame,bytes);}
}
static void port_replies(){
    for(unsigned budget=0;budget<16;budget++){
        lock();if(reply_head==reply_tail){unlock();break;}
        const Reply r=replies[reply_tail];const uint64_t session=control_session;unlock();
        uint8_t message[kNetHdrBytes+sizeof(piano_wifi_8021x_result)];
        const uint32_t n=netBuildResult(message,sizeof(message),r.seq,r.type,r.error,r.detail,r.generation);
        if(session==r.session&&send_message(session,message,n))break;
        lock();reply_tail=(reply_tail+1)%16;unlock();
    }
}
static void key_turn(uint64_t now){
    if(!live||!sta.vdevUp||sta.outLength)return;
    lock();
    if(keys.inFlight&&(key_answered||now>key_wait+2000)){
        const bool ok=key_answered&&key_answer.status==0;
        if(ok&&keys.inFlightGroup)group_completed=true;
        const uint32_t seq=netKeysDone(keys,ok);key_answered=false;
        push_reply(seq,PIANO_WIFI_8021X_KEY,ok?0:5,ok?0:1);
        notice(802,ok?"key completion accepted":"key completion failed");
    }
    uint32_t seq=0;const auto *next=netKeysNext(keys,&seq);
    if(next){
        KeyInstall k;k.vdevId=0;k.index=next->index;k.group=next->group!=0;
        k.cipher=next->cipher==kRsnCipherTkip?kWmiCipherTkip:kWmiCipherCcmp;
        for(unsigned i=0;i<6;i++)k.peer[i]=sta.bssid[i];
        uint8_t key[32];for(unsigned i=0;i<32;i++)key[i]=i<next->key_len?next->key[i]:0;
        if(k.cipher==kWmiCipherTkip&&next->key_len==32)for(unsigned i=0;i<8;i++){key[16+i]=next->key[24+i];key[24+i]=next->key[16+i];}
        k.key=key;k.keyBytes=next->key_len;k.rsc=next->rsc&0xffffffffffffull;
        WmiWriter writer;const uint32_t n=assocBuildInstallKey(writer,key_output,sizeof(key_output),k);
        const int result=n?linkSendWmi(link,key_output,n):-1;
        wipe(key,sizeof(key));wipe(key_output,sizeof(key_output));
        if(result==1){key_sent_index=next->index;netKeysSent(keys,next->group!=0,now);key_wait=now;key_answered=false;}
        else if(result<0){push_reply(seq,PIANO_WIFI_8021X_KEY,5);netKeysReset(keys);}
        unlock();return;
    }
    const bool authorize=authorize_pending;const uint32_t aseq=authorize_seq;unlock();
    if(authorize&&keys.pairwiseDone&&group_completed){
        WmiWriter writer;const uint32_t n=assocBuildPeerSetParam(writer,key_output,sizeof(key_output),0,sta.bssid,kWmiPeerParamAuthorize,1);
        const int result=n?linkSendWmi(link,key_output,n):-1;
        if(result){lock();authorize_pending=false;if(result==1)sta.authorized=true;push_reply(aseq,PIANO_WIFI_8021X_AUTHORIZE,result==1?0:5);unlock();}
    }
}
static void transmit(){
    for(unsigned budget=0;budget<16;budget++){
        lock();const NetFrame *f=netQueuePeek(tx_queue);
        if(!f){unlock();return;}
        if(f->eapol&&live&&!dp.txReady){unlock();return;}
        if(!dp.txReady||(!f->eapol&&!sta.authorized)){netQueuePop(tx_queue,false);unlock();continue;}
        const bool sent=dpSend(dp,{owner_io.owner,owner_io.read,owner_io.write},f->bytes,f->length);
        if(sent)netQueuePop(tx_queue,true);unlock();if(!sent)return;
    }
}
static void station_turn(uint64_t now){
    if(link.step!=kLinkHandOff)return;
    lock();const bool pending=profile_pending;const bool connected=control_session!=0;const bool sent=profile_sent;
    const uint64_t revision=profile_revision;unlock();
    if(pending&&station_began&&revision!=join_revision&&!staFinished(sta))staStop(sta,now,300);
    if(pending&&connected&&sent&&(!station_began||staFinished(sta))){
        StaOptions o;o.chains=linkdetail::chainCountOf(link.caps.rfChains);o.holdMs=0;
        sta.note=sta_notice;sta.ctx=owner_io.owner;staBegin(sta,o,environment,now);
        lock();
        if(profile_revision==revision){staSetProfile(sta,profile.ssid,profile.ssid_bytes,profile.security,profile.has_bssid?profile.bssid:nullptr);profile_pending=false;join_revision=revision;}
        unlock();station_began=1;network_notified=0;
    }
    lock();const bool cached_scan=scan_pending;scan_pending=false;unlock();
    if(cached_scan&&callbacks.scan_done)callbacks.scan_done();
    if(!station_began)return;
    lock();const bool leave=leave_pending;const uint32_t seq=leave_seq;leave_pending=false;unlock();
    if(leave){staStop(sta,now,300);lock();push_reply(seq,PIANO_WIFI_8021X_LEAVE,0);unlock();}
    staRun(sta,now);
    if(sta.outLength){const int rc=linkSendWmi(link,sta.out,sta.outLength);if(rc==1)staSent(sta,now);}
    if(staFinished(sta)&&sta.error&&!network_notified){
        network_notified=1;notice(sta.failedStep,"station ended with a protocol failure");
        if(callbacks.connect_done)callbacks.connect_done(NW_RES_FAILED);
    }
}
}

extern "C" int elden_wifi_portable_requested(void){return 1;}
extern "C" int elden_wifi_station_requested(void){return 1;}
extern "C" int elden_wifi_station_port_install(const EldenStationPort *value){
    if(port.context)return -16;
    if(!value||!value->context||!value->lock||!value->unlock||!value->send)return -22;
    port=*value;return 0;
}
extern "C" int elden_wifi_portable_prepare(const EldenPortableIo *io,void *cpu,uint64_t bus,uint32_t bytes,const uint8_t *mac,uint64_t now){
    if(prepared)return -16;
    if(!port.context||!io||!io->owner||!io->read||!io->write||!cpu||!mac||bytes!=(4u<<20)||((uintptr_t)cpu&4095)||
       !bus||(bus&(bytes-1))||bus>UINT32_MAX-(uint64_t)bytes+1||!wmiMacUsable(mac))return -22;
    prepared=1;owner_io=*io;arenaInit(arena,(uint8_t *)cpu,bus,bytes);
    if(!cePlan(ce,arena,kCePipeMaskWithHtt)||!httPlan(htt,arena,true)||!dpPlan(dp,arena,&htt))return -12;
    for(unsigned i=0;i<kAssocFrameBuffers;i++){
        environment.frame[i].va=arenaAlloc(arena,kAssocFrameBytes,&environment.frame[i].bus);environment.frame[i].bytes=kAssocFrameBytes;
        if(!environment.frame[i].va)return -12;
    }
    environment.reoq.va=arenaAlloc(arena,stadetail::kStaReoqBytes,&environment.reoq.bus);environment.reoq.bytes=stadetail::kStaReoqBytes;
    if(!environment.reoq.va)return -12;
    httFill(htt);const ChipIo chip{io->owner,io->read,io->write};
    dpProgram(dp,chip);ceProgram(ce,chip);
    LinkOptions options;options.htt=&htt;options.handOff=true;options.ownMacSet=true;
    for(unsigned i=0;i<6;i++)options.ownMac[i]=mac[i];
    link.note=io->note;link.noteCtx=io->owner;link.hook=hook;linkBegin(link,ce,chip,options,now);
    environment.ownMac=link.vdevMac;environment.scan=&link.scan;environment.reg=&link.reg;
    environment.chanList=&link.chanList;environment.htt=&htt;
    return 0;
}
extern "C" int elden_wifi_portable_tick(void *owner,uint64_t now,EldenPortableStatus *out){
    if(!prepared||owner!=owner_io.owner||disabled)return -19;
    if(stopping)return -108;
    linkRun(link,now);
    if(link.step==kLinkHandOff){
        while(rx_selection<kRxRadios){uint8_t m[kHttRxSelectionWords*4];const uint32_t n=httBuildRxSelection(m,sizeof(m),rx_selection);
            const int rc=n?linkSendHtt(link,m,n):-1;if(rc!=1)break;rx_selection++;}
        if(!scan_notice){scan_notice=true;notice(803,"station interface ready from actual WMI/HTT scan");if(callbacks.scan_done)callbacks.scan_done();}
        port_profile();station_turn(now);follow(now);publish_snapshot();port_link();
    }
    dpPoll(dp,{owner_io.owner,owner_io.read,owner_io.write},receive);
    follow(now);key_turn(now);transmit();port_replies();publish_snapshot();protocol_status(out);
    return link.step==kLinkStopped?(link.error?link.error:-5):0;
}
extern "C" int elden_wifi_portable_stop_tick(void *owner,uint64_t now){
    if(!prepared||owner!=owner_io.owner||disabled)return -19;
    if(!stopping){stopping=1;if(station_began)staStop(sta,now,100);}
    if(station_began&&!staFinished(sta)){
        linkRun(link,now);staRun(sta,now);
        if(sta.outLength&&linkSendWmi(link,sta.out,sta.outLength)==1)staSent(sta,now);
        dpPoll(dp,{owner_io.owner,owner_io.read,owner_io.write},[](uint32_t,const uint8_t *,uint32_t){});
        return 0;
    }
    return linkStopRequest(link,now)?1:0;
}
extern "C" void elden_wifi_portable_disable(void *owner){
    if(!prepared||owner!=owner_io.owner||disabled)return;
    stopping=1;dpTxStop(dp);linkDisable(link);disabled=1;
    lock();netQueueClear(tx_queue);netKeysReset(keys);wipe(&profile,sizeof(profile));control_session=0;unlock();
    publish_snapshot();
}
extern "C" int elden_wifi_station_port_open(uint64_t session){
    if(!port.context||!session||stopping||disabled)return -108;
    lock();int rc=control_session?-16:0;
    if(!rc){control_session=session;profile_sent=false;link_sent=false;query_pending=true;reply_head=reply_tail=0;}
    unlock();return rc;
}
extern "C" void elden_wifi_station_port_close(uint64_t session){
    if(!port.context)return;lock();if(control_session==session){control_session=0;profile_sent=false;leave_pending=true;leave_reason=15;authorize_pending=false;netKeysReset(keys);netQueueClear(tx_queue);}unlock();
}
extern "C" int elden_wifi_station_port_receive(uint64_t session,const uint8_t *message,uint32_t bytes){
    if(!prepared||stopping||disabled||!message||bytes>PIANO_WIFI_8021X_MSG_MAX)return -108;
    NetRequest request=netParseRequest(message,bytes);lock();
    int error=control_session!=session?-116:request.error?-22:
        request.kind!=kNetReqLinkQuery&&request.generation!=generation?-116:0;
    if(!error)switch(request.kind){
        case kNetReqLinkQuery:query_pending=true;break;
        case kNetReqEapol:{
            const uint32_t n=netEapolFrame(eapol_frame,sizeof(eapol_frame),snapshot.mac,snapshot.bssid,request.pdu,request.pduLength);
            if(snapshot.state<NW_STA_KEYS||!n)error=-107;else if(!netQueuePut(tx_queue,eapol_frame,n,true))error=-105;
            wipe(eapol_frame,sizeof(eapol_frame));break;}
        case kNetReqKey:if(snapshot.state<NW_STA_KEYS)error=-107;else if(!netKeysOffer(keys,request.key,request.seq))error=-16;break;
        case kNetReqAuthorize:if(snapshot.state<NW_STA_KEYS)error=-107;else if(authorize_pending)error=-16;else{authorize_pending=true;authorize_seq=request.seq;}break;
        case kNetReqLeave:leave_pending=true;leave_seq=request.seq;leave_reason=request.reason;break;
        default:error=-22;break;
    }
    if(error)push_reply(request.seq,request.type,-error);
    netWipeRequest(request);unlock();return error;
}
extern "C" int elden_wifi_station_profile(const EldenStationProfile *value){
    if(!port.context||!value||value->ssid_bytes<1||value->ssid_bytes>32||value->psk_bytes>64||value->security>1||
        (value->security==0&&value->psk_bytes)||(value->security==1&&(value->psk_bytes<8||value->psk_bytes>64)))return -22;
    if(value->has_bssid&&!wmiMacUsable(value->bssid))return -22;
    for(unsigned i=0;i<value->psk_bytes;i++){
        uint8_t c=value->psk[i];
        if(value->psk_bytes==64){if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')||(c>='A'&&c<='F')))return -22;}
        else if(c<0x20||c>0x7e)return -22;
    }
    lock();if(stopping||disabled){unlock();return -108;}
    if(profile_set){
        bool same=profile.ssid_bytes==value->ssid_bytes&&profile.psk_bytes==value->psk_bytes&&profile.security==value->security&&profile.has_bssid==value->has_bssid;
        for(unsigned i=0;i<32&&same;i++)same=profile.ssid[i]==value->ssid[i];
        for(unsigned i=0;i<64&&same;i++)same=profile.psk[i]==value->psk[i];
        for(unsigned i=0;i<6&&same;i++)same=profile.bssid[i]==value->bssid[i];
        unlock();return same?0:-16; /* one immutable owner profile for this trial */
    }
    profile=*value;profile_set=true;profile_pending=true;profile_sent=false;profile_revision++;
    generation++;if(!generation)generation++;
    authorize_pending=false;netKeysReset(keys);group_completed=false;unlock();return 0;
}
extern "C" int elden_wifi_station_connect(const uint8_t *ssid,size_t bytes,const uint8_t *bssid,const char *psk,size_t key_bytes){
    if(!ssid||bytes<1||bytes>32||key_bytes>64||(!psk&&key_bytes)||(bssid&&!wmiMacUsable(bssid)))return -22;
    EldenStationProfile p{};p.ssid_bytes=(uint8_t)bytes;p.psk_bytes=(uint8_t)key_bytes;p.security=key_bytes?1:0;
    for(unsigned i=0;i<bytes;i++)p.ssid[i]=ssid[i];for(unsigned i=0;i<key_bytes;i++)p.psk[i]=(uint8_t)psk[i];
    if(bssid){p.has_bssid=1;for(unsigned i=0;i<6;i++)p.bssid[i]=bssid[i];}
    const int rc=elden_wifi_station_profile(&p);wipe(&p,sizeof(p));return rc;
}
extern "C" void elden_wifi_station_disconnect(void){if(!port.context)return;lock();leave_pending=true;profile_pending=false;unlock();}
extern "C" void elden_wifi_station_power(int on){if(!on)elden_wifi_station_disconnect();}
extern "C" int elden_wifi_station_scan(const uint8_t *ssid,size_t bytes){
    if(bytes>32||(bytes&&!ssid))return -22;if(!prepared||stopping||disabled)return -108;
    lock();scan_pending=true;unlock();return 0;
}
extern "C" int elden_wifi_station_bss_get(int index,nw_bss_info *out){
    if(!out||index<0||!prepared)return -22;lock();
    if((unsigned)index>=link.scan.count){unlock();return -2;}
    const auto &e=link.scan.entries[index];*out={};
    for(unsigned i=0;i<6;i++)out->bssid[i]=e.bssid[i];out->ssid_len=e.ssidLength;
    for(unsigned i=0;i<e.ssidLength;i++)out->ssid[i]=e.ssidRaw[i];
    out->freq_mhz=e.freq;out->signal_dbm=(int8_t)e.rssi;out->caps=e.capability;out->beacon_int=e.beaconInterval;
    unsigned n=0;out->ie[n++]=0;out->ie[n++]=e.ssidLength;for(unsigned i=0;i<e.ssidLength;i++)out->ie[n++]=e.ssidRaw[i];
    if(e.rsnElementLength&&e.rsnElementLength<=64){for(unsigned i=0;i<e.rsnElementLength;i++)out->ie[n++]=e.rsnElement[i];}
    out->ie_len=(uint16_t)n;unlock();return 0;
}
extern "C" int elden_wifi_station_tx(const uint8_t *frame,size_t bytes){
    if(!frame||bytes<14||bytes>PIANO_WIFI_NET_FRAME_MAX)return -22;if(!prepared||stopping||disabled)return -108;
    lock();const bool open=snapshot.state==NW_STA_UP;const bool queued=open&&netQueuePut(tx_queue,frame,(uint32_t)bytes,false);unlock();
    return queued?0:open?-105:-100;
}
extern "C" int elden_wifi_station_tx_packet(void *context,size_t bytes,EldenStationPacketReader reader,void (*release)(void *)){
    if(!port.context||!reader||!release||bytes<14||bytes>sizeof(packet_copy))return -22;
    lock();int rc=reader(context,0,packet_copy,bytes);
    if(!rc){if(snapshot.state!=NW_STA_UP)rc=-100;else if(!netQueuePut(tx_queue,packet_copy,(uint32_t)bytes,false))rc=-105;}
    unlock();if(!rc)release(context);return rc;
}
extern "C" void elden_wifi_station_status(nw_wifi_status *out){if(!out)return;if(!port.context){*out={};return;}lock();*out=snapshot;unlock();}
extern "C" void elden_wifi_station_events(const nw_wifi_events *ev){if(!port.context)return;lock();callbacks=ev?*ev:nw_wifi_events{};unlock();}
extern "C" void elden_wifi_station_counters(EldenStationStatus *s){
    if(s)*s={sta.step,sta.error,sta.failedStep,(uint32_t)sta.vdevStarted,(uint32_t)sta.authAnswered,
        (uint32_t)sta.assocAnswered,(uint32_t)sta.authorized,keys.installed,dp.st.rxFrames,dp.st.txFrames,
        dp.st.rxEapol,dp.st.txEapol,dp.st.txCompletions,dp.st.txAcked};
}
