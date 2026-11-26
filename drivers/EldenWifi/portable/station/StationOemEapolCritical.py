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
    critical_arg = 'f->eapol'
    replacement = f'''        // The successful station donor uses voice TID 7 on WMM peers.
        // OEM critical-flow routing remains a separate TCL decision.
        const uint32_t normal_tid=dp.tid;
        if(false&&f->eapol&&sta.phy.qos)dp.tid=7;
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
        const HttPeerMap *pm=httPeerMapOf(htt,link.options.vdevId,sta.bssid);
        {const uint32_t pv[]={0u,pm?pm->type:0,pm?pm->peerId:0,pm?pm->hwPeerId:0,pm?pm->astHash:0,pm?(uint32_t)pm->hasSearch:0};diag_line("TX_LMAC_PM lmac/type/pid/hwpid/hash/has",pv,6);}
        dpTxSetupPeer(dp,{owner_io.owner,owner_io.read,owner_io.write},link.options.vdevId,kDpPdevSingle,pm);
    }'''
        else:
            tx_replace = '''    if(current&&sta.vdevUp&&!dp.txReady&&tx_target_pdev){
        dpTxSetupPeer(dp,{owner_io.owner,owner_io.read,owner_io.write},link.options.vdevId,tx_target_pdev,httPeerMapOf(htt,link.options.vdevId,sta.bssid));
    }'''
        edits.extend([
            (dp_state, dp_state + '\nstatic uint32_t tx_target_pdev;'),
            (begin, '        tx_target_pdev=0;o.phy=kPhyLegacy;\n' + begin),
            (response, response + '''
            if(station_began&&sta.step==kStaVdevStart&&sta.vdevStartSent&&facts[1]==0&&facts[2]==0)
                tx_target_pdev=(facts[3]==kWmiVdevStartOk)?(facts[6]+1u):0;'''),
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
        diag_extra = diag_extra + '''
    const uint32_t tx_hdr[]={
        dp.tx[0].va?dpdetail::get32(dp.tx[0].va+0):0,dp.tx[0].va?dpdetail::get32(dp.tx[0].va+4):0,
        dp.tx[0].va?dpdetail::get32(dp.tx[0].va+8):0,dp.tx[0].va?dpdetail::get32(dp.tx[0].va+12):0,
        io.read(io.ctx,kDpWbm2Sw0R2+8),io.read(io.ctx,kDpWbm2Sw0R2+16),
        io.read(io.ctx,kDpWbm2Sw0R2+24),io.read(io.ctx,kDpWbm2Sw0R2+32)
    };
    diag_line("TX_HDR w0..w3/wbm1..4HP",tx_hdr,8);'''
        diag_extra = diag_extra + '''
    const uint32_t tx_w01[]={
        dpdetail::get32(dp.tcl.va+0),dpdetail::get32(dp.tcl.va+4),
        (uint32_t)dp.tx[0].bus,(uint32_t)(dp.tx[0].bus>>32),
        dp.reoCookieCfg,dp.wbmCookieConvert,
        io.read(io.ctx,kDpReoSwCookieCfg1),io.read(io.ctx,kDpWbmCookieConvert)
    };
    diag_line("TX_W01 w0/w1/busLo/Hi/reoCC0/wbmCC0/reoCC/wbmCC",tx_w01,8);
    const uint32_t dp_hw[]={
        io.read(io.ctx,0x00a44000u),io.read(io.ctx,0x00a46048u),io.read(io.ctx,0x00a4604cu),
        io.read(io.ctx,0x00a37010u),io.read(io.ctx,0x00a37014u),
        htt.t2hMessages,
        (htt.t2hTypes[0]&0xffu)|((htt.t2hTypes[1]&0xffu)<<8)|((htt.t2hTypes[2]&0xffu)<<16)|((htt.t2hTypes[3]&0xffu)<<24),
        (htt.t2hTypes[4]&0xffu)|((htt.t2hTypes[5]&0xffu)<<8)|((htt.t2hTypes[6]&0xffu)<<16)|((htt.t2hTypes[7]&0xffu)<<24),
        htt.errorsSeen,dp.st.excEntries,dp.st.rxEntries,dp.st.rxErrors
    };
    diag_line("DP_HW tclMisc/tclStHP-TP/wbmRelHP-TP/httN/t0..3/t4..7/httErr/exc/rx/rxErr",dp_hw,12);'''
        diag_extra = diag_extra + '''
    const uint32_t tcl_regs[]={
        io.read(io.ctx,0x00a4408cu),io.read(io.ctx,0x00a44020u),
        io.read(io.ctx,0x00a34240u),io.read(io.ctx,0x00a34244u),
        io.read(io.ctx,0x00a34254u),io.read(io.ctx,0x00a34d4cu),
        io.read(io.ctx,0x00a44990u),io.read(io.ctx,0x00a46008u)
    };
    diag_line("TCL_REGS bank0/cmnCtrl/idleCtrl/idleSz/idleMsb/idleMisc/tcl2Base/tcl2HP",tcl_regs,8);'''
        bhi_anchor = 'follow(now);key_turn(now);transmit();tx_diagnostic(now);port_replies();publish_snapshot();protocol_status(out);'
        bhi_extra = bhi_anchor + '''
    {static uint64_t t0;static uint32_t last_st,nlog;
     if(dp.st.txFrames&&nlog<8){if(!t0)t0=now;
       const ChipIo io{owner_io.owner,owner_io.read,owner_io.write};
       const uint32_t dt=(uint32_t)(now-t0),st=io.read(io.ctx,0x48);
       static const uint32_t marks[]={0,50,200,500,1000,2000,5000,15000};
       const bool due=(st!=last_st)||(dt>=marks[nlog]);
       if(due){last_st=st;++nlog;
         const uint32_t bhi=io.read(io.ctx,0x28);
         const uint32_t v[]={dt,st,bhi,io.read(io.ctx,bhi+0x28),io.read(io.ctx,bhi+0x2c),
           io.read(io.ctx,bhi+0x30),io.read(io.ctx,bhi+0x34),io.read(io.ctx,bhi+0x38),
           io.read(io.ctx,bhi+0x3c),link.events};
         diag_line("BHI_WATCH dt/mhiSt/bhi/ee/st/err/dbg1..3/ev",v,10);}}}'''
        bhi_extra = bhi_extra + '''
    {static uint32_t st_req;static uint64_t st_t0;
     if(dp.txReady){
       if(dp.st.txFrames&&!st_t0)st_t0=now;
       const bool want=(st_req==0)||(st_req==1&&st_t0&&now-st_t0>=600)||(st_req==2&&st_t0&&now-st_t0>=2500);
       if(want){
         uint8_t sb[64];WmiWriter ww;wmiBegin(ww,sb,sizeof(sb),kWmiCmdRequestStats);
         uint8_t *sc=wmiStruct(ww,kWmiTagRequestStatsCmd,5);
         if(sc){wmiPut(sc,0,kWmiStatsPdev);wmiPut(sc,1,0);wmiPut(sc,4,kWmiPdevIdSoc);}
         const uint32_t sl=wmiEnd(ww);
         if(sl&&linkSendWmi(link,sb,sl)==1){
           const uint32_t sv[]={st_req,dp.st.txFrames,(uint32_t)(st_t0?now-st_t0:0),link.events};
           diag_line("STATS_REQ n/tx/dt/ev",sv,4);++st_req;}}}}'''
        edits.append((diag_anchor, diag_extra))
        edits.append((bhi_anchor, bhi_extra))
        edits.append(('if(now-first_tx<2000)return;', 'if(now-first_tx<150)return;'))
        edits.append(('if(id==kWmiEvtVdevInstallKeyComplete){',
                      'if(dp.st.txFrames){static unsigned post_ev;if(post_ev<16){++post_ev;'
                      'const uint32_t pv[]={post_ev,id,bytes,link.events};'
                      'diag_line("POST_TX_EVT n/id/bytes/ev",pv,4);}}\n'
                      '    if(id==kWmiEvtUpdateStats&&dp.txReady){\n'
                      '        uint32_t fs=0,ds=0;const uint8_t *fx=wmiFind(payload,bytes,kWmiTagStatsEvent,&fs);\n'
                      '        const uint8_t *da=wmiFind(payload,bytes,kWmiTagArrayByte,&ds);\n'
                      '        if(fx&&fs>=36&&da&&ds>=kWmiPdevStatsWords*4){\n'
                      '            const uint32_t tx1[]={dp.st.txFrames,wmiGet(da,7),wmiGet(da,8),wmiGet(da,9),wmiGet(da,10),wmiGet(da,11),wmiGet(da,12),wmiGet(da,13),wmiGet(da,14),wmiGet(da,15),wmiGet(da,16),wmiGet(da,17)};\n'
                      '            const uint32_t tx2[]={wmiGet(da,18),wmiGet(da,19),wmiGet(da,20),wmiGet(da,21),wmiGet(da,22),wmiGet(da,23),wmiGet(da,24),wmiGet(da,25),wmiGet(da,26),wmiGet(da,27),wmiGet(da,28),wmiGet(da,29)};\n'
                      '            diag_line("PDEV_TX1 tx/cQ/cD/msduQ/mpduQ/wmmD/locQ/locF/hwQ/hwR/ur/abrt",tx1,12);\n'
                      '            diag_line("PDEV_TX2 req/ko/rc/sTrg/swR/illR/xRet/tmo/rst/tidF/pUr/txop",tx2,12);\n'
                      '        }\n'
                      '    }\n'
                      '    if(id==kWmiEvtVdevInstallKeyComplete){'))
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
            bank = 'kDpBankStation'
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
        '                (critical && !' + ('true' if oem_index_bank else 'false') + ' ? txNotifySemiHard : 0u));',
        'TX notify field',
    )
    text = replace_once(
        text,
        '  put32(e + 20, kDpTclTidOverwrite | (dp.tid & 0xfu) << kDpTclTidShift | (dp.vdevId & 0xffu) << kDpTclVdevShift);',
        '  put32(e + 20, kDpTclTidOverwrite |\n'
        '                    (critical && !' + ('true' if oem_index_bank else 'false') + ' ? flowOverrideEnable | classifyInfoSelOne : 0u) |\n'
        '                    (dp.tid & 0xfu) << kDpTclTidShift |\n'
        '                    ((dp.pdevId & 0x3u) << 9) | (dp.vdevId & 0xffu) << kDpTclVdevShift);',
        'critical queue fields',
    )
    text = replace_once(
        text,
        '  put32(e + 16, length & 0xffffu);                                              // no offset, not to the firmware',
        '  put32(e + 16, (length & 0xffffu) | kDpTclToFw);',
        'r29 to_fw bisect',
    )
    return text.encode()
