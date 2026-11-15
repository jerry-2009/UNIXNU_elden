"""Keep process references local to a callback; bind persistent identity by PID/uniqueid."""
from RegistrySource import source as registry_source
def source():
    text=registry_source().decode()
    def change(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('Ambiguous process-lifetime delta')
        text=text.replace(old,new)
    change('    proc_t client_proc=nullptr;','    int client_pid=0;uint64_t client_uniqueid=0;uint32_t client_unit=0;')
    change('    proc_t proc=proc_find(pid);if(proc==nullptr)return ESRCH;', '''    proc_t proc=proc_find(pid);if(proc==nullptr)return ESRCH;
    uint64_t uniqueid=proc_uniqueid(proc);
    if(!uniqueid){proc_rele(proc);return ESRCH;}''')
    change('    if(h->client_proc!=nullptr){IOLockUnlock(h->lock);proc_rele(proc);return EBUSY;}\n    h->client_proc=proc;IOLockUnlock(h->lock);', '''    if(h->client_pid!=0){IOLockUnlock(h->lock);proc_rele(proc);return EBUSY;}
    h->client_pid=pid;h->client_uniqueid=uniqueid;h->client_unit=address->sc_unit;IOLockUnlock(h->lock);
    proc_rele(proc);proc=nullptr;''')
    change('        IOLockLock(h->lock);if(h->client_proc==proc)h->client_proc=nullptr;IOLockUnlock(h->lock);\n        proc_rele(proc);return rc==PbBridgeBusy?EBUSY:ECONNREFUSED;', '''        IOLockLock(h->lock);
        if(h->client_pid==pid&&h->client_uniqueid==uniqueid&&h->client_unit==address->sc_unit){h->client_pid=0;h->client_uniqueid=0;h->client_unit=0;}
        IOLockUnlock(h->lock);
        return rc==PbBridgeBusy?EBUSY:ECONNREFUSED;''')
    change('    IOLockLock(h->lock);proc_t p=h->client_proc;h->client_proc=nullptr;IOLockUnlock(h->lock);\n    if(p!=nullptr)proc_rele(p);return 0;', '''    IOLockLock(h->lock);if(h->client_unit==unit){h->client_pid=0;h->client_uniqueid=0;h->client_unit=0;}IOLockUnlock(h->lock);
    return 0;''')
    change('    IOLockLock(h->lock);proc_t p=h->client_proc;h->client_proc=nullptr;\n    int pid=h->bridge.kill_pid;IOLockUnlock(h->lock);', '''    IOLockLock(h->lock);int client_pid=h->client_pid;uint64_t uniqueid=h->client_uniqueid;
    h->client_pid=0;h->client_uniqueid=0;h->client_unit=0;
    int pid=h->bridge.kill_pid;IOLockUnlock(h->lock);''')
    change('    if(p!=nullptr){if(proc_pid(p)==pid&&pid>0)psignal(p,SIGKILL);proc_rele(p);}', '''    if(pid>0&&pid==client_pid&&uniqueid){
        proc_t p=proc_find(pid);
        if(p){if(proc_uniqueid(p)==uniqueid)psignal(p,SIGKILL);proc_rele(p);}
    }''')
    if 'client_proc' in text:raise ValueError('Persistent process reference remains')
    return text.encode()
