"""Pair the TB322FC stock HTT request with its TCL metadata layout."""

from ProfileReadySource import derive
from StationTxPriority import READY_SHA


def station(data):
    link_header = '#include "../upstream/WifiLink.h"'
    # Use the stock one-word request in this translation unit while keeping
    # the imported donor header and the independently qualified scan intact.
    link = '''#define httBuildVersionReq donorHttBuildVersionReq
#include "../upstream/WifiHtt.h"
#undef httBuildVersionReq

namespace pianowifi {
inline uint32_t httBuildVersionReq(uint8_t *out, uint32_t capacity)
{
    if (!out || capacity < 4) return 0;
    httdetail::put32(out, kHttMsgVersionReq);
    return 4;
}

// The current Elden path exposes one target PDEV and one logical MAC.
inline uint32_t eldenOemTclMetadata(uint32_t vdev, uint32_t targetPdev)
{
    return 1u | ((vdev & 0xffu) << 2) | (targetPdev << 10);
}
}
''' + link_header

    dp_state = 'static Dp dp;'
    response = '            uint32_t facts[9];for(unsigned i=0;i<9;i++)facts[i]=wmiGet(reply,i);'
    begin = '        sta.note=sta_notice;sta.report=station_report;sta.ctx=owner_io.owner;staBegin(sta,o,environment,now);'
    tx_setup = '''    if(current&&sta.vdevUp&&!dp.txReady){
        dpTxSetupPeer(dp,{owner_io.owner,owner_io.read,owner_io.write},link.options.vdevId,kDpPdevSingle,httPeerMapOf(htt,link.options.vdevId,sta.bssid));
    }'''
    return derive(data, READY_SHA, [
        (link_header, link),
        (dp_state, dp_state + '\nstatic uint32_t tx_target_pdev;'),
        (begin, '        tx_target_pdev=0;\n' + begin),
        (response, response + '''
            if(station_began&&sta.step==kStaVdevStart&&sta.vdevStartSent&&facts[1]==0&&facts[2]==0)
                tx_target_pdev=(facts[3]==kWmiVdevStartOk&&facts[6]==1)?facts[6]:0;'''),
        (tx_setup, '''    if(current&&sta.vdevUp&&!dp.txReady&&tx_target_pdev){
        dpTxSetupPeer(dp,{owner_io.owner,owner_io.read,owner_io.write},link.options.vdevId,kDpPdevSingle,httPeerMapOf(htt,link.options.vdevId,sta.bssid));
        // In the OEM one-word HTT dialect, dp_tx_vdev_attach encodes
        // target pdev at bit 10 and vdev at bit 2. PMAC remains the
        // zero-based logical MAC, distinct from the firmware pdev field.
        dp.tclMetadata=eldenOemTclMetadata(link.options.vdevId,tx_target_pdev);
    }'''),
    ])
