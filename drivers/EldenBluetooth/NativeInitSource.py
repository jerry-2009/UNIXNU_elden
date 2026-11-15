"""The native completion callback, rather than optional0c5b, owns ready state."""
from ProcessLifetimeSource import source as lifetime_source
def host():
    text=lifetime_source().decode()
    return (text+'''
extern "C" int elden_bt_native_init_result(proc_t p,uint32_t result){
    Host *h=gEldenBtHost;if(!h||!p)return 0;
    int pid=proc_pid(p);uint64_t uniqueid=proc_uniqueid(p);
    IOLockLock(h->lock);
    bool matched=h->client_pid==pid&&h->client_uniqueid==uniqueid&&h->client_unit==h->bridge.unit&&
        h->bridge.client&&h->bridge.pid==pid&&h->bridge.link==PbLinkUp;
    bool accepted=matched&&!result&&!h->bridge.pending&&!h->bridge.own_reset&&
        !__atomic_load_n(&h->withdrawing,__ATOMIC_ACQUIRE)&&!elden_wcn_stop_requested();
    if(matched){h->bridge.ready=accepted;h->bridge.ready_noted=accepted;}
    IOLockUnlock(h->lock);return accepted?1:0;
}
''').encode()
def bridge(original):
    import hashlib
    if hashlib.sha256(original).hexdigest()!='7fddbf007f66d1055dd463432358708c5db4c8f743bab5a4985e2b88d86dd571':raise ValueError('Bridge source differs')
    line=b'    if (!status && f[1] == PbEvtCommandComplete && opcode == PbOpErroneousData) stack_ready(b, now);'
    if original.count(line)!=1:raise ValueError('Readiness heuristic differs')
    return original.replace(line,b'    /* Native init completion now decides ready; optional0c5b may be absent. */')
