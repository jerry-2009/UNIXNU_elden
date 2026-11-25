"""Derive the fixed OEM EAPOL critical-queue fields over the ready object."""

import hashlib

from ProfileReadySource import derive


READY_SOURCE_SHA = '66585bb02c6a5428a23efbc1ab7de8b29482ebb202d99f500ad8ca741f81c592'
DP_SOURCE_SHA = 'e34fd826570c827b3c20790a895296a963066450790196df55b8d2d4a3afa5ef'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError('OEM EAPOL critical anchor differs: ' + label)
    return text.replace(old, new, 1)


def station(data, *, oem_target_pdev=False, oem_tcl_v1=False):
    if sha(data) != READY_SOURCE_SHA:
        raise ValueError('OEM EAPOL critical patch requires the qualified ready object')
    send = '        const bool sent=dpSend(dp,{owner_io.owner,owner_io.read,owner_io.write},f->bytes,f->length);'
    critical_arg = 'false' if oem_tcl_v1 else 'f->eapol'
    replacement = f'''        // The successful station donor uses voice TID 7 on WMM peers.
        // OEM critical-flow routing remains a separate TCL decision.
        const uint32_t normal_tid=dp.tid;
        if(f->eapol&&sta.phy.qos)dp.tid=7;
        const bool sent=dpSend(dp,{{owner_io.owner,owner_io.read,owner_io.write}},f->bytes,f->length,{critical_arg});
        dp.tid=normal_tid;'''
    edits = [(send, replacement)]
    if oem_target_pdev or oem_tcl_v1:
        dp_state = 'static Dp dp;'
        begin = '        sta.note=sta_notice;sta.report=station_report;sta.ctx=owner_io.owner;staBegin(sta,o,environment,now);'
        response = '            uint32_t facts[9];for(unsigned i=0;i<9;i++)facts[i]=wmiGet(reply,i);'
        tx_setup = '''    if(current&&sta.vdevUp&&!dp.txReady){
        dpTxSetupPeer(dp,{owner_io.owner,owner_io.read,owner_io.write},link.options.vdevId,kDpPdevSingle,httPeerMapOf(htt,link.options.vdevId,sta.bssid));
    }'''
        if oem_tcl_v1:
            tx_replace = '''    if(current&&sta.vdevUp&&!dp.txReady&&tx_target_pdev){
        dpTxSetupPeer(dp,{owner_io.owner,owner_io.read,owner_io.write},link.options.vdevId,kDpPdevSingle,httPeerMapOf(htt,link.options.vdevId,sta.bssid));
        dp.tclMetadata=1u|((link.options.vdevId&0xffu)<<3);
    }'''
        else:
            tx_replace = '''    if(current&&sta.vdevUp&&!dp.txReady&&tx_target_pdev){
        dpTxSetupPeer(dp,{owner_io.owner,owner_io.read,owner_io.write},link.options.vdevId,tx_target_pdev,httPeerMapOf(htt,link.options.vdevId,sta.bssid));
    }'''
        edits.extend([
            (dp_state, dp_state + '\nstatic uint32_t tx_target_pdev;'),
            (begin, '        tx_target_pdev=0;\n' + begin),
            (response, response + '''
            if(station_began&&sta.step==kStaVdevStart&&sta.vdevStartSent&&facts[1]==0&&facts[2]==0)
                tx_target_pdev=(facts[3]==kWmiVdevStartOk&&facts[6]==1)?facts[6]:0;'''),
            (tx_setup, tx_replace),
        ])
        diag_anchor = '    diag_line("TX_DESC metadata-only words2..7",desc,6);'
        diag_extra = diag_anchor + '''
    const uint32_t lw=(dp.txComp.ours+dp.txComp.entries-1)%dp.txComp.entries;
    const uint8_t *we=dp.txComp.va+lw*dp.txComp.words*4;
    const uint32_t wbm_diag[]={
        dpdetail::get32(we+8),dpdetail::get32(we+12),dpdetail::get32(we+16),
        dp.st.lastTxSource,dp.st.lastTxReason,dp.st.txNotAcked,
        io.read(io.ctx,kDpIdleLinkR2),io.read(io.ctx,kDpIdleLinkR2+4),
        dp.st.relEntries,dp.st.txFwReleased,dp.st.txOtherRelease,dp.st.txBadCookie
    };
    diag_line("WBM_DIAG w2/w3/w4/src/rsn/nAck/idleHP-TP/rel/fwRel/oth/badC",wbm_diag,12);'''
        edits.append((diag_anchor, diag_extra))
    return derive(data, READY_SOURCE_SHA, edits)


def dp_header(data, *, single_pdev_bank=False, oem_index_bank=False):
    if sha(data) != DP_SOURCE_SHA:
        raise ValueError('OEM EAPOL critical patch requires the fixed donor Dp header')
    text = data.decode()
    if oem_index_bank and not single_pdev_bank:
        raise ValueError('OEM index bank requires the single-PDEV station')
    if single_pdev_bank:
        # The installed TB322FC module clears vdev_id_check_en on attach.
        # Keep the existing station search mode and the descriptor's VDEV ID.
        bank = 'kDpBankStation & ~kDpBankVdevCheck'
        if oem_index_bank:
            # hal_tx_populate_bank_register_be masks SW bank_config with 0x1ffff
            # (dropping SW mcast_pkt_ctrl bits 18:17) and shifts dscp_tid_map_id
            # (bits 24:19) to HW bits 22:17, writing 0x00000204 for STA index mode.
            bank = 'kDpBankEncapEthernet | kDpBankIndexLookup'
        text = replace_once(
            text,
            '  write(dp, io, kDpTclBankConfig + 4 * dp.bank, kDpBankStation);',
            f'  write(dp, io, kDpTclBankConfig + 4 * dp.bank, {bank});',
            'single-PDEV station bank',
        )
    text = replace_once(
        text,
        'inline bool dpSend(Dp &dp, const ChipIo &io, const uint8_t *frame, uint32_t length)\n{\n  using namespace dpdetail;',
        'inline bool dpSend(Dp &dp, const ChipIo &io, const uint8_t *frame, uint32_t length, bool critical = false)\n'
        '{\n  using namespace dpdetail;\n'
        '  constexpr uint32_t flowOverrideEnable = 1u << 1, classifyInfoSelOne = 1u << 2, txNotifySemiHard = 3u << 8;',
        'TX encoder and critical descriptor fields',
    )
    text = replace_once(
        text,
        '  put32(e + 8, (dp.bank & 0x3fu) << kDpTclBankShift);                          // a buffer, bank 0',
        '  put32(e + 8, (dp.bank & 0x3fu) << kDpTclBankShift |\n'
        '                (critical ? txNotifySemiHard : 0u));',
        'TX notify field',
    )
    text = replace_once(
        text,
        '  put32(e + 20, kDpTclTidOverwrite | (dp.tid & 0xfu) << kDpTclTidShift | (dp.vdevId & 0xffu) << kDpTclVdevShift);',
        '  put32(e + 20, kDpTclTidOverwrite |\n'
        '                    (critical ? flowOverrideEnable | classifyInfoSelOne : 0u) |\n'
        '                    (dp.tid & 0xfu) << kDpTclTidShift |\n'
        '                    ((dp.pdevId & 0x3u) << 9) | (dp.vdevId & 0xffu) << kDpTclVdevShift);',
        'critical queue fields',
    )
    return text.encode()
