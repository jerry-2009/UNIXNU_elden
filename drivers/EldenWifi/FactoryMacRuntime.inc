/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Factory identifier is a private build input. No addresses are logged.
 * All non-MAC requests retain the existing verified firmware cache path.
 */
#include "EldenWifiFactoryMac.h"
static int runtime_service_firmware_get(const char *name,const uint8_t **data,size_t *bytes){
    if(data)*data=nullptr;if(bytes)*bytes=0;
    if(!name||!data||!bytes)return -22;
    if(strcmp(name,"wlan_mac.bin"))return elden_wifi_firmware_get(name,data,bytes);
    Context *c=runtime_context;
    if(!c||!c->runtime_prepared||!c->runtime_entered||c->runtime_returned||c->transport_cleanup||
       __atomic_load_n(&stop_requested,__ATOMIC_ACQUIRE))return -108;
    int rc=transport_admit(c,false);if(rc)return rc;
    EldenWifiFirmwareStatus state={};rc=elden_wifi_firmware_status(&state);if(rc)return rc;
    if(state.run!=2||state.stopping||state.error||state.epoch!=c->wlan_epoch)return state.error?state.error:-108;
    *data=reinterpret_cast<const uint8_t *>(elden_wifi_factory_mac_text);
    *bytes=sizeof(elden_wifi_factory_mac_text)-1;
    log("\nELDEN_WIFI_SERVICE factory-mac-provided=1\n");return 0;
}
