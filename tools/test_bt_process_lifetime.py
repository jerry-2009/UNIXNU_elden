"""Reproduce the old per-thread reference leak and exercise fixed callbacks."""
from pathlib import Path
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth'))
from RegistrySource import source as old_source
from ProcessLifetimeSource import source as new_source
def functions(data):
    text=data.decode();parts=[]
    for marker in ('static errno_t connect(','static errno_t disconnect(','static void finish('):
        a=text.index(marker);b=text.index('\n}\n',a)+2;parts.append(text[a:b])
    return '\n'.join(parts)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
    prefix=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cerrno>
#include <csignal>
#include <initializer_list>
using errno_t=int;using kern_ctl_ref=void*;using u_int32_t=uint32_t;
struct Proc{int pid;uint64_t unique;};using proc_t=Proc*;
struct sockaddr_ctl{uint32_t sc_unit;};struct Bridge{int kill_pid=0;unsigned guard=0,packets_out=0,frames_up=0,tx_dropped=0;};
struct Host{bool withdrawing=false;void *lock=nullptr,*control=nullptr;proc_t client_proc=nullptr;int client_pid=0;uint64_t client_uniqueid=0;uint32_t client_unit=0;Bridge bridge;};
static Host *gEldenBtHost;static Proc process{79,17};static int refs,kills,finds,bridge_result;static bool missing,wrong_name,replace_during_connect;static unsigned trace_connects;
int proc_selfpid(){return 79;}void proc_name(int,char *s,size_t n){snprintf(s,n,"%s",wrong_name?"other":"bluetoothd");}
proc_t proc_find(int pid){finds++;if(missing||pid!=process.pid)return nullptr;refs++;return &process;}
void proc_rele(proc_t p){assert(p==&process&&refs>0);refs--;}
uint64_t proc_uniqueid(proc_t p){return p->unique;}int proc_pid(proc_t p){return p->pid;}
void IOLockLock(void*){}void IOLockUnlock(void*){}
enum{PbBridgeBusy=-1};
int pb_bridge_connect(Bridge*,uint32_t,int){if(replace_during_connect){gEldenBtHost->client_pid=90;gEldenBtHost->client_uniqueid=23;gEldenBtHost->client_unit=2;}return bridge_result;}
void pb_bridge_disconnect(Bridge*,uint32_t){}void retract(Host*){}void log(const char*){}
void psignal(proc_t p,int sig){assert(p==&process&&sig==SIGKILL);kills++;}errno_t ctl_deregister(kern_ctl_ref){return 0;}
static void reset(Host& h){h=Host{};gEldenBtHost=&h;process={79,17};refs=kills=finds=bridge_result=0;missing=wrong_name=replace_during_connect=false;trace_connects=0;}
'''
    oldmain=r'''
int main(){Host h;reset(h);sockaddr_ctl a{1};void *info=nullptr;assert(connect(nullptr,&a,&info)==0);assert(refs==1);disconnect(nullptr,1,info);assert(refs==0);puts("REPRODUCED old successful connect returns with thread proc refcount1");}
'''
    newmain=r'''
int main(){Host h;sockaddr_ctl a{1};void *info=nullptr;
reset(h);assert(connect(nullptr,&a,&info)==0&&refs==0&&h.client_pid==79&&h.client_uniqueid==17&&h.client_unit==1);disconnect(nullptr,2,info);assert(h.client_pid==79);disconnect(nullptr,1,info);assert(!h.client_pid&&!h.client_uniqueid&&!h.client_unit&&refs==0);
reset(h);missing=true;assert(connect(nullptr,&a,&info)==ESRCH&&refs==0);
reset(h);wrong_name=true;assert(connect(nullptr,&a,&info)==EPERM&&refs==0&&!finds);
reset(h);process.unique=0;assert(connect(nullptr,&a,&info)==ESRCH&&refs==0);
reset(h);h.client_pid=80;assert(connect(nullptr,&a,&info)==EBUSY&&refs==0&&h.client_pid==80);
for(int result:{-1,-2}){reset(h);bridge_result=result;assert(connect(nullptr,&a,&info)==(result==-1?EBUSY:ECONNREFUSED)&&refs==0&&!h.client_pid&&!h.client_uniqueid&&!h.client_unit);}
reset(h);bridge_result=-1;replace_during_connect=true;assert(connect(nullptr,&a,&info)==EBUSY&&refs==0&&h.client_pid==90&&h.client_uniqueid==23&&h.client_unit==2);
reset(h);assert(connect(nullptr,&a,&info)==0);h.bridge.kill_pid=79;finish(&h);assert(kills==1&&refs==0&&!h.client_pid);
reset(h);assert(connect(nullptr,&a,&info)==0);h.bridge.kill_pid=79;process.unique=18;finish(&h);assert(!kills&&refs==0);
reset(h);assert(connect(nullptr,&a,&info)==0);h.bridge.kill_pid=80;finish(&h);assert(!kills&&refs==0&&finds==1);
reset(h);assert(connect(nullptr,&a,&info)==0);h.bridge.kill_pid=79;missing=true;finish(&h);assert(!kills&&refs==0);
puts("PASS callback-local refs, failure cleanup, unit isolation and PID-reuse guard");}
'''
    for name,data,tail in [('original',old_source(),oldmain),('fixed',new_source(),newmain)]:
        f=o/(name+'.cpp');f.write_text(prefix+functions(data)+tail)
        cmd=['c++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(f),'-o',str(o/name)]
        for step,c in [('compile',cmd),('run',[str(o/name)])]:
            r=subprocess.run(c,capture_output=True,timeout=30);(o/(name+'-'+step+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    (o/'result.json').write_text(json.dumps({'passed':True,'original_ref_leak_reproduced':True,'actual_callbacks':True,'sanitizers':['ASan','UBSan'],'pid_reuse_guard':True,'scope':'reference/identity/callback model; requires native and hardware validation'},indent=2)+'\n');print('PASS original leak reproduced, fixed callbacks balanced')
if __name__=='__main__':main()
