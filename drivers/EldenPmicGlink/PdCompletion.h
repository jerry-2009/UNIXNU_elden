/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include "PdBootstrap.h"
#include "PdObservation.h"
/* Observe existing controller/telemetry state. Never advances the controller or
 * changes a GPIO, current limit, retry count or firmware result. */
static inline unsigned elden_pd_completion_state(const EldenPdBootstrap *s,const EldenPdBootInput *in){
    if(!s||!in)return EldenPdUnavailable;
    if(s->mode!=2)return EldenPdDisabled;
    if(s->phase==EldenPdBootFailed||s->error!=EldenPdBootOk||in->stop||in->icl_quarantined)return EldenPdFailed;
    if(s->phase!=EldenPdBootDone||!s->restored||!in->epoch||s->epoch!=in->epoch||!in->cycle||
       !in->link_up||!in->qualified||!in->raw_fresh||!in->high_voltage||!in->icl_owned||in->icl_pending||
       in->icl_applied!=500000||in->icl_observed!=500000||
       (in->pulse!=EldenPulseReady&&in->pulse!=EldenPulseRestored))return EldenPdPending;
    return EldenPdReady;
}
