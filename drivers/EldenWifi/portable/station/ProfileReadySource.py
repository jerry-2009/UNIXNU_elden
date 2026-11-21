"""Prepare the actual PMK before association; preserve donor crypto algorithms.

Derives fixed source using exact anchors and SHA. Historical donor/helper and
runtime remain unchanged. An ACK contains generation/status only and is bound
to the existing root-only socket's actual session by the kernel.
"""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STATION_SHA='516e1acd649bb4351932ebc678391270dac0a2dfbdb0373a2ff76443c6851781'
HELPER_SHA='7fae6d9b36858816c907b47af292561f4248ad569890678dd86a980fd5b0ad31'

def sha(data):return hashlib.sha256(data).hexdigest()

def derive(data,expected,edits):
    if sha(data)!=expected:raise ValueError('Profile readiness exact parent differs')
    original=text=data.decode()
    for before,after in edits:
        if text.count(before)!=1:raise ValueError('Profile readiness anchor differs: '+before[:80])
        text=text.replace(before,after,1)
    restored=text
    for before,after in reversed(edits):restored=restored.replace(after,before,1)
    if restored!=original:raise ValueError('Profile readiness modified unrelated behavior')
    return text.encode()

PREPARE=r'''
/* Cache the PMK as soon as PROFILE arrives, before LINK/association. The
 * original PBKDF2, PTK/MIC/replay/RSN/key-wrap routines are not modified. */
static bool elden_prepare_profile(const struct piano_wifi_8021x_profile *wire,
                                 struct profile *profile,struct pmk_state *ps,
                                 uint32_t *prepared_generation,
                                 send_fn send,void *context)
{
  struct profile incoming;
  memset(&incoming,0,sizeof incoming);
  struct elden_wifi_profile_ready answer={.generation=wire->generation,.status=EINVAL};
  bool parsed=wire->generation!=0&&profile_from_wire(wire,&incoming);
  if(parsed){
    const bool same=*prepared_generation==wire->generation&&
      profile->wpa2==incoming.wpa2&&profile->ssid_len==incoming.ssid_len&&
      memcmp(profile->ssid,incoming.ssid,sizeof incoming.ssid)==0&&
      memcmp(profile->psk,incoming.psk,sizeof incoming.psk)==0;
    const bool ready=same&&(!incoming.wpa2||ps->have);
    if(!ready){
      wipe(ps->pmk,sizeof ps->pmk);ps->have=false;*prepared_generation=0;
      *profile=incoming;
      if(!incoming.wpa2||set_pmk_profile(profile,ps)){
        *prepared_generation=wire->generation;answer.status=0;
      }else answer.status=EIO;
    }else answer.status=0;
  }
  if(answer.status){wipe(ps->pmk,sizeof ps->pmk);ps->have=false;*prepared_generation=0;wipe(profile,sizeof *profile);}
  wipe(&incoming,sizeof incoming);
  const int rc=send(context,ELDEN_WIFI_PROFILE_READY,&answer,sizeof answer,NULL,0);
  say("profile preparation generation %u status %d ack %d",answer.generation,answer.status,rc);
  return answer.status==0;
}
'''

def helper(data):
    # Exact donor whitespace is kept in the anchors below.
    edits=[
      ('#include "StationApi.h"','#include "StationApi.h"\n#include "ProfileReady.h"'),
      ('static int run(const char *profile_path, bool once)',PREPARE+'\nstatic int run(const char *profile_path, bool once)'),
      ('''      if (profile_from_wire(&wire, &menu_profile)) {
        menu_profile_valid = true;
        menu_profile_generation = wire.generation;
        if (menu_profile_generation == h.generation && menu_profile.wpa2 && !set_pmk_profile(&menu_profile, &ps)) {
          menu_profile_valid = false;
          say("the menu join profile's key could not be derived (generation %u)", wire.generation);
        }
      } else {
        say("the menu join profile message was refused (invalid lengths or security kind)");
      }''',
       '''      menu_profile_valid=elden_prepare_profile(&wire,&menu_profile,&ps,&menu_profile_generation,sock_send,NULL);'''),
      ('''          if (!set_pmk_profile(&menu_profile, &ps)) {''',
       '''          if (!ps.have) {'''),
    ]
    return derive(data,HELPER_SHA,edits)

READY_RECEIVE=r'''
    /* The privileged native transport supplies the real session. A stale
     * process/previous profile cannot arm this boot's association. */
    if(message&&bytes>=kNetHdrBytes&&netdetail::get16(message)==ELDEN_WIFI_PROFILE_READY){
        if(bytes!=kNetHdrBytes+sizeof(elden_wifi_profile_ready)||netdetail::get16(message+2)!=bytes)return -22;
        const uint32_t acknowledged=netdetail::get32(message+kNetHdrBytes);
        const int32_t status=(int32_t)netdetail::get32(message+kNetHdrBytes+4);
        lock();
        int result=!prepared||stopping||disabled?-108:
            !session||session!=control_session||acknowledged!=generation?-116:
            !profile_set||!profile_offered||!profile_pending?-107:status?-5:0;
        if(!result)profile_ready=true;
        unlock();
        const uint32_t facts[]={acknowledged,(uint32_t)status,(uint32_t)result};
        diag_line("PROFILE_READY generation/status/result",facts,3);
        return result;
    }
'''
def station(data):
    edits=[
      ('#include "StationApi.h"','#include "StationApi.h"\n#include "ProfileReady.h"'),
      ('    if(id==kWmiEvtVdevInstallKeyComplete){',
       '''    if(id==kWmiEvtVdevStartResp){
        uint32_t size=0;
        const uint8_t *reply=wmiFind(payload,bytes,kWmiTagVdevStartRespEvent,&size);
        if(reply&&size>=36&&wmiGet(reply,0)==link.options.vdevId){
            uint32_t facts[9];for(unsigned i=0;i<9;i++)facts[i]=wmiGet(reply,i);
            diag_line("VDEV_START_REPLY id/request/type/status/chains/smps/pdev/tx/rx",facts,9);
        }
    }
    if(id==kWmiEvtVdevInstallKeyComplete){'''),
      ('static bool profile_pending,profile_set,profile_sent,link_sent,leave_pending,query_pending,authorize_pending;',
       'static bool profile_pending,profile_set,profile_sent,profile_offered,profile_ready,link_sent,leave_pending,query_pending,authorize_pending;'),
      ('    if(profile_set&&!profile_sent&&session){',
       '    if(profile_set&&!profile_sent&&session){\n        profile_offered=true;'),
      ('    if(!rc){lock();if(control_session==session)profile_sent=true;unlock();}',
       '''    lock();
    if(control_session==session&&generation==p.generation){
        if(!rc)profile_sent=true;
        else{profile_offered=false;profile_ready=false;}
    }
    unlock();'''),
      ('const uint64_t revision=profile_revision;unlock();',
       'const uint64_t revision=profile_revision;const bool ready=profile_ready;unlock();'),
      ('if(pending&&connected&&sent&&(!station_began||staFinished(sta))){',
       'if(pending&&connected&&sent&&ready&&(!station_began||staFinished(sta))){'),
      ('if(!rc){control_session=session;profile_sent=false;link_sent=false;query_pending=true;reply_head=reply_tail=0;}',
       'if(!rc){control_session=session;profile_sent=false;profile_offered=false;profile_ready=false;link_sent=false;query_pending=true;reply_head=reply_tail=0;}'),
      ('if(control_session==session){control_session=0;profile_sent=false;leave_pending=true;',
       'if(control_session==session){control_session=0;profile_sent=false;profile_offered=false;profile_ready=false;leave_pending=true;'),
      ('    NetRequest request=netParseRequest(message,bytes);lock();',READY_RECEIVE+'\n    NetRequest request=netParseRequest(message,bytes);lock();'),
      ('profile=*value;profile_set=true;profile_pending=true;profile_sent=false;profile_revision++;',
       'profile=*value;profile_set=true;profile_pending=true;profile_sent=false;profile_offered=false;profile_ready=false;profile_revision++;'),
    ]
    return derive(data,STATION_SHA,edits)
