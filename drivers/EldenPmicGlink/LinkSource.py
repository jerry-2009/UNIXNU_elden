"""Recover manual charge inhibit across transport loss.

The frozen v139/v140 inputs remain unchanged. Both the policy and its native
consumer must be rebuilt with header() for this explicit derived variant.
"""
import hashlib
from pathlib import Path
from WindowSource import policy as window_policy
from VerificationSource import client as verified_client, replace

ROOT = Path(__file__).resolve().parent
HEADER = "ffa9a0c4cb4aee9a4f0881058365306dcd8e0cb1c1b5fc8356322e18c48a0605"
POLICY = "ff0847a18b64859ab7543f8cca21c0b5e5c11e293bbbdee0aae8e4ad1a867726"


def header():
    original = (ROOT / "ChargePolicy.h").read_bytes()
    if hashlib.sha256(original).hexdigest() != HEADER:
        raise ValueError("Frozen charge policy header changed")
    old = "    uint32_t last_opcode,last_property,last_value,errors,timeouts,firmware_error;"
    new = old + """
    /* SET28=0 can take effect before ACK/readback. Link loss and errors do not
     * relinquish that possible inhibit. A valid successful SET28=1 ACK does.
     * A known unsent SET28=0 restores only its prior ownership state. */
    bool manual_inhibit_possible,manual_inhibit_before_send;"""
    return replace(original.decode("utf-8"), old, new).encode("utf-8")


def policy():
    original = window_policy()
    if hashlib.sha256(original).hexdigest() != POLICY:
        raise ValueError("Frozen charge window policy changed")
    text = replace(original.decode("utf-8"),
                   "if(s->applied_mode==EldenChargeBypass){",
                   "if(s->manual_inhibit_possible){")
    text = replace(text, "    if(up){++s->epoch;if(s->requested_mode)++s->request_sequence;}", """    if(up){
        ++s->epoch;
        if(s->requested_mode)++s->request_sequence;
    }else if(s->requested_mode==EldenChargeBypass){
        /* Do not re-enter manual inhibit after a broken transport. Restore
         * the original automatic window and release any inhibit we may own. */
        s->requested_mode=EldenChargeStock;
    }""")
    old = "    s->last_opcode=op;s->last_property=prop;s->last_value=value;s->pending=true;return 24;"
    new = """    if(op==0x61&&prop==28&&value==0){
        s->manual_inhibit_before_send=s->manual_inhibit_possible;
        s->manual_inhibit_possible=true;
    }
""" + old
    text = replace(text, old, new)
    old = "void elden_charge_policy_unsent(EldenChargePolicy *s){s->pending=false;}"
    new = """void elden_charge_policy_unsent(EldenChargePolicy *s){
    if(s->pending&&s->last_opcode==0x61&&s->last_property==28&&s->last_value==0)
        s->manual_inhibit_possible=s->manual_inhibit_before_send;
    s->pending=false;
}"""
    text = replace(text, old, new)
    old = "    if(get(p+20))return fail(s,get(p+20));\n    s->pending=false;"
    new = """    if(get(p+20))return fail(s,get(p+20));
    if(s->last_opcode==0x61&&s->last_property==28&&s->last_value==1)
        s->manual_inhibit_possible=false;
    s->pending=false;"""
    text = replace(text, old, new)
    return text.encode("utf-8")


def client():
    text = verified_client().decode("utf-8")
    text = replace(text, """    if (__atomic_exchange_n(&linkUp,up,__ATOMIC_ACQ_REL)!=up)
        __atomic_add_fetch(&linkEpoch,1,__ATOMIC_RELEASE);""", """    if (__atomic_exchange_n(&linkUp,up,__ATOMIC_ACQ_REL)!=up) {
        __atomic_store_n(&policyAvailable,0,__ATOMIC_RELEASE);
        __atomic_add_fetch(&linkEpoch,1,__ATOMIC_RELEASE);
    }""")
    old = """            if(policyEnable==1){elden_charge_policy_link(&chargePolicy,false);elden_charge_policy_link(&chargePolicy,nowUp);}"""
    text = replace(text, old, """            if(policyEnable==1){
                const unsigned request=__atomic_load_n(&policyRequestSequence,__ATOMIC_ACQUIRE);
                if(request!=policySeenRequest && __atomic_load_n(&policyRequested,__ATOMIC_ACQUIRE)==EldenChargeBypass)
                    policySeenRequest=request;
                elden_charge_policy_link(&chargePolicy,false);
                elden_charge_policy_link(&chargePolicy,nowUp);
            }""")
    old = """                if(available&&!__atomic_load_n(&policyAvailable,__ATOMIC_ACQUIRE)){
                    __atomic_store_n(&policyAvailable,1,__ATOMIC_RELEASE);"""
    text = replace(text, old, """                IOLockLock(lock);
                const bool publishReady=available&&__atomic_load_n(&linkUp,__ATOMIC_ACQUIRE)&&
                    __atomic_load_n(&linkEpoch,__ATOMIC_ACQUIRE)==seen&&
                    !__atomic_load_n(&policyAvailable,__ATOMIC_ACQUIRE);
                if(publishReady)__atomic_store_n(&policyAvailable,1,__ATOMIC_RELEASE);
                IOLockUnlock(lock);
                if(publishReady){""")
    old = """    if(!__atomic_load_n(&policyAvailable,__ATOMIC_ACQUIRE))return -2;
    __atomic_store_n(&policyRequested,mode,__ATOMIC_RELEASE);
    __atomic_add_fetch(&policyRequestSequence,1,__ATOMIC_RELEASE);"""
    text = replace(text, old, """    if(!__atomic_load_n(&policyAvailable,__ATOMIC_ACQUIRE))return -2;
    IOLockLock(lock);
    if(!__atomic_load_n(&policyAvailable,__ATOMIC_ACQUIRE)){
        IOLockUnlock(lock);
        return -2;
    }
    __atomic_store_n(&policyRequested,mode,__ATOMIC_RELEASE);
    __atomic_add_fetch(&policyRequestSequence,1,__ATOMIC_RELEASE);
    IOLockUnlock(lock);""")
    return text.encode("utf-8")
