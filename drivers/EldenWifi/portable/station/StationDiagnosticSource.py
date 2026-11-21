"""Add one consolidated first-TX observation to the unchanged portable station.

No register writes/credits/timeout changes. Logs only protocol metadata and
the already-owned TCL/WBM configuration/pointers, not frame/key/SSID data.
"""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parent
EXPECTED='f3fe353a613312777d6d04a80f4a2a1af86568a8543579f22ece4be39b238c21'
OBSERVATION=r'''
static void diag_line(const char *name,const uint32_t *values,unsigned count){
    if(!owner_io.note)return;
    char text[256];unsigned at=0;
    while(*name&&at<80)text[at++]=*name++;
    static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<count&&at+10<sizeof(text);i++){
        text[at++]=' ';
        for(unsigned nibble=0;nibble<8;nibble++)text[at++]=hex[(values[i]>>(28-4*nibble))&15];
    }
    text[at]=0;owner_io.note(owner_io.owner,805,text);
}
static void tx_diagnostic(uint64_t now){
    static uint64_t first_tx;static unsigned sampled;
    if(!dp.st.txFrames||sampled)return;
    if(!first_tx){first_tx=now;return;}
    if(now-first_tx<2000)return;
    sampled=1;
    const ChipIo io{owner_io.owner,owner_io.read,owner_io.write};
    const uint32_t state[]={dp.st.txFrames,dp.st.txCompletions,dp.st.txAcked,
        dp.tcl.ours,dpdetail::load(dp.tcl.theirs),dp.txComp.ours,dpdetail::load(dp.txComp.theirs),
        (uint32_t)dp.txReady,sta.peerId,sta.hwPeerId,(uint32_t)sta.peerMapped,
        dp.searchIndex,dp.cacheSet,dp.tclMetadata};
    diag_line("TX_STATE submitted/completed/acked TCL-own/device WBM-own/device ready peer/hw/mapped search/hash/meta",state,14);
    const uint32_t offsets[]={0,4,8,0x10,0x1c,0x20};uint32_t tcl[8],wbm[8];
    for(unsigned i=0;i<6;i++)tcl[i]=io.read(io.ctx,dp.tcl.r0+offsets[i]);
    tcl[6]=io.read(io.ctx,dp.tcl.r2);tcl[7]=io.read(io.ctx,dp.tcl.r2+4);
    diag_line("TCL_CONFIG base/msb/id/misc/tp-lo/tp-hi/HP/TP",tcl,8);
    const uint32_t woffsets[]={0,4,8,0x10,0x14,0x18};
    for(unsigned i=0;i<6;i++)wbm[i]=io.read(io.ctx,dp.txComp.r0+woffsets[i]);
    wbm[6]=io.read(io.ctx,dp.txComp.r2);wbm[7]=io.read(io.ctx,dp.txComp.r2+4);
    diag_line("WBM_CONFIG base/msb/id/misc/hp-lo/hp-hi/HP/TP",wbm,8);
    const uint32_t config[]={io.read(io.ctx,kDpTclBankConfig),dp.bank,sta.choice.freq,
        (uint32_t)sta.vdevUp,(uint32_t)sta.rsn,htt.versionMajor,htt.versionMinor,
        io.read(io.ctx,0x3004),io.read(io.ctx,0x38),io.read(io.ctx,0x48)};
    diag_line("TX_CONTRACT bank-config/id/frequency/up/RSN/HTTmajor/minor/wake/MHIcontrol/status",config,10);
    const uint32_t desc[]={dpdetail::get32(dp.tcl.va+8),dpdetail::get32(dp.tcl.va+12),
        dpdetail::get32(dp.tcl.va+16),dpdetail::get32(dp.tcl.va+20),dpdetail::get32(dp.tcl.va+24),dpdetail::get32(dp.tcl.va+28)};
    diag_line("TX_DESC metadata-only words2..7",desc,6);
}
'''

def source(data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED:raise ValueError('Exact full-station code required')
    original=text=data.decode();changes=[]
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('Station diagnostic anchor differs: '+old[:70])
        text=text.replace(old,new,1);changes.append((old,new))
    replace('static void station_turn(uint64_t now){',OBSERVATION+'\nstatic void station_turn(uint64_t now){')
    replace('follow(now);key_turn(now);transmit();port_replies();publish_snapshot();protocol_status(out);',
            'follow(now);key_turn(now);transmit();tx_diagnostic(now);port_replies();publish_snapshot();protocol_status(out);')
    replace('    if(id==kWmiEvtVdevInstallKeyComplete){',r'''    if(id==kWmiEvtPdevSetHwModeResp){
        uint32_t size=0;const uint8_t *p=wmiFind(payload,bytes,kWmiTagPdevSetHwModeResp,&size);
        if(p&&size>=16){uint32_t values[]={wmiGet(p,0),wmiGet(p,1),wmiGet(p,2),wmiGet(p,3)};diag_line("MODE_REPLY pdev/status/configured/mappings",values,4);}
    }
'''+ '    if(id==kWmiEvtVdevInstallKeyComplete){')
    replace('static bool hook(void *,uint32_t id,', 'static void diag_line(const char *,const uint32_t *,unsigned);\nstatic bool hook(void *,uint32_t id,')
    replace('        if(n)(void)send_message(session,message,n);',r'''        const auto kind=netEapolKind(frame+14,bytes-14);
        uint32_t facts[]={kind.message,bytes-14,(uint32_t)dp.txReady,(uint32_t)sta.vdevUp};diag_line("EAPOL_RX message/bytes/TXready/up",facts,4);
        if(n)(void)send_message(session,message,n);''')
    restored=text
    for old,new in reversed(changes):restored=restored.replace(new,old,1)
    if restored!=original:raise ValueError('Diagnostic changed functional code')
    return text.encode()
