/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include "../PortableApi.h"
#include "upstream/PianoWifiNet.h"
#undef PIANO_WIFI_8021X_CONTROL
#define PIANO_WIFI_8021X_CONTROL "org.unixnu.elden.wifi.8021x"
#ifdef __cplusplus
extern "C" {
#endif
struct nw_bss_info;
struct nw_wifi_status;
struct nw_wifi_events;
typedef int (*EldenStationPacketReader)(void *,size_t,void *,size_t);
struct EldenStationPort {
    void *context;
    void (*lock)(void *);
    void (*unlock)(void *);
    int (*send)(void *,uint64_t,const void *,uint32_t);
};
struct EldenStationProfile {
    uint8_t ssid[32],psk[64],bssid[6];
    uint8_t ssid_bytes,psk_bytes,security,has_bssid;
};
struct EldenStationStatus {
    int step,error,failed_step;
    uint32_t vdev_started,authentication,association,port_open,keys_installed;
    uint32_t rx_frames,tx_frames,rx_eapol,tx_eapol,tx_completions,tx_acked;
};
int elden_wifi_station_requested(void);
int elden_wifi_station_native_start(void);
void elden_wifi_station_native_stop(void);
int elden_wifi_station_port_install(const struct EldenStationPort *);
int elden_wifi_station_port_open(uint64_t);
void elden_wifi_station_port_close(uint64_t);
int elden_wifi_station_port_receive(uint64_t,const uint8_t *,uint32_t);
int elden_wifi_station_profile(const struct EldenStationProfile *);
int elden_wifi_station_bss_get(int,struct nw_bss_info *);
int elden_wifi_station_scan(const uint8_t *,size_t);
int elden_wifi_station_connect(const uint8_t *,size_t,const uint8_t *,const char *,size_t);
void elden_wifi_station_disconnect(void);
void elden_wifi_station_power(int);
int elden_wifi_station_tx(const uint8_t *,size_t);
int elden_wifi_station_tx_packet(void *,size_t,EldenStationPacketReader,void (*)(void *));
void elden_wifi_station_status(struct nw_wifi_status *);
void elden_wifi_station_events(const struct nw_wifi_events *);
void elden_wifi_station_counters(struct EldenStationStatus *);
#ifdef __cplusplus
}
#endif
