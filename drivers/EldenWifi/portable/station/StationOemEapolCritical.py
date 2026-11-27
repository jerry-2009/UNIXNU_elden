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
        if(!dp.programmed)dpProgram(dp,{owner_io.owner,owner_io.read,owner_io.write});
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
            ('dpProgram(dp,chip);ceProgram(ce,chip);', 'ceProgram(ce,chip);'),
            (tx_setup, tx_replace),
        ])
        diag_anchor = '    diag_line("TX_DESC metadata-only words2..7",desc,6);'
        ms_old = '''static void tx_diagnostic(uint64_t now){
    static uint64_t first_tx;static unsigned sampled;
    if(!dp.st.txFrames||sampled)return;
    if(!first_tx){first_tx=now;return;}
    if(now-first_tx<2000)return;
    sampled=1;
    const ChipIo io{owner_io.owner,owner_io.read,owner_io.write};'''
        ms_new = '''static void tx_diagnostic(uint64_t now){
    static uint64_t first_tx;static unsigned sampled;
    if(!dp.st.txFrames||sampled>=5)return;
    if(!first_tx){first_tx=now;return;}
    if(now-first_tx<1500ull*(uint64_t)(sampled+1))return;
    ++sampled;
    const ChipIo io{owner_io.owner,owner_io.read,owner_io.write};
    {
    const uint32_t whp[]={sampled,
        io.read(io.ctx,kDpWbm2Sw0R2),io.read(io.ctx,kDpWbm2Sw0R2+4),
        io.read(io.ctx,kDpWbm2Sw0R2+kDpWbm2SwR2Stride),io.read(io.ctx,kDpWbm2Sw0R2+kDpWbm2SwR2Stride+4),
        io.read(io.ctx,kDpWbm2Sw0R2+2*kDpWbm2SwR2Stride),io.read(io.ctx,kDpWbm2Sw0R2+2*kDpWbm2SwR2Stride+4),
        io.read(io.ctx,kDpWbm2Sw0R2+3*kDpWbm2SwR2Stride),io.read(io.ctx,kDpWbm2Sw0R2+3*kDpWbm2SwR2Stride+4),
        io.read(io.ctx,kDpWbm2Sw0R2+4*kDpWbm2SwR2Stride),io.read(io.ctx,kDpWbm2Sw0R2+4*kDpWbm2SwR2Stride+4)};
    diag_line("WBMHP n/HP0/TP0/HP1/TP1/HP2/TP2/HP3/TP3/HP4/TP4",whp,11);
    const uint32_t idl[]={sampled,io.read(io.ctx,kDpIdleLinkR2),io.read(io.ctx,kDpIdleLinkR2+4),
        io.read(io.ctx,dp.tcl.r2),io.read(io.ctx,dp.tcl.r2+4)};
    diag_line("WBMIDL n/idleHP/idleTP/tclHP/tclTP",idl,5);
    const uint8_t *rb[4]={dp.txComp.va,dp.txComp2.va,dp.txComp1.va,dp.rel3.va};
    for(unsigned r=0;r<4;r++){
        uint32_t ew[9];ew[0]=r;
        for(unsigned w=0;w<8;w++)ew[w+1]=dpdetail::get32(rb[r]+w*4);
        diag_line("WBMENT ring0-2-4-3/w0..w7",ew,9);
    }
    }
    if(sampled>1)return;'''

        diag_extra = diag_anchor + '''
    const uint32_t lw=(dp.txComp.ours+dp.txComp.entries-1)%dp.txComp.entries;
    const uint8_t *we=dp.txComp.va+lw*dp.txComp.words*4;
    const uint32_t wbm_diag[]={
        dpdetail::get32(we+8),dpdetail::get32(we+12),dpdetail::get32(we+16),
        dp.st.lastTxSource,dp.st.lastTxReason,dp.st.txNotAcked,
        io.read(io.ctx,kDpIdleLinkR2),io.read(io.ctx,kDpIdleLinkR2+4),
        dp.st.relEntries,dp.st.txFwReleased,dp.st.txOtherRelease,dp.st.txBadCookie
    };
    diag_line("WBM_DIAG w2/w3/w4/src/rsn/nAck/idleHP-TP/rel/fwRel/oth/badC",wbm_diag,12);
    const uint32_t wbm_w01[]={dpdetail::get32(dp.txComp.va+0),dpdetail::get32(dp.txComp.va+4),dp.tx[0].busy,dp.st.txBadCookie};
    diag_line("WBM_W01 w0/w1/busy/badC",wbm_w01,4);'''
        diag_extra = diag_extra + '''
    const uint32_t tx_hdr[]={
        dp.tx[0].va?dpdetail::get32(dp.tx[0].va+0x00):0,dp.tx[0].va?dpdetail::get32(dp.tx[0].va+0x04):0,
        dp.tx[0].va?dpdetail::get32(dp.tx[0].va+0x08):0,dp.tx[0].va?dpdetail::get32(dp.tx[0].va+0x0c):0,
        io.read(io.ctx,kDpWbm2Sw0R2+8),io.read(io.ctx,kDpWbm2Sw0R2+16),
        io.read(io.ctx,kDpWbm2Sw0R2+24),io.read(io.ctx,kDpWbm2Sw0R2+32)
    };
    diag_line("TX_HDR payload0..3/wbm1..4HP",tx_hdr,8);'''
        diag_extra = diag_extra + '''
    const uint32_t tx_w01[]={
        dpdetail::get32(dp.tcl.va+0),dpdetail::get32(dp.tcl.va+4),
        (uint32_t)dp.tx[0].bus,(uint32_t)(dp.tx[0].bus>>32),
        dp.reoCookieCfg,dp.wbmCookieConvert,
        io.read(io.ctx,kDpReoSwCookieCfg1),io.read(io.ctx,kDpWbmCookieConvert)
    };
    diag_line("TX_W01 w0/w1/busLo/Hi/reoCC0/wbmCC0/reoCC/wbmCC",tx_w01,8);
    const uint32_t tx_w4=dpdetail::get32(dp.tcl.va+16);
    const uint32_t tx_pkt[]={tx_w4,(tx_w4>>23)&0x1ffu,tx_w4&0xffffu,dpdetail::get32(dp.tx[0].va+0x00)};
    diag_line("TX_PKT w4/pktOff/len/payload0",tx_pkt,4);
    const uint32_t dp_sw[]={
        htt.t2hMessages,
        (htt.t2hTypes[0]&0xffu)|((htt.t2hTypes[1]&0xffu)<<8)|((htt.t2hTypes[2]&0xffu)<<16)|((htt.t2hTypes[3]&0xffu)<<24),
        (htt.t2hTypes[4]&0xffu)|((htt.t2hTypes[5]&0xffu)<<8)|((htt.t2hTypes[6]&0xffu)<<16)|((htt.t2hTypes[7]&0xffu)<<24),
        htt.errorsSeen,dp.st.excEntries,dp.st.rxEntries,dp.st.rxErrors
    };
    diag_line("DP_SW httN/t0..3/t4..7/httErr/exc/rx/rxErr",dp_sw,7);'''
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
        edits.append((ms_old, ms_new))
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
    edits.append((
        'static uint64_t control_session,profile_revision,join_revision;',
        'static uint64_t control_session,profile_revision,join_revision;\nstatic uint64_t rx_now;'
    ))
    edits.append((
        '    dpPoll(dp,{owner_io.owner,owner_io.read,owner_io.write},receive);',
        '    rx_now=now;dpPoll(dp,{owner_io.owner,owner_io.read,owner_io.write},receive);'
    ))
    rx_old="""        uint8_t message[PIANO_WIFI_8021X_MSG_MAX];
        const uint32_t n=netBuildEapolRx(message,sizeof(message),++message_sequence,generation,frame+6,frame+14,bytes-14);
        const auto kind=netEapolKind(frame+14,bytes-14);
        uint32_t facts[]={kind.message,bytes-14,(uint32_t)dp.txReady,(uint32_t)sta.vdevUp};diag_line("EAPOL_RX message/bytes/TXready/up",facts,4);
        if(n)(void)send_message(session,message,n);"""
    rx_new="""        static uint64_t last_m1_ms;static bool m3_seen;
        if(!sta.vdevUp){last_m1_ms=0;m3_seen=false;}
        uint32_t eapol_bytes=bytes-14;
        const uint32_t eapol_len=4u+(((uint32_t)frame[16]<<8)|frame[17]);
        if(eapol_len>=4&&eapol_len<eapol_bytes)eapol_bytes=eapol_len;
        const uint32_t info=bytes>=21?(((uint32_t)frame[19]<<8)|frame[20]):0;
        const bool is_m1=(info&0x0088u)==0x0088u&&!(info&0x0100u);
        const bool is_m3=(info&0x01c8u)==0x01c8u;
        if(is_m1){
            const bool skip=!dp.txReady||!sta.vdevUp||m3_seen||(last_m1_ms&&rx_now-last_m1_ms<4000);
            if(skip){const uint32_t sv[]={(uint32_t)dp.txReady,(uint32_t)sta.vdevUp,(uint32_t)m3_seen,(uint32_t)(last_m1_ms?rx_now-last_m1_ms:0)};diag_line("EAPOL_M1_SKIP ready/up/m3/dt",sv,4);return;}
            last_m1_ms=rx_now;
        }
        if(is_m3)m3_seen=true;
        uint8_t message[PIANO_WIFI_8021X_MSG_MAX];
        const uint32_t n=netBuildEapolRx(message,sizeof(message),++message_sequence,generation,frame+6,frame+14,eapol_bytes);
        const auto kind=netEapolKind(frame+14,eapol_bytes);
        uint32_t facts[]={kind.message,eapol_bytes,(uint32_t)dp.txReady,(uint32_t)sta.vdevUp};diag_line("EAPOL_RX message/bytes/TXready/up",facts,4);
        if(n)(void)send_message(session,message,n);"""
    edits.append((rx_old,rx_new))
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
            bank = '0x00000204u'
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
        '{\n  using namespace dpdetail;\n',
        'TX encoder and critical descriptor fields',
    )
    text = replace_once(
        text,
        '  put32(e + 8, (dp.bank & 0x3fu) << kDpTclBankShift);                          // a buffer, bank 0',
        '  put32(e + 8, (dp.bank & 0x3fu) << kDpTclBankShift |\n'
        '                (0u));',
        'TX notify field',
    )
    text = replace_once(
        text,
        '  put32(e + 20, kDpTclTidOverwrite | (dp.tid & 0xfu) << kDpTclTidShift | (dp.vdevId & 0xffu) << kDpTclVdevShift);',
        '  put32(e + 20, kDpTclTidOverwrite |\n'
        '                    (0u) |\n'
        '                    (dp.tid & 0xfu) << kDpTclTidShift |\n'
        '                    ((dp.pdevId & 0x3u) << 9) | (dp.vdevId & 0xffu) << kDpTclVdevShift);',
        'critical queue fields',
    )
    text = replace_once(
        text,
        '  for (uint32_t i = 0; i < length; ++i) b.va[i] = frame[i];',
        '  (void)critical;\n'
        '  const uint32_t off = 0x28u;\n'
        '  for (uint32_t i = 0; i < off; ++i) b.va[i] = 0;\n'
        '  put32(b.va, 0x80000000u); // r79: ext2 dword0 host_tx_desc_pool (TQM-BYPASS host-pool completion linkage)\n'
        '  for (uint32_t i = 0; i < length; ++i) b.va[off + i] = frame[i];',
        'Peach 0x28 headroom zeroed before Ethernet frame',
    )
    text = replace_once(
        text,
        '  put32(e + 16, length & 0xffffu);                                              // no offset, not to the firmware',
        '  put32(e + 16, (length & 0xffffu) | (1u << 21) | (0x28u << 23)); // r78: to_fw=1 + pkt_offset=0x28, all-zero ext2 metadata (TQM VP WAR firmware path)',
        'Peach pktOff=0x28 in w4',
    )
    text = replace_once(
        text,
        'constexpr uint32_t kDpTclEntries = 64, kDpTxCompEntries = 64',
        'constexpr uint32_t kDpTclEntries = 512, kDpTxCompEntries = 1024',
        'Peach upstream TX ring sizes',
    )
    text = replace_once(
        text,
        '  CeRing tcl, txComp, reo, reoExc, rel3, idle;',
        '  CeRing tcl, txComp, tcl1, txComp1, tcl2, txComp2, reo, reoExc, rel3, idle;',
        'Peach three TX ring pairs',
    )
    text = replace_once(
        text,
        '  uint8_t *pointers = arenaAlloc(arena, 4 * 8, &pointersBus);',
        '  uint8_t *pointers = arenaAlloc(arena, 4 * 16, &pointersBus);',
        'Peach TX shadow pointers',
    )
    text = replace_once(
        text,
        '''  uint32_t index = 0;
  if (!plan(dp.tcl, arena, kDpTclEntries, kDpTclEntryWords, kDpTcl1R0, kDpTcl1R2, 0, pointers, pointersBus, index) ||
      !plan(dp.txComp, arena, kDpTxCompEntries, kDpWbmEntryWords, kDpWbm2Sw0R0, kDpWbm2Sw0R2, kDpRingIdWbm2Sw0, pointers,
            pointersBus, index) ||
      !plan(dp.reo, arena, kDpReoEntries, kDpReoEntryWords, kDpReo2Sw1R0, kDpReo2Sw1R2, kDpRingIdReo2Sw1, pointers, pointersBus,
            index) ||
      !plan(dp.reoExc, arena, kDpReoExcEntries, kDpReoEntryWords, kDpReo2Sw0R0, kDpReo2Sw0R2, kDpRingIdReo2Sw0, pointers,
            pointersBus, index) ||
      !plan(dp.rel3, arena, kDpRelEntries, kDpWbmEntryWords, kDpWbm2Sw0R0 + 3 * kDpWbm2SwR0Stride,
            kDpWbm2Sw0R2 + 3 * kDpWbm2SwR2Stride, kDpRingIdWbm2Sw0 + 3, pointers, pointersBus, index) ||
      !plan(dp.idle, arena, kDpIdleEntries, kDpIdleEntryWords, kDpIdleLinkR0, kDpIdleLinkR2, 0, pointers, pointersBus, index))
    return false;
''',
        '''  uint32_t index = 0;
  if (!plan(dp.tcl, arena, kDpTclEntries, kDpTclEntryWords, kDpTcl1R0, kDpTcl1R2, 0, pointers, pointersBus, index) ||
      !plan(dp.txComp, arena, kDpTxCompEntries, kDpWbmEntryWords, kDpWbm2Sw0R0, kDpWbm2Sw0R2, kDpRingIdWbm2Sw0, pointers,
            pointersBus, index) ||
      !plan(dp.tcl1, arena, kDpTclEntries, kDpTclEntryWords, kDpTcl1R0 + 0x78, kDpTcl1R2 + 8, 0, pointers, pointersBus, index) ||
      !plan(dp.txComp1, arena, kDpTxCompEntries, kDpWbmEntryWords, kDpWbm2Sw0R0 + 4 * kDpWbm2SwR0Stride,
            kDpWbm2Sw0R2 + 4 * kDpWbm2SwR2Stride, kDpRingIdWbm2Sw0 + 4, pointers, pointersBus, index) ||
      !plan(dp.tcl2, arena, kDpTclEntries, kDpTclEntryWords, kDpTcl1R0 + 2 * 0x78, kDpTcl1R2 + 2 * 8, 0, pointers, pointersBus,
            index) ||
      !plan(dp.txComp2, arena, kDpTxCompEntries, kDpWbmEntryWords, kDpWbm2Sw0R0 + 2 * kDpWbm2SwR0Stride,
            kDpWbm2Sw0R2 + 2 * kDpWbm2SwR2Stride, kDpRingIdWbm2Sw0 + 2, pointers, pointersBus, index) ||
      !plan(dp.reo, arena, kDpReoEntries, kDpReoEntryWords, kDpReo2Sw1R0, kDpReo2Sw1R2, kDpRingIdReo2Sw1, pointers, pointersBus,
            index) ||
      !plan(dp.reoExc, arena, kDpReoExcEntries, kDpReoEntryWords, kDpReo2Sw0R0, kDpReo2Sw0R2, kDpRingIdReo2Sw0, pointers,
            pointersBus, index) ||
      !plan(dp.rel3, arena, kDpRelEntries, kDpWbmEntryWords, kDpWbm2Sw0R0 + 3 * kDpWbm2SwR0Stride,
            kDpWbm2Sw0R2 + 3 * kDpWbm2SwR2Stride, kDpRingIdWbm2Sw0 + 3, pointers, pointersBus, index) ||
      !plan(dp.idle, arena, kDpIdleEntries, kDpIdleEntryWords, kDpIdleLinkR0, kDpIdleLinkR2, 0, pointers, pointersBus, index))
    return false;
''',
        'Peach three TCL completion pair layout',
    )
    text = replace_once(
        text,
        '    case kDpBlockTcl: program(dp, io, dp.tcl, true); break;',
        '''    case kDpBlockTcl:
      program(dp, io, dp.tcl, true);
      program(dp, io, dp.tcl1, true);
      program(dp, io, dp.tcl2, true);
      break;''',
        'Peach three TCL rings programmed',
    )
    text = replace_once(
        text,
        '    case kDpBlockTxComp: program(dp, io, dp.txComp, false); break;',
        '''    case kDpBlockTxComp:
      program(dp, io, dp.txComp, false);
      program(dp, io, dp.txComp1, false);
      program(dp, io, dp.txComp2, false);
      break;''',
        'Peach three TX completion rings programmed',
    )
    text = replace_once(
        text,
        '        put32(e + 4, uint32_t((bus >> 32) & 0xffu) | kDpRbmIdleDescDev0 << 8 | (i & 0xfffffu) << 12);',
        '        put32(e + 4, uint32_t((bus >> 32) & 0xffu) | kDpRbmIdleDescDev0 << 8 | ((((i / 32u) + 0x400u) << 9) | (i & 31u)) << 12);',
        'Peach nonzero 16K-page idle-link cookie base',
    )
    # r75: the missing Peach ring fabric. hw_srng_table_peach inside the real qca_cld3_peach_v2.ko initializes
    # SW2WBM_RELEASE (ring id 121), REO_CMD (20), REO_STATUS (21) and REO_REINJECT (16) besides what r68 already
    # had; TCL_CMD_CREDIT/TCL_STATUS carry max_rings 0 there, so this build never sets them up either.
    text = replace_once(
        text,
        '  CeRing tcl, txComp, tcl1, txComp1, tcl2, txComp2, reo, reoExc, rel3, idle;',
        '  CeRing tcl, txComp, tcl1, txComp1, tcl2, txComp2, reo, reoExc, rel3, idle, sw2wbm, reoCmd, reoStatus, reoReinject;',
        'r75 fabric ring objects',
    )
    # The ring fabric constants live here rather than in portable/upstream/WifiHw.h because the donor provenance
    # check hashes that header. Values from the hw_srng_table_peach dump inside qca_cld3_peach_v2.ko.
    text = replace_once(
        text,
        '// Every ring, the link descriptors and the transmit buffers out of the window.',
        '''constexpr uint32_t kDpSw2WbmR0 = kUnitWbm + 0x37c, kDpSw2WbmR2 = kUnitWbm + 0x3010;
constexpr uint32_t kDpReoCmdR0 = kUnitReo + 0x2a8, kDpReoCmdR2 = kUnitReo + 0x3020;
constexpr uint32_t kDpReoStatusR0 = kUnitReo + 0xaa0, kDpReoStatusR2 = kUnitReo + 0x30a8;
constexpr uint32_t kDpReoReinjectR0 = kUnitReo + 0x320, kDpReoReinjectR2 = kUnitReo + 0x3028;
constexpr uint32_t kDpRingIdSw2Wbm = 121, kDpRingIdReoCmd = 20, kDpRingIdReoStatus = 21, kDpRingIdReoReinject = 16;
constexpr uint32_t kDpReoCmdEntryWords = 10, kDpReoStatusEntryWords = 28;

// Every ring, the link descriptors and the transmit buffers out of the window.''',
        'r75 fabric ring constants',
    )
    text = replace_once(
        text,
        '''      !plan(dp.idle, arena, kDpIdleEntries, kDpIdleEntryWords, kDpIdleLinkR0, kDpIdleLinkR2, 0, pointers, pointersBus, index))
    return false;
''',
        '''      !plan(dp.idle, arena, kDpIdleEntries, kDpIdleEntryWords, kDpIdleLinkR0, kDpIdleLinkR2, 0, pointers, pointersBus, index) ||
      !plan(dp.sw2wbm, arena, 128, kDpWbmEntryWords, kDpSw2WbmR0, kDpSw2WbmR2, kDpRingIdSw2Wbm, pointers, pointersBus, index))
    return false;
''',
        'r75 fabric ring planning',
    )
    text = replace_once(
        text,
        '''      program(dp, io, dp.txComp2, false);
      break;''',
        '''      program(dp, io, dp.txComp2, false);
      program(dp, io, dp.sw2wbm, true);
      break;''',
        'r75 fabric rings programmed',
    )
    text = replace_once(
        text,
        '  put32(e + 12, (dp.tclMetadata & 0xffffu) << kDpTclCmdNumShift);',
        '  put32(e + 12, (0x0401u | ((dp.vdevId & 0xffu) << 2)) << kDpTclCmdNumShift);',
        'Peach V1 fw_metadata target pdev=1 vdev=0 (0x0401)',
    )
    text = replace_once(
        text,
        '      if (cookie < kDpTxBuffers && dp.tx[cookie].busy && addrOf(e) == dp.tx[cookie].bus) dp.tx[cookie].busy = false;',
        '      if (cookie < kDpTxBuffers && dp.tx[cookie].busy && addrOf(e) == dp.tx[cookie].bus) dp.tx[cookie].busy = false;',
        'Peach +0x28 TX completion buffer address',
    )
    text = replace_once(
        text,
        """  for (uint32_t block = 0; block < kDpBlocks; ++block) {
    if (block > lastBlock) return;
    trace(block);
    switch (block) {
""",
        """  const uint32_t order[kDpBlocks] = {kDpBlockProbe, kDpBlockIdle, kDpBlockTcl, kDpBlockTxComp, kDpBlockReo,
                                     kDpBlockReoExc, kDpBlockRel, kDpBlockReoSetup};
  for (uint32_t position = 0; position < kDpBlocks; ++position) {
    const uint32_t block = order[position];
    if (position > lastBlock) return;
    trace(block);
    switch (block) {
""",
        'Peach WBM idle-link ring before data rings',
    )
    text = replace_once(
        text,
        '    dp.blocksDone = block + 1;',
        '    dp.blocksDone = position + 1;',
        'Peek ring programming order position',
    )
    return text.encode()
