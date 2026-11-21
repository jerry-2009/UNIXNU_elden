"""Short PD option and coherent read-only observation of the existing controller."""
from VerificationSource import client as verified_client,replace

def client():
    return with_pd_observation(verified_client())

def recovery_client():
    from LinkSource import client as link_client
    text=with_pd_observation(link_client()).decode('utf-8')
    return replace(text, 'const bool allowed=stable&&poll.committed.value[EldenChargePresent]',
        '''/* The startup handoff temporarily owns the input limit. Wait
                 * until its transition ends before changing battery policy. */
                const bool pdSettled=bootMode!=2||
                    ((bootstrap.phase==EldenPdBootDone||bootstrap.phase==EldenPdBootFailed)&&
                     !icl.suspend_requested&&!icl.quarantined);
                const bool allowed=stable&&pdSettled&&poll.committed.value[EldenChargePresent]''').encode('utf-8')

def with_pd_observation(source):
    text=source.decode('utf-8')
    text=replace(text,'#include "PdBootstrap.h"','#include "PdBootstrap.h"\n#include "PdCompletion.h"')
    text=replace(text,'static unsigned usbIclSends;','static unsigned usbIclSends;\nstatic volatile uint64_t pdObservation;\nstatic unsigned pdObservationSeen=EldenPdUnavailable;')
    text=replace(text,'PE_parse_boot_argn("elden-pd-bootstrap",&bootMode,sizeof(bootMode));',
        'if(!PE_parse_boot_argn("elden-pd-bootstrap",&bootMode,sizeof(bootMode)))PE_parse_boot_argn("epd",&bootMode,sizeof(bootMode));')
    old='            policyDeadline=policyReadyAt=policyVerifyDeadline=0;policyReported=false;'
    text=replace(text,old,old+'\n            __atomic_store_n(&pdObservation,elden_pd_observation_pack(bootMode==2?EldenPdPending:EldenPdDisabled,epoch,milliseconds(mach_absolute_time())),__ATOMIC_RELEASE);')
    old='                __atomic_store_n(&bootstrapStopped,(unsigned)(input.stop&&action.stop_ready),__ATOMIC_RELEASE);'
    text=replace(text,old,old+'''
                unsigned observation=elden_pd_completion_state(&bootstrap,&input);
                __atomic_store_n(&pdObservation,elden_pd_observation_pack(observation,seen,input.now_ms),__ATOMIC_RELEASE);
                if(observation!=pdObservationSeen){
                    pdObservationSeen=observation;
                    report("\\nELDEN_PD_POWER state=%u phase=%u error=%u epoch=%u cycle=%u\\n",observation,(unsigned)bootstrap.phase,(unsigned)bootstrap.error,seen,input.cycle);
                }''')
    text+='''
extern "C" unsigned elden_pd_power_observation(void){
    if(__atomic_load_n(&bootstrapStop,__ATOMIC_ACQUIRE))return EldenPdFailed;
    if(!__atomic_load_n(&linkUp,__ATOMIC_ACQUIRE))return EldenPdUnavailable;
    unsigned before=__atomic_load_n(&linkEpoch,__ATOMIC_ACQUIRE);
    uint64_t value=__atomic_load_n(&pdObservation,__ATOMIC_ACQUIRE);
    unsigned after=__atomic_load_n(&linkEpoch,__ATOMIC_ACQUIRE);
    if(before!=after||!__atomic_load_n(&linkUp,__ATOMIC_ACQUIRE))return EldenPdUnavailable;
    if(__atomic_load_n(&bootstrapStop,__ATOMIC_ACQUIRE))return EldenPdFailed;
    return elden_pd_observation_read(value,after,milliseconds(mach_absolute_time()));
}
'''
    if 'elden_usb_icl_sdp_only(&icl,iclEnable==2);if(iclEnable==2)iclEnable=1;' not in text:raise ValueError('SDP-only normalization changed')
    if any(s in text for s in ('DcTrial.h','nativeDc','elden_dc_native_io')):raise ValueError('Retired DC path reintroduced')
    return text.encode('utf-8')
