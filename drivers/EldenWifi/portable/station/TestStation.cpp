/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Actual adapter ownership/key/profile/queue checks with symbolic register
 * memory. Full donor station/DP/handshake fixtures run separately unchanged.
 */
#include "Station.cpp"
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <mutex>
static std::recursive_mutex mutex;
static unsigned writes;
static void take(void *){mutex.lock();}
static void give(void *){mutex.unlock();}
static int message(void *,uint64_t,const void *,uint32_t){return 0;}
static uint32_t reg_read(void *,uint32_t){return 0;}
static void reg_write(void *,uint32_t,uint32_t){writes++;}
int main(){
    int owner,other;EldenStationPort io{&owner,take,give,message};
    assert(elden_wifi_station_port_install(nullptr)==-22);
    assert(elden_wifi_station_port_install(&io)==0);
    assert(elden_wifi_station_port_install(&io)==-16);
    const uint8_t mac[6]={2,3,4,5,6,7};
    void *memory=std::aligned_alloc(4u<<20,4u<<20);assert(memory);
    EldenPortableIo hardware{&owner,reg_read,reg_write,nullptr};
    assert(elden_wifi_portable_prepare(&hardware,memory,0x20000001,4u<<20,mac,0)==-22&&writes==0);
    assert(elden_wifi_portable_prepare(&hardware,memory,0x20000000,4u<<20,mac,0)==0);
    assert(elden_wifi_station_port_open(7)==0);
    assert(elden_wifi_station_port_open(8)==-16);
    EldenStationProfile p{};p.ssid[0]='x';p.ssid_bytes=1;p.psk_bytes=8;p.security=1;
    std::memcpy(p.psk,"12345678",8);assert(elden_wifi_station_profile(&p)==0);
    const auto old_generation=generation;
    assert(elden_wifi_station_profile(&p)==0&&generation==old_generation);
    p.psk[0]=1;assert(elden_wifi_station_profile(&p)==-22);
    p.psk[0]='2';assert(elden_wifi_station_profile(&p)==-16);
    uint8_t query[16]={19,0,16,0,1,0,0,0};
    assert(elden_wifi_station_port_receive(8,query,sizeof(query))==-116);
    assert(elden_wifi_station_port_receive(7,query,sizeof(query))==0);
    uint8_t auth[16]={18,0,16,0,2,0,0,0};
    pianowifi::netdetail::put32(auth+8,generation);
    assert(elden_wifi_station_port_receive(7,auth,sizeof(auth))==-107);
    uint8_t packet[64]={};assert(elden_wifi_station_tx(packet,sizeof(packet))==-100);
    /* No firmware -> real failure, no invented station, key/port success. */
    EldenPortableStatus status{};assert(elden_wifi_portable_tick(&other,0,&status)==-19);
    assert(elden_wifi_portable_tick(&owner,10001,&status)<0);
    assert(status.ready==0&&status.bss==0&&snapshot.state!=NW_STA_UP);
    elden_wifi_station_port_close(7);assert(!control_session&&!authorize_pending);
    elden_wifi_portable_disable(&owner);assert(elden_wifi_station_tx(packet,sizeof(packet))==-108);
    assert(elden_wifi_station_profile(&p)<0);std::free(memory);
    return 0;
}
