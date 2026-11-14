"""Bind discovery accounting to the verified bridge's actual delivery points."""
from pathlib import Path
from ScanInitSource import host as previous_host,bridge as previous_bridge
ROOT=Path(__file__).resolve().parent

def host():
    text=previous_host().decode()
    old='#include "BtUtil.h"';assert text.count(old)==1
    text=text.replace(old,old+'\nint elden_bt_discovery_read(PbBridge*,uint32_t*,unsigned);')
    helper='''static void discovery_report(Host *h){
    uint32_t v[20];if(elden_bt_discovery_read(&h->bridge,v,20))return;
    char line[320];snprintf(line,sizeof(line),"ELDEN_BT_DISCOVERY tx=%u/%u/%u/%u/%u replies=%u/%u/%u/%u/%u status=%x/%x/%x/%x/%x inquiry-events=%u le=%u ext=%u incomplete=%u malformed=%u",
        v[0],v[1],v[2],v[3],v[4],v[5],v[6],v[7],v[8],v[9],v[10],v[11],v[12],v[13],v[14],v[15],v[16],v[17],v[18],v[19]);log(line);
}
'''
    old='static void finish(Host *h){';assert text.count(old)==1;text=text.replace(old,helper+old+'\n    discovery_report(h);')
    old='h->bridge.client,h->bridge.ready,h->bridge.packets_out,h->bridge.frames_up,h->bridge.frames_bad,h->bridge.pending);log(b);'
    assert text.count(old)==1;text=text.replace(old,old+'discovery_report(h);')
    return text.encode()

def bridge(original):
    text=previous_bridge(original).decode()
    anchor='static uint32_t ring_used';assert text.count(anchor)==1
    text=text.replace(anchor,(ROOT/'Discovery.inc').read_text()+ '\n'+anchor)
    old='    b->io = io;';assert text.count(old)==1;text=text.replace(old,old+'\n    discovery_init(b);')
    old='        else b->frames_up++;';assert text.count(old)==1;text=text.replace(old,'        else {b->frames_up++;discovery_up(b,b->scratch,bytes);}')
    old='    if (opcode == PbOpHostCompleted) return;';assert text.count(old)==1;text=text.replace(old,'    discovery_tx(b,opcode);\n'+old)
    return text.encode()
