"""One-shot SPMI page translation survey on first qualified charge availability."""
from VerificationSource import client as verified_client,replace

def client():
    text=verified_client().decode('utf-8')
    text=replace(text,'#include "ChargeVerification.h"','#include "ChargeVerification.h"\n#include "TranslationSurvey.h"')
    text=replace(text,'static unsigned usbIclSends;','static unsigned usbIclSends;\nstatic bool translationSurveyDone;')
    text=replace(text,'                if(available&&!__atomic_load_n(&policyAvailable,__ATOMIC_ACQUIRE)){',
        '''                if(available&&!translationSurveyDone){
                    translationSurveyDone=true;
                    bool ok=elden_spmi_translation::run(report);
                    report("\\nELDEN_SPMI_AT complete=%u; no charger register writes\\n",(unsigned)ok);
                }
                if(available&&!__atomic_load_n(&policyAvailable,__ATOMIC_ACQUIRE)){''')
    return text.encode('utf-8')
