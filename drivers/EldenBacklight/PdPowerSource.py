"""Wait for the existing PD handoff before the bounded brightness observation."""
from PowerTrialSource import source as power_source

def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('Ambiguous PD power delta: '+old[:70])
    return text.replace(old,new)

def source():
    text=power_source().decode('utf-8')
    text=replace(text,'#include "Lifecycle.h"','#include "Lifecycle.h"\n#include "PdObservation.h"\nextern "C" unsigned elden_pd_power_observation(void) __attribute__((weak_import));')
    text=replace(text,'static volatile unsigned restoreConfirmed=1;','static volatile unsigned restoreConfirmed=1;\nstatic bool pdObservationActive;')
    text=replace(text,'        if(!sleepChecked(100))return -7;',
        '        if(pdObservationActive&&(!elden_pd_power_observation||elden_pd_power_observation()!=EldenPdReady))return -8;\n        if(!sleepChecked(100))return -7;')
    text=replace(text,'    return 0;\n}\nstatic void powerTrial(Context *c){',
        '''    return pdObservationActive&&(!elden_pd_power_observation||elden_pd_power_observation()!=EldenPdReady)?-8:0;
}
static void powerTrial(Context *c){
    if(!elden_pd_power_observation){report("\\nELDEN_BACKLIGHT PD observer unavailable\\n");return;}
    uint64_t waitUntil=now_us(nullptr)+240000000ull;unsigned state=EldenPdUnavailable;
    report("\\nELDEN_BACKLIGHT waiting for confirmed PD handoff\\n");
    while(!stopping()&&now_us(nullptr)<waitUntil){
        state=elden_pd_power_observation();
        if(state==EldenPdReady)break;
        if(state==EldenPdFailed||state==EldenPdDisabled)break;
        if(!sleepChecked(100))break;
    }
    if(stopping()||state!=EldenPdReady){report("\\nELDEN_BACKLIGHT PD handoff refused state=%u\\n",state);return;}''')
    text=replace(text,'    int rc=0;\n    report("\\nELDEN_BACKLIGHT power-settle',
        '    pdObservationActive=true;\n    int rc=0;\n    report("\\nELDEN_BACKLIGHT power-settle')
    old='        rc,restored,__atomic_load_n(&restoreConfirmed,__ATOMIC_ACQUIRE),c->chip.level,c->chip.writes,stopping());'
    text=replace(text,old,old+'\n    pdObservationActive=false;')
    return text.encode('utf-8')
