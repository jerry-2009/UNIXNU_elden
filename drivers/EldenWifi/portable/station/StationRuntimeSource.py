"""Select station through the already-qualified portable firmware/glue path."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[4]
PORT=ROOT/'drivers/EldenWifi/portable'
EXPECTED={'core.c': '1101964543125cb532c668a77b7e6c2dbd1df6947d7c0e77d1504efecbf624a8', 'qmi.c': 'f4294eb6c54e84f13bb7aaaee3f43e3c3aa61f3a73a7bd311be5ada4ac14cd2a', 'nw_wifi.c': '96e1f01f5f63d218620b2f57907ee68679910b5a39053febb6fed6bf29d367d6', 'nw_mainline.c': 'a9d89710b2d09596ff712b8fdfc711411286136a1528b20e9d5cb3a8345dfcd9'}

def patch(name,data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED[name]:raise ValueError('Exact portable scan parent required: '+name)
    original=text=data.decode();changes=[]
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('Station runtime anchor changed: '+old[:90])
        text=text.replace(old,new,1);changes.append((old,new))
    if name=='core.c':
        old=(PORT/'PortableGlue.inc').read_text()
        new=old.replace('#include "PortableApi.h"','#include "StationApi.h"')
        new=new.replace('    rc=ath12k_qmi_firmware_start(ab,ab->fw_mode);',
                        '    rc=elden_wifi_station_native_start();if(rc)goto fail;\n'
                        '    rc=ath12k_qmi_firmware_start(ab,ab->fw_mode);')
        new=new.replace('    /* The original cfg80211/iPadOS bridge has no invented station. */',
                        '''    /* Stage4 only after real WMI/HTT scan and factory MAC snapshot. */
    struct nw_wifi_status station={};elden_wifi_station_status(&station);
    if(elden_portable_state.step==629&&station.channels)nw_wifi_stats.stage=4;
    static uint64_t station_report_at;
    if(nw_wifi_stats.stage==4){
        const uint8_t *data=NULL;size_t bytes=0;
        static bool profile_loaded;
        if(!profile_loaded&&lx_plat->fw_get&&!lx_plat->fw_get("elden-station-profile.bin",&data,&bytes)&&
           bytes==sizeof(struct EldenStationProfile)){
            int error=elden_wifi_station_profile((const struct EldenStationProfile *)data);
            if(!error)profile_loaded=true;
        }
        struct EldenStationStatus st={};elden_wifi_station_counters(&st);
        if(now>=station_report_at){station_report_at=now+1000;
            ath12k_warn(elden_portable_owner,"ELDEN_STATION stage=%d error=%d failed=%d start=%u auth=%u assoc=%u port=%u keys=%u RX=%u TX=%u EAPOL=%u/%u done=%u ack=%u\\n",
                st.step,st.error,st.failed_step,st.vdev_started,st.authentication,st.association,st.port_open,st.keys_installed,
                st.rx_frames,st.tx_frames,st.rx_eapol,st.tx_eapol,st.tx_completions,st.tx_acked);
        }
    }''')
        new=new.replace('    elden_wifi_portable_disable(elden_portable_owner);elden_portable_stopped=1;',
                        '    elden_wifi_portable_disable(elden_portable_owner);elden_portable_stopped=1;\n'
                        '    elden_wifi_station_native_stop();')
        replace(old,new)
    elif name=='nw_mainline.c':
        routes={
          'int nw_wifi_scan(const u8 *ssid, size_t length) {':'    if(elden_wifi_station_requested())return elden_wifi_station_scan(ssid,length);',
          'int nw_wifi_connect(const u8 *ssid, size_t length, const u8 *address, const char *password, size_t password_length) {':'    if(elden_wifi_station_requested())return elden_wifi_station_connect(ssid,length,address,password,password_length);',
          'void nw_wifi_disconnect(void) {':'    if(elden_wifi_station_requested()){elden_wifi_station_disconnect();return;}',
          'void nw_wifi_power(int enabled) {':'    if(elden_wifi_station_requested()){elden_wifi_station_power(enabled);return;}',
          'int nw_wifi_bss_get(int index, struct nw_bss_info *out) {':'    if(elden_wifi_station_requested())return elden_wifi_station_bss_get(index,out);',
          'void nw_wifi_status_get(struct nw_wifi_status *out) {':'    if(elden_wifi_station_requested()){elden_wifi_station_status(out);return;}',
          'int nw_wifi_tx(const u8 *bytes, size_t length) {':'    if(elden_wifi_station_requested())return elden_wifi_station_tx(bytes,length);',
          'int nw_wifi_tx_packet(void *context, size_t length, nw_packet_reader reader, void (*release)(void *)) {':'    if(elden_wifi_station_requested())return elden_wifi_station_tx_packet(context,length,reader,release);',
        }
        for old,new in routes.items():replace(old,old+'\n'+new)
        replace('#include "PortableApi.h"','#include "StationApi.h"')
    elif name=='nw_wifi.c':
        replace('  static unsigned last_frames; nw_wifi_control_poll(); lx_pump();',
                '  static unsigned last_frames; extern struct nw_wifi_events nw_events;\n'
                '  elden_wifi_station_events(&nw_events); nw_wifi_control_poll(); lx_pump();')
        replace('#include "PortableApi.h"','#include "StationApi.h"')
    elif name=='qmi.c':pass
    else:raise ValueError('Unknown station runtime unit')
    restored=text
    for old,new in reversed(changes):restored=restored.replace(new,old,1)
    if restored!=original:raise ValueError('Unrelated station delta')
    return text.encode()
