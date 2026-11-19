/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* The actual generated service, with recorded kernel/network models. */
#include "net_stub.h"
#include "nw_abi.h"
#include <cassert>
#include <algorithm>
StubWorld world;
extern "C" int kev_post_msg(struct kev_msg *message) __asm__("_kev_post_msg");
extern "C" int kev_post_msg(struct kev_msg *message){return kev_post_msg_stub(message);}
#include "Net17.cpp"

static unsigned checks;
#define CHECK(value) do{if(!(value)){std::fprintf(stderr,"line %u: %s\n",__LINE__,#value);std::abort();}checks++;}while(0)
static int admitted=0,scans=0,joins=0,leaves=0,powers=0,wakes=0,txs=0;
static int scan_error=0,tx_error=0;
static bool stop_on_tx=false;
static nw_wifi_status status={};
static const nw_wifi_events *events;
static std::string key_sent,ssid_sent;
static std::vector<nw_bss_info> bsses;
extern "C" {
int elden_wifi_net_admit(void){return admitted;}
void native_wifi_logf(int,const char *format,...){char text[256];va_list args;va_start(args,format);vsnprintf(text,sizeof text,format,args);va_end(args);}
void sheng_wifi_wake(void){wakes++;}
void nw_wifi_set_events(const nw_wifi_events *value){events=value;}
void nw_wifi_status_get(nw_wifi_status *value){*value=status;}
int nw_wifi_scan(const uint8_t *,size_t){scans++;return scan_error;}
int nw_wifi_bss_count(void){return (int)bsses.size();}
int nw_wifi_bss_get(int index,nw_bss_info *value){if(index<0||(size_t)index>=bsses.size())return -1;*value=bsses[index];return 0;}
int nw_wifi_connect(const uint8_t *ssid,size_t length,const uint8_t *,const char *pass,size_t pass_length){
    joins++;ssid_sent.assign((const char *)ssid,length);key_sent.assign(pass?pass:"",pass_length);return 0;
}
void nw_wifi_disconnect(void){leaves++;}
void nw_wifi_power(int){powers++;}
int nw_wifi_tx(const uint8_t *bytes,size_t length){
    CHECK(bytes&&length>=14);txs++;
    if(stop_on_tx){elden_wifi_net_stop_begin();CHECK(elden_wifi_net_drain()==EBUSY);}
    return tx_error;
}
}

static int request(bool set,int type,void *bytes,uint32_t length,int32_t *value=nullptr){
    apple80211req req={};req.req_type=type;req.req_len=length;req.req_data=(user_addr_t)bytes;
    int error=if_ioctl(gIf,set?SIOCSA80211:SIOCGA80211,&req);
    if(value)*value=req.req_val;return error;
}

int main(){
    const uint8_t mac[6]={0x02,1,2,3,4,5};
    CHECK(elden_wifi_net_start(nullptr)==EINVAL);
    uint8_t bad[6]={1,0,0,0,0,0};CHECK(elden_wifi_net_start(bad)==EINVAL);
    admitted=-108;CHECK(elden_wifi_net_start(mac)==-108);admitted=0;
    CHECK(!elden_wifi_net_start(mac));CHECK(gIf&&events&&world.ioctl&&world.output);
    CHECK(world.threads.empty());CHECK(elden_wifi_net_start(mac)==EBUSY);
    CHECK(events->rx&&events->connect_done&&!events->rx_packet&&!events->rx_flush);
    CHECK(world.init_flags==(IFNET_INIT_LEGACY|IFNET_INIT_NX_NOAUTO));
    CHECK(world.bpf_attached&&world.factory_mac==std::vector<uint8_t>(mac,mac+6));
    status.state=NW_STA_IDLE;
    uint32_t power[6]={1,1,0,0,0,0};
    CHECK(request(true,kPower,power,sizeof power)==0&&powers==1&&leaves==1);
    CHECK(!world.running);power[2]=1;
    CHECK(!request(true,kPower,power,sizeof power)&&powers==2);
    CHECK(request(true,kPower,power,8)==EINVAL);
    uint8_t scan[5520]={};
    CHECK(!request(true,kScanReq,scan,sizeof scan)&&scans==1&&gScanning==1);
    CHECK(request(true,kScanReq,scan,8)==EINVAL);
    unsigned count=33;memcpy(scan+16,&count,4);
    CHECK(request(true,kScanReq,scan,sizeof scan)==EINVAL&&scans==1);
    count=4;memcpy(scan+16,&count,4);CHECK(request(true,kScanReq,scan,22)==EINVAL);
    count=0;memcpy(scan+16,&count,4);scan_error=-11;gScanning=0;
    CHECK(request(true,kScanReq,scan,sizeof scan)==EBUSY&&gScanning==0);scan_error=0;
    events->scan_done();CHECK(gScanning==0&&!world.events.empty());
    nw_bss_info b={};b.freq_mhz=5180;b.signal_dbm=-43;b.ssid_len=4;memcpy(b.ssid,"test",4);
    b.beacon_int=100;b.caps=0x11;b.age_ms=50;b.bssid[5]=1;bsses.push_back(b);
    scan_result result={};CHECK(!request(false,kScanResult,&result,sizeof result));
    CHECK(result.ch.channel==36&&result.ssid_length==4&&result.rssi==-43);
    CHECK(request(false,kScanResult,&result,sizeof result)==EIO);
    assoc_request join={};join.version=1;join.ssid_length=4;memcpy(join.ssid,"test",4);
    join.key_cipher=6;join.key_length=32;for(unsigned i=0;i<32;i++)join.key[i]=(uint8_t)i;
    CHECK(!request(true,kAssociate,&join,sizeof join)&&joins==1&&key_sent.size()==64&&ssid_sent=="test");
    CHECK(key_sent.substr(0,8)=="00010203"&&key_sent.substr(60)=="1e1f");
    CHECK(request(true,kAssociate,&join,32)==EINVAL&&joins==1);
    join.key_length=65;CHECK(request(true,kAssociate,&join,sizeof join)==EINVAL);
    join.key_length=12;CHECK(request(true,kAssociate,&join,sizeof join)==EINVAL);
    join.key_cipher=10;memcpy(join.key,"testpassword",12);
    CHECK(!request(true,kAssociate,&join,sizeof join)&&joins==2&&key_sent=="testpassword");
    status.state=NW_STA_UP;status.freq_mhz=5180;status.signal_dbm=-43;memcpy(status.ssid,"test",4);status.ssid_len=4;
    events->connect_done(NW_RES_OK);CHECK(world.running&&gAssocResult==kAssocOk);
    events->connect_done(NW_RES_BAD_KEY);CHECK(gAssocResult==kAssocBadKey);
    events->link_lost(7);CHECK(!world.running);
    CHECK(!request(true,kDisassociate,nullptr,0)&&leaves==2);
    CHECK(request(false,999,&result,sizeof result)==EOPNOTSUPP);
    // Fragmented receive storage: actual source must not overrun the first
    // buffer and the model records/frees every chained packet it consumes.
    std::vector<uint8_t> frame(1800,0);frame[12]=0x08;frame[13]=0x00;
    frame[14]=0x45;frame[23]=17;frame[34]=0;frame[35]=67;frame[36]=0;frame[37]=68;
    world.cluster_bytes=300;events->rx(frame.data(),frame.size());
    CHECK(world.inputs==1&&world.last_frame==frame&&world.mbuf_live==0&&gRxChains==1);
    world.alloc_failure=true;events->rx(frame.data(),frame.size());world.alloc_failure=false;
    CHECK(world.inputs==1&&gRxNoBuffer==1);
    world.truncate_chain=true;events->rx(frame.data(),frame.size());world.truncate_chain=false;
    CHECK(world.inputs==1&&world.mbuf_live==0&&gRxNoBuffer==2);
    mbuf_t output=nullptr;CHECK(!mbuf_allocpacket(0,frame.size(),nullptr,&output));
    size_t copied=0;for(mbuf_t n=output;n;n=mbuf_next(n)){
        size_t bytes=std::min(frame.size()-copied,mbuf_maxlen(n));memcpy(mbuf_data(n),frame.data()+copied,bytes);mbuf_setlen(n,bytes);copied+=bytes;
    }
    mbuf_pkthdr_setlen(output,frame.size());CHECK(!if_output(gIf,output)&&txs==1&&world.mbuf_live==0);
    CHECK(!mbuf_allocpacket(0,100,nullptr,&output));mbuf_pkthdr_setlen(output,100);world.copy_failure=true;
    CHECK(if_output(gIf,output)==EFAULT&&world.mbuf_live==0&&txs==1);world.copy_failure=false;
    admitted=-108;CHECK(request(false,kState,nullptr,0)==ENETDOWN);
    CHECK(!mbuf_allocpacket(0,100,nullptr,&output));mbuf_pkthdr_setlen(output,100);
    CHECK(if_output(gIf,output)==ENETDOWN&&world.mbuf_live==0&&txs==1);admitted=0;
    elden_wifi_net_pump(1);CHECK(world.threads.empty());
    CHECK(elden_wifi_net_drain()==EBUSY);
    CHECK(!mbuf_allocpacket(0,100,nullptr,&output));mbuf_pkthdr_setlen(output,100);mbuf_setlen(output,100);
    stop_on_tx=true;CHECK(!if_output(gIf,output)&&txs==2&&world.mbuf_live==0);stop_on_tx=false;
    size_t event_count=world.events.size();elden_wifi_net_stop_begin();CHECK(!elden_wifi_net_drain());
    CHECK(request(false,kState,nullptr,0)==ENETDOWN&&!world.running);
    events->scan_done();events->connect_done(0);events->link_lost(0);events->rx(frame.data(),frame.size());
    CHECK(world.events.size()==event_count&&world.inputs==1&&world.mbuf_live==0);
    std::printf("PASS %u actual iOS17 bridge checks; Settings requests, ownership, chained packets and stopped admission\n",checks);
}
