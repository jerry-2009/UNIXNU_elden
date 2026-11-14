"""Fresh readback, finite verification and truthful availability; no policy value change."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parent
POLICY='baea8785f4353b020293126b7b109f40157f3287e34c080134ad3d70c29bdfeb'
CLIENT='6c7fbcb75b1fbc7aa39c286171d9e6859534a4f79c197a28ab8542b20321e17a'
CLIENT_PATH=ROOT.parents[1]/'profiles/v91/sources/power/PmicClient.cpp'

def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('Ambiguous charge verification delta: '+old[:80])
    return text.replace(old,new)

def policy():
    original=(ROOT/'ChargePolicy.c').read_bytes()
    if hashlib.sha256(original).hexdigest()!=POLICY:raise ValueError('Frozen charge policy changed')
    return replace(original.decode(),
        'void elden_charge_policy_timeout(EldenChargePolicy *s){if(s->pending){++s->timeouts;fail(s,UINT32_MAX);}}',
        'void elden_charge_policy_timeout(EldenChargePolicy *s){if(s->pending||(s->up&&(s->phase==EldenPolicyWaitWindow||s->phase==EldenPolicyWaitEnable))){++s->timeouts;fail(s,UINT32_MAX);}}').encode()

def client():
    # The declared build excludes the retired direct-DC experiment. Do not
    # restore that code from the broader historical driver working copy.
    original=CLIENT_PATH.read_bytes()
    if hashlib.sha256(original).hexdigest()!=CLIENT:raise ValueError('Frozen PMIC client changed')
    text=original.decode()
    text=replace(text,'#include "ChargePolicy.h"','#include "ChargePolicy.h"\n#include "ChargeVerification.h"')
    text=replace(text,'uint64_t policyDeadline=0,policyReadyAt=0;','uint64_t policyDeadline=0,policyReadyAt=0,policyVerifyDeadline=0;')
    text=replace(text,'policyDeadline=policyReadyAt=0;policyReported=false;','policyDeadline=policyReadyAt=policyVerifyDeadline=0;policyReported=false;')
    text=replace(text,'if(policyEnable==1&&poll.committed.valid==((UINT64_C(1)<<EldenChargeFieldCount)-1))',
        'if(policyEnable==1&&elden_charge_verify_fresh(ageMs,poll.committed.epoch,chargePolicy.epoch,!poll.quarantined,poll.committed.valid==((UINT64_C(1)<<EldenChargeFieldCount)-1)))')
    old='            if(chargePolicy.pending&&policyDeadline&&now>=policyDeadline)elden_charge_policy_timeout(&chargePolicy);'
    text=replace(text,old,old+'\n            elden_charge_verify_tick(&chargePolicy,milliseconds(now),poll.quarantined,&policyVerifyDeadline);')
    start=text.index('                const bool stable=policyReadyAt&&')
    end=text.index('                uint8_t request[24];int bytes=stable?',start)
    admission=text[start:end]
    text=text[:start]+text[end:]
    old='''                if(chargePolicy.original_saved&&chargePolicy.phase!=EldenPolicyReadWindow&&chargePolicy.phase!=EldenPolicyReadEu&&
                   !__atomic_load_n(&policyAvailable,__ATOMIC_ACQUIRE)){'''
    new=admission+'''                const bool available=elden_charge_verify_available(&chargePolicy,allowed);
                if(!available&&__atomic_load_n(&policyAvailable,__ATOMIC_ACQUIRE)){
                    __atomic_store_n(&policyAvailable,0,__ATOMIC_RELEASE);
                    report("\\nELDEN_CHARGE unavailable: awaiting fresh qualified telemetry\\n");
                }
                if(available&&!__atomic_load_n(&policyAvailable,__ATOMIC_ACQUIRE)){'''
    text=replace(text,old,new)
    if any(s in text for s in ('DcTrial.h','nativeDc','elden_dc_native_io')):raise ValueError('Retired direct-DC path reintroduced')
    return text.encode()
