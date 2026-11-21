/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Actual owner adapter plus the donor's CE and firmware model. Host model
 * success remains distinct from Y700 hardware/network acceptance.
 */
#define main donor_checks_main
#include "upstream/tests/wmi_host.cpp"
#undef main
#include "PortableScan.cpp"
#include <cstdlib>
static void note(void *owner,int,const char *) { CHECK(owner!=nullptr); }
int main() {
    using namespace pianowifi;
    Device device;
    EldenPortableIo io{&device,Device::read,Device::write,note};
    const uint8_t mac[6]={0x02,0x33,0x44,0x55,0x66,0x77};
    device.stalled=true;
    /* The stalled model touches registers only. No model device access is
     * allowed against this separate, aligned real CPU backing. */
    void *memory=std::aligned_alloc(kWindowBytes,kWindowBytes);
    CHECK(memory!=nullptr);std::memset(memory,0,kWindowBytes);
    CHECK(elden_wifi_portable_prepare(nullptr,memory,kBusBase,kWindowBytes,mac,0)==-22);
    CHECK(elden_wifi_portable_prepare(&io,memory,kBusBase+1,kWindowBytes,mac,0)==-22);
    CHECK(elden_wifi_portable_prepare(&io,memory,kBusBase,1u<<20,mac,0)==-22);
    uint8_t group[6]={1,0,0,0,0,1};
    CHECK(elden_wifi_portable_prepare(&io,memory,kBusBase,kWindowBytes,group,0)==-22);
    CHECK(device.writes==0);
    CHECK(elden_wifi_portable_prepare(&io,memory,kBusBase,kWindowBytes,mac,0)==0);
    CHECK(elden_wifi_portable_prepare(&io,memory,kBusBase,kWindowBytes,mac,0)==-16);
    EldenPortableStatus s{};int wrong;
    CHECK(elden_wifi_portable_tick(&wrong,0,&s)==-19);
    CHECK(elden_wifi_portable_stop_tick(&wrong,0)==-19);
    unsigned before=device.writes;elden_wifi_portable_disable(&wrong);CHECK(device.writes==before);
    /* A stalled firmware must time out with real failure; no fabricated BSS
     * or network-ready status. Existing donor suite exercises successful
     * receive scans, trailer credits and actual ring teardown. */
    CHECK(elden_wifi_portable_tick(&device,10001,&s)<0);
    CHECK(s.step==kLinkStopped&&s.error!=0&&s.ready==0&&s.bss==0);
    CHECK(elden_wifi_portable_stop_tick(&device,10002)==1);
    elden_wifi_portable_disable(&device);
    CHECK(elden_wifi_portable_tick(&device,10003,&s)==-19);
    CHECK(elden_wifi_portable_stop_tick(&device,10003)==-19);
    before=device.writes;elden_wifi_portable_disable(&device);CHECK(device.writes==before);
    std::free(memory);
    return donor_checks_main()||failures?1:0;
}
