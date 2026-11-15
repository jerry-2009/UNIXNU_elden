/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Real driver + bounded OEM-contract model, not a hardware/full-cycle test.
 * The model's latch/precedence are bound by audit_charge_window_contract.py. */
#include "ChargePolicy.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct {
    unsigned window,eu,recharge,soc,enabled,manual,external_hold,cycle,disable_writes,enable_writes;
} Firmware;
static unsigned get(const unsigned char *p){return p[0]|(unsigned)p[1]<<8|(unsigned)p[2]<<16|(unsigned)p[3]<<24;}
static void put(unsigned char*p,unsigned v){for(unsigned i=0;i<4;i++)p[i]=(unsigned char)(v>>(8*i));}
static void tick(Firmware*f){
    if(f->manual||f->external_hold){f->enabled=0;return;}
    /* Property29 -> info19 -> 602ab94e is tested before property30's
     * info20 -> 602ab948. The previous model had these labels reversed. */
    unsigned w=f->window/100000?f->window:f->eu;
    if(! (w/100000)){f->enabled=1;return;}
    unsigned low=w/1000%100,high=w%1000;
    if(!(f->window/100000)&&f->recharge)low=high*f->recharge/100;
    /* Firmware truncates centi-percent capacity before comparisons. */
    unsigned soc=f->soc/100;
    if(soc>=high)f->enabled=0;
    else if(soc<=low)f->enabled=1;
}
static void observe(EldenChargePolicy*s,Firmware*f){
    tick(f);elden_charge_policy_observe(s,++f->cycle,f->soc,f->enabled);
}
static int transact(EldenChargePolicy*s,Firmware*f,unsigned error){
    unsigned char p[24],r[24]={0};int n=elden_charge_policy_next(s,true,p);
    if(!n)return 0;
    assert(n==24&&get(p)==32778&&get(p+4)==1&&get(p+12)==0);
    unsigned op=get(p+8),prop=get(p+16),v=get(p+20),value=0;
    if(op==0x60){assert(prop==29||prop==30);value=prop==29?f->window:f->eu;}
    else{
        assert(op==0x61&&(prop==28||prop==29));
        if(!error){
            if(prop==29){f->window=v;}
            else{assert(v<=1);f->manual=!v;f->enabled=v;if(v)f->enable_writes++;else f->disable_writes++;}
        }
    }
    put(r,32778);put(r+4,1);put(r+8,op);put(r+12,prop);put(r+16,value);put(r+20,error);
    int rc=elden_charge_policy_receive(s,r,24);assert(rc==(error?-1:1));return 1;
}
static void setup(EldenChargePolicy*s,Firmware*f,unsigned eu,unsigned soc){
    memset(f,0,sizeof(*f));f->window=95100;f->eu=eu;f->recharge=95;f->soc=soc;f->enabled=1;f->cycle=10;
    elden_charge_policy_init(s);elden_charge_policy_link(s,true);
    assert(transact(s,f,0));assert(transact(s,f,0));observe(s,f);
}
static void settle(EldenChargePolicy*s,Firmware*f){
    for(unsigned i=0;i<12;i++){
        transact(s,f,0);observe(s,f);
        if(s->phase==EldenPolicyReady&&s->applied_sequence==s->request_sequence)return;
    }
    assert(!"request did not settle");
}
static void select_mode(EldenChargePolicy*s,Firmware*f,unsigned mode){assert(!elden_charge_policy_select(s,mode));settle(s,f);}
int main(void){
    unsigned cases=0;EldenChargePolicy s;Firmware f;
    const unsigned modes[]={EldenChargeLimit80,EldenChargeWindow4060,EldenChargeStock};
    for(unsigned m=0;m<3;m++)for(unsigned e=0;e<2;e++){
        setup(&s,&f,e?176080:0,9000);select_mode(&s,&f,EldenChargeBypass);
        assert(f.manual&&f.disable_writes==1);
        select_mode(&s,&f,modes[m]);assert(s.applied_mode==modes[m]);
#ifdef ORIGINAL
        /* At high SOC the old policy treats a latched inhibit as a window hold. */
        if(modes[m]!=EldenChargeStock||e){assert(f.manual&&f.enable_writes==0);f.soc=2000;observe(&s,&f);assert(!f.enabled);}
#else
        assert(!f.manual&&f.enable_writes==1&&f.disable_writes==1);
        f.soc=2000;observe(&s,&f);assert(f.enabled);
        f.soc=9000;observe(&s,&f);assert(f.enabled==(modes[m]==EldenChargeStock&&!e));
        f.soc=2000;observe(&s,&f);assert(f.enabled); /* no second host SET needed */
#endif
        cases++;
    }
    /* Firmware is slow to evaluate a newly written limit: stale permission1
     * must not make the host latch SET28=0 on behalf of the automatic window. */
    setup(&s,&f,0,9000);assert(!elden_charge_policy_select(&s,EldenChargeLimit80));
    assert(transact(&s,&f,0));assert(transact(&s,&f,0));
    elden_charge_policy_observe(&s,f.cycle+2,9000,1);
#ifdef ORIGINAL
    assert(s.phase==EldenPolicySetEnable&&s.target_enable==0);assert(transact(&s,&f,0));assert(f.manual);
#else
    assert(s.phase==EldenPolicyReady);assert(!transact(&s,&f,0));assert(!f.manual&&!f.disable_writes);
    f.soc=2000;observe(&s,&f);assert(f.enabled);
#endif
    cases++;
#ifndef ORIGINAL
    /* An unrelated firmware protection may keep actual charging disabled. */
    setup(&s,&f,0,5000);select_mode(&s,&f,EldenChargeBypass);f.external_hold=1;
    select_mode(&s,&f,EldenChargeLimit80);assert(!f.manual&&!f.enabled&&s.firmware_held);
    f.external_hold=0;observe(&s,&f);assert(f.enabled);cases++;
    /* Refused or missing ACK must not report the inhibit as released. */
    for(unsigned timeout=0;timeout<2;timeout++){
        setup(&s,&f,0,9000);select_mode(&s,&f,EldenChargeBypass);
        unsigned before=s.applied_sequence;assert(!elden_charge_policy_select(&s,EldenChargeLimit80));
        assert(transact(&s,&f,0));assert(transact(&s,&f,0));observe(&s,&f);observe(&s,&f);
        assert(s.phase==EldenPolicySetEnable&&s.target_enable==1);
        if(timeout){unsigned char p[24];assert(elden_charge_policy_next(&s,true,p)==24);elden_charge_policy_timeout(&s);}
        else assert(transact(&s,&f,4));
        assert(s.phase==EldenPolicyFailed&&s.applied_sequence==before&&f.manual);cases++;
    }
    /* Normal protection wins; restoring its disabled stock window falls back
     * to EU without changing EU or its recharge parameter. */
    setup(&s,&f,176080,6500);select_mode(&s,&f,EldenChargeWindow4060);
    assert(!f.enabled&&!f.manual&&f.eu==176080&&!f.enable_writes&&!f.disable_writes);
    select_mode(&s,&f,EldenChargeStock);assert(f.enabled&&f.eu==176080&&f.recharge==95&&!f.enable_writes&&!f.disable_writes);cases++;
    /* Boundaries from the identified normal/EU branches distinguish this
     * contract from the prior reversed/centi-percent model. */
    setup(&s,&f,140060,5000);f.enabled=0;tick(&f);assert(f.enabled);cases++;
    f.recharge=0;f.enabled=0;tick(&f);assert(!f.enabled);cases++;
    f.window=140060;f.recharge=95;f.enabled=0;tick(&f);assert(!f.enabled);cases++;
    f.soc=4099;tick(&f);assert(f.enabled);cases++;
    f.soc=4100;f.enabled=0;tick(&f);assert(!f.enabled);cases++;
    f.soc=5999;f.enabled=1;tick(&f);assert(f.enabled);cases++;
    f.soc=6000;tick(&f);assert(!f.enabled);cases++;
#endif
    printf("PASS %u charge-window contract scenarios\n",cases);
}
