/* SPDX-License-Identifier: GPL-2.0-only */
/* Included only by WcnPower.c; one physical supply/PDC implementation. */
static int shared_enter(EldenWcnSharedPower *s){
    if(!s)return EldenWcnPowerArgument;
    unsigned expected=0;
    return __atomic_compare_exchange_n(&s->busy,&expected,1,false,
        __ATOMIC_ACQUIRE,__ATOMIC_RELAXED)?0:EldenWcnPowerAgain;
}
static int shared_leave(EldenWcnSharedPower *s,int rc){
    __atomic_store_n(&s->busy,0,__ATOMIC_RELEASE);return rc;
}
static int shared_hold(EldenWcnSharedPower *s,int rc){
    __atomic_store_n(&s->faulted,1,__ATOMIC_RELEASE);
    __atomic_store_n(&s->live_mask,0,__ATOMIC_RELEASE);
    s->held=true;return fail(&s->supply,rc,true);
}
static bool shared_io_valid(const EldenWcnSharedPower *s){
    const EldenWcnPowerIo *io=&s->supply.io;
    return io->preflight&&io->rail_read&&io->rail_vote&&io->qmp&&
        io->bt_set&&io->bt_get&&io->wlan_get&&io->parents&&
        io->now_us&&io->delay_us&&s->wlan_set;
}
static int shared_levels(EldenWcnSharedPower *s,bool high[2]){
    EldenWcnPowerIo *io=&s->supply.io;
    int rc=io->bt_get(io->context,&high[EldenWcnBluetooth]);
    if(!rc)rc=io->wlan_get(io->context,&high[EldenWcnWlan]);
    return rc;
}
static int shared_set(EldenWcnSharedPower *s,unsigned consumer,bool high){
    EldenWcnPowerIo *io=&s->supply.io;
    int rc=consumer==EldenWcnBluetooth?io->bt_set(io->context,high):s->wlan_set(io->context,high);
    bool actual=!high;
    if(!rc)rc=consumer==EldenWcnBluetooth?io->bt_get(io->context,&actual):io->wlan_get(io->context,&actual);
    return rc?rc:actual==high?0:EldenWcnPowerIdentity;
}
static int shared_check_levels(EldenWcnSharedPower *s){
    bool high[2];int rc=shared_levels(s,high);if(rc)return rc;
    for(unsigned i=0;i<2;i++)
        if(high[i]!=(s->state[i]==EldenWcnLeaseOn))return EldenWcnPowerIdentity;
    return 0;
}
static int shared_acquire_locked(EldenWcnSharedPower *s,unsigned consumer,uint64_t epoch){
    EldenWcnPower *p=&s->supply;
    if(!shared_io_valid(s)||consumer>=2||!epoch)return EldenWcnPowerArgument;
    if(s->held||p->quarantined||s->state[consumer]!=EldenWcnLeaseOff||epoch<=s->epoch[consumer])
        return EldenWcnPowerAgain;
    /* Before first mutation both boot consumers must be known off. For a join,
     * validate both leases; never replay initial PDC/rail votes or peer reset. */
    int rc=p->io.preflight(p->io.context);
    if(!rc)rc=parents(p);
    if(!rc)rc=s->prepared?rails(p):read_targets(p);
    if(!rc)rc=shared_check_levels(s);
    if(rc)return s->prepared?shared_hold(s,rc):rc;
    s->epoch[consumer]=epoch;
    if(!s->prepared){
        p->control_started=true;
        for(unsigned i=0;i<4;i++){
            if((rc=p->io.qmp(p->io.context,initial[i])))return shared_hold(s,rc);
            p->qmp_messages++;
        }
        if((rc=shared_set(s,consumer,false)))return shared_hold(s,rc);
        for(unsigned i=0;i<EldenWcnRailCount;i++){
            if((rc=p->io.rail_vote(p->io.context,(EldenWcnRail)i,p->target[i],7,true)))
                return shared_hold(s,rc);
            p->rail_votes++;p->baseline_votes_retained=true;
        }
        if((rc=rails(p)))return shared_hold(s,rc);
        s->prepared=true;
    }
    if(consumer==EldenWcnBluetooth){
        if((rc=shared_set(s,consumer,false))||(rc=delay(p,50000)))return shared_hold(s,rc);
        bool wlan=false;
        if((rc=p->io.wlan_get(p->io.context,&wlan)))return shared_hold(s,rc);
        if(wlan!=(s->state[EldenWcnWlan]==EldenWcnLeaseOn))return shared_hold(s,EldenWcnPowerIdentity);
        if(!wlan&&(rc=delay(p,100000)))return shared_hold(s,rc);
    }else{
        /* A joining WLAN consumer still needs its own output configured low;
         * the first shared preparation may have belonged to Bluetooth. */
        if((rc=shared_set(s,consumer,false)))return shared_hold(s,rc);
    }
    /* WCN7861 has no inter-GPIO delay, but both targets have post-enable50ms. */
    if((rc=rails(p))||(rc=shared_set(s,consumer,true))||(rc=delay(p,50000)))
        return shared_hold(s,rc);
    s->state[consumer]=EldenWcnLeaseOn;
    if((rc=shared_check_levels(s))||(rc=rails(p)))return shared_hold(s,rc);
    __atomic_store_n(&s->live_epoch[consumer],epoch,__ATOMIC_RELEASE);
    __atomic_fetch_or(&s->live_mask,1u<<consumer,__ATOMIC_RELEASE);
    return 0;
}
int elden_wcn_shared_acquire(EldenWcnSharedPower *s,unsigned consumer,uint64_t epoch){
    int rc=shared_enter(s);if(rc)return rc;
    return shared_leave(s,shared_acquire_locked(s,consumer,epoch));
}
static int shared_live(EldenWcnSharedPower *s,unsigned consumer,uint64_t epoch){
    if(consumer>=2||!epoch||!shared_io_valid(s))return EldenWcnPowerArgument;
    if(s->held||s->supply.quarantined||!s->prepared||
       s->state[consumer]!=EldenWcnLeaseOn||s->epoch[consumer]!=epoch)return EldenWcnPowerAgain;
    return 0;
}
int elden_wcn_shared_stop(EldenWcnSharedPower *s,unsigned consumer,uint64_t epoch){
    int rc=shared_enter(s);if(rc)return rc;
    rc=shared_live(s,consumer,epoch);
    if(!rc){
        __atomic_fetch_and(&s->live_mask,~(1u<<consumer),__ATOMIC_RELEASE);
        rc=shared_check_levels(s);
        if(!rc)rc=shared_set(s,consumer,false);
        if(!rc&&consumer==EldenWcnBluetooth)rc=delay(&s->supply,100000);
        if(!rc){s->state[consumer]=EldenWcnLeaseOff;rc=shared_check_levels(s);}
        if(rc)shared_hold(s,rc);
        /* Shared baseline votes and their mapping owner remain platform-lived,
         * even when both known consumers are off. No unqualified rail disable. */
    }
    return shared_leave(s,rc);
}
int elden_wcn_shared_cpr(EldenWcnSharedPower *s,unsigned consumer,uint64_t epoch,
                       const EldenWcnPmuParam *params,size_t count){
    int rc=shared_enter(s);if(rc)return rc;
    rc=shared_live(s,consumer,epoch);
    if(!rc){
        rc=shared_check_levels(s);
        if(rc)shared_hold(s,rc);
        else{
            EldenWcnPdcVote own[4],combined[4];
            rc=elden_wcn_cpr_plan(params,count,own);
            if(!rc){
                /* A later client's request must not undercut the other radio.
                 * Retain stopped clients' votes until their next qualified
                 * request; stopping is never a shared rail-lowering event. */
                for(unsigned i=0;i<4;i++){
                    /* QMI may provide a partial update: omitted fields retain
                     * this consumer's prior request, exactly as omitted QMP
                     * commands retain firmware state. */
                    if(!own[i].wake_valid){own[i].wake=s->cpr[consumer][i].wake;own[i].wake_valid=s->cpr[consumer][i].wake_valid;}
                    if(!own[i].sleep_valid){own[i].sleep=s->cpr[consumer][i].sleep;own[i].sleep_valid=s->cpr[consumer][i].sleep_valid;}
                    EldenWcnPdcVote peer=s->cpr[1-consumer][i];
                    combined[i]=own[i];
                    if(peer.wake_valid){
                        combined[i].wake_valid=true;
                        if(peer.wake>combined[i].wake)combined[i].wake=peer.wake;
                    }
                    if(peer.sleep_valid){
                        combined[i].sleep_valid=true;
                        if(peer.sleep>combined[i].sleep)combined[i].sleep=peer.sleep;
                    }
                }
                rc=cpr_send_votes(&s->supply,combined);
                if(!rc)memcpy(s->cpr[consumer],own,sizeof(own));
                if(s->supply.quarantined)shared_hold(s,rc);
            }
        }
    }
    return shared_leave(s,rc);
}
int elden_wcn_shared_snapshot(EldenWcnSharedPower *s,EldenWcnSharedSnapshot *out){
    if(!out)return EldenWcnPowerArgument;
    int rc=shared_enter(s);if(rc)return rc;
    EldenWcnSharedSnapshot v={0};
    for(unsigned i=0;i<2;i++){v.epoch[i]=s->epoch[i];v.state[i]=s->state[i];}
    v.qmp_messages=s->supply.qmp_messages;v.rail_votes=s->supply.rail_votes;
    v.prepared=s->prepared;v.held=s->held;v.error=s->supply.error;
    v.baseline_votes_retained=s->supply.baseline_votes_retained;
    *out=v;return shared_leave(s,0);
}
int elden_wcn_shared_check(const EldenWcnSharedPower *s,unsigned consumer,uint64_t epoch){
    if(!s||consumer>=2||!epoch)return EldenWcnPowerArgument;
    uint64_t before=__atomic_load_n(&s->live_epoch[consumer],__ATOMIC_ACQUIRE);
    unsigned mask=__atomic_load_n(&s->live_mask,__ATOMIC_ACQUIRE);
    uint64_t after=__atomic_load_n(&s->live_epoch[consumer],__ATOMIC_ACQUIRE);
    if(__atomic_load_n(&s->faulted,__ATOMIC_ACQUIRE)||before!=epoch||after!=epoch||!(mask&(1u<<consumer)))
        return EldenWcnPowerAgain;
    return 0;
}
