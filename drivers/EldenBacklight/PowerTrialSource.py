"""Fit the existing lower/restore observation inside the current recovery window."""
from BootSource import source as service_source

def source():
    text=service_source().decode('utf-8')
    old='''    /* Begin measurement after the startup load; keep 60s of final headroom.
     * Same schedule in the PD and non-PD controls; PD success is assessed
     * separately from its original logs, never inferred from this timer. */
    while(!rc&&left>240){
        rc=hold(c,"settle",1000);
        left=elden_recovery_deadline_remaining();
        if(!left)rc=-7;
    }'''
    new='''    /* A bounded observation under the existing smp-hold=240 guard.
     * Do not extend recovery merely to wait for a near-full battery to drain.
     * Compare baseline/dim/restored telemetry; this is not a full charge cycle. */
    rc=hold(c,"settle",30000);'''
    if text.count(old)!=1:raise ValueError('Unexpected old power-trial schedule')
    text=text.replace(old,new)
    for phase in ('baseline','dim','restored'):
        old='hold(c,"'+phase+'",60000)'
        if text.count(old)!=1:raise ValueError('Unexpected phase schedule')
        text=text.replace(old,'hold(c,"'+phase+'",45000)')
    return text.encode('utf-8')
