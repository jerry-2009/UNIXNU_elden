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
static uint32_t read_reg(void *,uint32_t){return 0;}static void write_reg(void *,uint32_t,uint32_t){}
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
    assert(dpdetail::get32(dp.tcl.va+20)==1);
    dpTxStop(dp);
    live=false;
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
    elden_wifi_portable_disable(&owner);std::free(memory);
    return 0;
}
