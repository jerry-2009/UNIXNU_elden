"""Complete exact WCN7861 board sideband pinctrl before power/enable."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi'))
import BatteryAdmissionSource as battery


def source(board_state=False):
    text=battery.wcn().decode()
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('Sideband source anchor changed: '+old[:90])
        text=text.replace(old,new,1)
    replace('#include "WlanGpio.h"','#include "WlanGpio.h"\n#include "SidebandPins.h"')
    replace('Region gcc,core,owner,observer,writer,aoss,ipcc,rsc,wlan;',
        'Region gcc,core,owner,observer,writer,aoss,ipcc,rsc,wlan,sideband_maps[3];\n    EldenWifiSideband sideband={};')
    marker='static int platform_get(Context **out){'
    helper='''static int sideband_read(void *p,unsigned pin,unsigned off,uint32_t *v){
    Context *c=static_cast<Context *>(p);if(pin>=3||off>8||(off&3)||!v)return -22;
    *v=c->sideband_maps[pin].read(off);return *v==UINT32_MAX?-5:0;
}
static int sideband_write(void *p,unsigned pin,unsigned off,uint32_t v){
    Context *c=static_cast<Context *>(p);if(pin>=3||(off!=0&&(pin!=2||off!=4)))return -22;
    c->sideband_maps[pin].write(off,v);return 0;
}
static int sideband_prepare(Context *c){
    static const unsigned gpios[]={18,19,202};
    bool wlan=true,bt=true;int rc=preflight(c);
    if(!rc)rc=wlan_get(c,&wlan);if(!rc)rc=bt_get(c,&bt);
    if(rc||wlan||bt)return rc?rc:-16;
    for(unsigned i=0;i<3;i++)if(!c->sideband_maps[i].map(0x0f100000ULL+gpios[i]*0x1000ULL,0x1000))return -12;
    c->sideband.context=c;c->sideband.read=sideband_read;c->sideband.write=sideband_write;
    rc=elden_wifi_sideband_prepare(&c->sideband);
    for(unsigned i=0;i<3;i++)log("\\nELDEN_WIFI_SIDEBAND pin=%u before=%x/%x/%x after=%x/%x/%x rc=%d writes=%u held=%u\\n",
        gpios[i],c->sideband.before[i][0],c->sideband.before[i][1],c->sideband.before[i][2],
        c->sideband.after[i][0],c->sideband.after[i][1],c->sideband.after[i][2],rc,c->sideband.writes,c->sideband.held);
    return rc;
}
'''
    replace(marker,helper+marker)
    marker='    c->wlan_gpio={c,wlan_read,wlan_write,delay,false,false};c->shared.wlan_set=wlan_set;'
    replace(marker,marker+'''
    int sideband=sideband_prepare(c);
    if(sideband){__atomic_store_n(&active,c,__ATOMIC_RELEASE);__atomic_store_n(&platform_init_state,3,__ATOMIC_RELEASE);return sideband;}
''')
    if board_state:
        marker='static void publish(Context *c){'
        replace(marker,(ROOT/'drivers/EldenWifi/BoardState.inc').read_text(encoding='utf-8')+'\n'+marker)
        text+='\nextern "C" int elden_wifi_board_state(unsigned stage){return board_state(stage);}\n'
    return text.encode()
