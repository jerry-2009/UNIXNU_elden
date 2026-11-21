/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Actual policy with the existing OEM-contract peer, no device access. */
#include "ChargeLinkFirmware.inc"

static void inhibit_request(EldenChargePolicy *s,Firmware *f,unsigned state){
    unsigned char request[24],reply[24]={0};
    assert(!elden_charge_policy_select(s,EldenChargeBypass));
    assert(elden_charge_policy_next(s,true,request)==24);
    assert(get(request+8)==0x61&&get(request+16)==28&&get(request+20)==0);
    if(state==3){elden_charge_policy_unsent(s);return;} /* known send refusal */
    f->manual=1;f->enabled=0;f->disable_writes++;
    if(state==0)return; /* accepted transport send, no response received */
    put(reply,32778);put(reply+4,1);put(reply+8,0x61);put(reply+12,28);
    assert(elden_charge_policy_receive(s,reply,24)==1);
    if(state==2){observe(s,f);observe(s,f);assert(s->applied_mode==EldenChargeBypass);}
    else assert(s->phase==EldenPolicyWaitEnable);
}

int main(void){
    EldenChargePolicy s;Firmware f;unsigned cases=0;
    setup(&s,&f,0,5000);select_mode(&s,&f,EldenChargeStock);
    assert(s.applied_mode==EldenChargeStock&&!f.manual);
    const unsigned modes[]={EldenChargeLimit80,EldenChargeWindow4060,EldenChargeStock};
    for(unsigned m=0;m<3;m++)for(unsigned soc=0;soc<2;soc++)for(unsigned state=0;state<4;state++){
        setup(&s,&f,0,soc?9000:5000);inhibit_request(&s,&f,state);
        assert(!elden_charge_policy_select(&s,modes[m]));
        unsigned sequence=s.applied_sequence;
        elden_charge_policy_link(&s,false);assert(!s.up&&s.phase==EldenPolicyOff);
        assert(s.applied_sequence==sequence);
        elden_charge_policy_link(&s,true);settle(&s,&f);
        assert(s.applied_mode==modes[m]&&s.applied_sequence==s.request_sequence);
#ifdef ORIGINAL
        if(state<2){
            assert(f.manual&&!f.enabled&&f.enable_writes==0);
            f.soc=2000;observe(&s,&f);assert(!f.enabled);
        }else{
            assert(!f.manual&&f.enable_writes==(state==2));
        }
#else
        assert(!f.manual&&f.enable_writes==(state!=3));
        assert(f.disable_writes==(state!=3));
        f.soc=2000;observe(&s,&f);assert(f.enabled);
        assert(!s.manual_inhibit_possible);
#endif
        cases++;
    }
#ifndef ORIGINAL
    /* Timeout and explicit/malformed failures lose no ownership facts. */
    for(unsigned failure=0;failure<3;failure++){
        setup(&s,&f,0,9000);inhibit_request(&s,&f,0);
        assert(!elden_charge_policy_select(&s,EldenChargeLimit80));
        unsigned applied=s.applied_sequence;
        if(failure==0)elden_charge_policy_timeout(&s);
        else{
            unsigned char response[24]={0};put(response,32778);put(response+4,1);put(response+8,0x61);
            if(failure==1)put(response+20,4);
            assert(elden_charge_policy_receive(&s,response,failure==2?20:24)==-1);
        }
        assert(s.phase==EldenPolicyFailed&&s.applied_sequence==applied&&s.manual_inhibit_possible);
        elden_charge_policy_link(&s,false);elden_charge_policy_link(&s,true);settle(&s,&f);
        assert(!f.manual&&f.enable_writes==1&&!s.manual_inhibit_possible);cases++;
    }
    /* A successful release ACK clears ownership even while firmware holds0. */
    setup(&s,&f,0,9000);select_mode(&s,&f,EldenChargeBypass);
    assert(s.manual_inhibit_possible);assert(!elden_charge_policy_select(&s,EldenChargeLimit80));
    assert(transact(&s,&f,0));assert(transact(&s,&f,0));observe(&s,&f);observe(&s,&f);
    assert(s.phase==EldenPolicySetEnable);assert(transact(&s,&f,0));
    assert(!s.manual_inhibit_possible&&!f.manual&&f.enable_writes==1);
    elden_charge_policy_link(&s,false);elden_charge_policy_link(&s,true);settle(&s,&f);
    assert(f.enable_writes==1&&!f.manual&&s.applied_mode==EldenChargeLimit80);cases++;
    /* Failed release keeps evidence across link changes until a valid ACK. */
    setup(&s,&f,0,9000);select_mode(&s,&f,EldenChargeBypass);
    assert(!elden_charge_policy_select(&s,EldenChargeLimit80));
    assert(transact(&s,&f,0));assert(transact(&s,&f,0));observe(&s,&f);observe(&s,&f);
    assert(s.phase==EldenPolicySetEnable);assert(transact(&s,&f,4));
    assert(s.phase==EldenPolicyFailed&&s.manual_inhibit_possible&&f.manual);
    elden_charge_policy_link(&s,false);elden_charge_policy_link(&s,true);settle(&s,&f);
    assert(!s.manual_inhibit_possible&&!f.manual);cases++;
    /* A queued request that never reaches the transport owns no inhibit. */
    setup(&s,&f,0,5000);inhibit_request(&s,&f,3);
    assert(!s.manual_inhibit_possible);assert(!elden_charge_policy_select(&s,EldenChargeStock));
    elden_charge_policy_link(&s,false);elden_charge_policy_link(&s,true);settle(&s,&f);
    assert(!f.manual&&!f.enable_writes&&!f.disable_writes);cases++;
#endif
    printf("PASS %u actual charge-policy reconnect scenarios; partial writes and original threshold ownership\n",cases);
    return 0;
}
