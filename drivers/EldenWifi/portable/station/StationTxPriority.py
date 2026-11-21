"""Select WMM voice priority for EAPOL on the tested profile-ready runtime."""

from ProfileReadySource import derive


READY_SHA = '66585bb02c6a5428a23efbc1ab7de8b29482ebb202d99f500ad8ca741f81c592'


def station(data):
    send = '        const bool sent=dpSend(dp,{owner_io.owner,owner_io.read,owner_io.write},f->bytes,f->length);'
    replacement = '''        // mac80211 classifies control-port traffic as voice when the peer uses WMM.
        const uint32_t normal_tid=dp.tid;
        if(f->eapol&&sta.phy.qos)dp.tid=7;
''' + send + '''
        dp.tid=normal_tid;'''
    return derive(data, READY_SHA, [(send, replacement)])
