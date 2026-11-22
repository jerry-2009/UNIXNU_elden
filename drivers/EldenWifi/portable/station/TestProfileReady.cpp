/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#ifndef ELDEN_STATION_SOURCE
#define ELDEN_STATION_SOURCE "Station.cpp"
#endif
#include ELDEN_STATION_SOURCE
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <mutex>
static std::recursive_mutex mutex;
static unsigned sends;static bool synchronous;
static int send_error;
static void take(void *){mutex.lock();}static void give(void *){mutex.unlock();}
static uint32_t bank_config;
static uint32_t read_reg(void *,uint32_t){return 0;}
static void write_reg(void *,uint32_t reg,uint32_t value){
    if(reg==kDpTclBankConfig)bank_config=value;
}
static uint8_t ready[16]={21,0,16,0,1,0,0,0};
static int message(void *,uint64_t session,const void *data,uint32_t){
    sends++;
    if(synchronous&&netdetail::get16((const uint8_t *)data)==PIANO_WIFI_8021X_PROFILE){
        netdetail::put32(ready+8,generation);
        assert(!elden_wifi_station_port_receive(session,ready,sizeof ready));
    }
    return send_error;
}
#if ELDEN_TEST_OEM_METADATA
static void test_oem_metadata(const EldenPortableIo &io){
    uint8_t version[8];
    std::memset(version,0xff,sizeof version);
    assert(!httBuildVersionReq(version,3));
    assert(httBuildVersionReq(version,sizeof version)==4);
    assert(dpdetail::get32(version)==0 && dpdetail::get32(version+4)==0xffffffff);
    assert(eldenOemTclMetadata(3,1)==0x40d);

    uint8_t event[44]={};
    WmiWriter wire;
    wmiBegin(wire,event,sizeof event,kWmiEvtVdevStartResp);
    uint8_t *reply=wmiStruct(wire,kWmiTagVdevStartRespEvent,9);
    assert(reply);
    for(uint32_t target : {2u,1u}){
        sta.step=kStaVdevStart;
        sta.vdevStartSent=true;
        wmiPut(reply,6,target);
        assert(hook(nullptr,kWmiEvtVdevStartResp,event+4,wmiEnd(wire)-4,10));
        sta.assocAnswered=true;
        sta.assocStatus=0;
        sta.step=kStaAssociated;
        sta.vdevUp=true;
        follow(11);
        assert(dp.txReady==(target==1));
    }
    uint8_t eapol[14]={};
    eapol[12]=0x88;
    eapol[13]=0x8e;
    assert(dpSend(dp,{io.owner,io.read,io.write},eapol,sizeof eapol));
    assert(dpdetail::get32(dp.tcl.va+12)==0x04010000);
    dpTxStop(dp);
    live=false;
}
#endif
#if ELDEN_TEST_OEM_EAPOL_CRITICAL
static void test_oem_critical(const EldenPortableIo &io){
    uint8_t version[8]={};
    assert(httBuildVersionReq(version,sizeof version)==8);
    dpTxSetup(dp,{io.owner,io.read,io.write},0,kDpPdevSingle,0,0);
#if ELDEN_TEST_OEM_INDEX_BANK
    assert(bank_config==0x40204);
#elif ELDEN_TEST_SINGLE_PDEV_BANK
    assert(bank_config==0x0a04);
#else
    assert(bank_config==0x4a04);
#endif
    uint8_t eapol[14]={};
    eapol[12]=0x88;eapol[13]=0x8e;
    assert(netQueuePut(tx_queue,eapol,sizeof eapol,true));
    transmit();
    assert(dpdetail::get32(dp.tcl.va+8)==0x300);
    assert(dpdetail::get32(dp.tcl.va+12)==0x00010000);
    assert(dpdetail::get32(dp.tcl.va+20)==0x07); // Legacy TID 0 with critical routing
    sta.phy.qos=true;
    assert(netQueuePut(tx_queue,eapol,sizeof eapol,true));
    transmit();
    assert(dpdetail::get32(dp.tcl.va+52)==0x77); // WMM TID 7 with critical routing
    sta.authorized=true;
    uint8_t ordinary[14]={};
    ordinary[12]=0x08;
    assert(netQueuePut(tx_queue,ordinary,sizeof ordinary,false));
    transmit();
    assert(dpdetail::get32(dp.tcl.va+72)==0);
    assert(dpdetail::get32(dp.tcl.va+84)==1);
    assert(!netQueueCount(tx_queue) && dp.tid==0);
    sta.authorized=false;
    dpTxStop(dp);
}
#endif

#if ELDEN_TEST_HTT_DRAIN
static void test_htt_drain(){
    constexpr unsigned endpoint=2;
    const int index=ceIndexOf(4);
    assert(index>=0 && ce.pipes[index].hasSrc);
    CeRing &source=ce.pipes[index].src;
    const auto stage=[&]{
        link.step=kLinkRxRings;
        link.pending=kLinkSendNothing;
        link.httEndpoint=endpoint;
        link.htc.ep[endpoint].used=true;
        link.htc.ep[endpoint].ulPipe=4;
        link.srngSent=kHttRings;
        link.ringSettle=20;
        link.deadline=60;
        link.options.noScan=false;
        link.endpoint=3;
        link.htc.ep[3].used=true;
        link.htc.ep[3].ulPipe=3;
        link.htc.ep[3].creditFlow=false;
        source.ours=1;
        source.taken=0;
        *source.theirs=0;
    };
    stage();
    const auto submitted=ce.sent;
    assert(linkRun(link,20)==kLinkRxRings);
    assert(link.pending==kLinkSendNothing && ce.sent==submitted);
    *source.theirs=source.words;
    assert(linkRun(link,25)==kLinkScanning);
    assert(source.taken==source.ours);
    assert(ce.sent==submitted+1 && link.request.scanId==kWmiScanId+2);

    stage();
    assert(linkRun(link,60)==kLinkErrTransport);
    assert(link.step==kLinkStopped && link.failedStep==kLinkRxRings);
    assert(ce.sent==submitted+1);
}
#endif

#if ELDEN_TEST_OEM_SRNG
static void test_oem_srng(){
    uint8_t payload[57];
    for(const auto &ring:htt.ring){
        std::memset(payload,0xa5,sizeof payload);
        assert(!httBuildSrngSetup(payload,55,ring));
        assert(payload[0]==0xa5);
        assert(httBuildSrngSetup(payload,56,ring)==56);
        assert(httdetail::get32(payload)==(kHttMsgSrngSetup | ring.radio<<8 | ring.htt<<16 | ring.kind<<24));
        assert(httdetail::get32(payload+4)==uint32_t(ring.bus));
        assert(httdetail::get32(payload+52)==0 && payload[56]==0xa5);
    }
}
#endif

int main(){
    int owner;EldenStationPort port={&owner,take,give,message};assert(!elden_wifi_station_port_install(&port));
    uint8_t mac[6]={2,1,2,3,4,5};void *memory=std::aligned_alloc(4u<<20,4u<<20);assert(memory);
    EldenPortableIo io={&owner,read_reg,write_reg,nullptr};assert(!elden_wifi_portable_prepare(&io,memory,0x20000000,4u<<20,mac,0));
    assert(!elden_wifi_station_port_open(7));
    EldenStationProfile p{};p.ssid[0]='x';p.ssid_bytes=1;p.psk_bytes=8;p.security=1;std::memcpy(p.psk,"12345678",8);
    assert(!elden_wifi_station_profile(&p));link.step=kLinkHandOff;
    port_profile();assert(sends==1&&profile_sent);
    station_turn(1);
#if ELDEN_TEST_READY
    assert(!profile_ready&&!station_began);
    netdetail::put32(ready+8,generation);
    assert(elden_wifi_station_port_receive(8,ready,sizeof ready)==-116&&!profile_ready);
    netdetail::put32(ready+8,generation+1);
    assert(elden_wifi_station_port_receive(7,ready,sizeof ready)==-116&&!profile_ready);
    netdetail::put32(ready+8,generation);netdetail::put32(ready+12,5);
    assert(elden_wifi_station_port_receive(7,ready,sizeof ready)==-5&&!profile_ready);
    netdetail::put32(ready+12,0);
    assert(elden_wifi_station_port_receive(7,ready,15)==-22&&!profile_ready);
    assert(!elden_wifi_station_port_receive(7,ready,sizeof ready)&&profile_ready);
    // ACK does not authorize a port or create a peer/association by itself.
    assert(!live&&!sta.authorized);station_turn(2);assert(station_began);
#if ELDEN_TEST_OEM_METADATA
    test_oem_metadata(io);
#endif
#if ELDEN_TEST_OEM_EAPOL_CRITICAL
    test_oem_critical(io);
#endif
    elden_wifi_station_port_close(7);assert(!profile_ready);
    station_began=0;profile_pending=true;leave_pending=false;
    assert(!elden_wifi_station_port_open(9));synchronous=true;port_profile();
    assert(profile_sent&&profile_ready);station_turn(3);assert(station_began);
    // A failed enqueue cannot leave a synchronous or stale ACK armed.
    elden_wifi_station_port_close(9);station_began=0;profile_pending=true;leave_pending=false;
    assert(!elden_wifi_station_port_open(10));send_error=-105;port_profile();
    assert(!profile_sent&&!profile_offered&&!profile_ready);station_turn(4);assert(!station_began);
#else
    // Old actual adapter associates after enqueue, without crypto completion.
    assert(station_began);
#endif
#if ELDEN_TEST_HTT_DRAIN
    test_htt_drain();
#endif
#if ELDEN_TEST_OEM_SRNG
    test_oem_srng();
#endif
    elden_wifi_portable_disable(&owner);std::free(memory);
    return 0;
}
