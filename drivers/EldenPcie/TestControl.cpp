/* Host model of kernel socket/mbuf services; production ControlNative.inc and
 * the pinned real nw_control/nw_control_wire/lx_rt implement both endpoints. */
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include "ControlApi.h"
using errno_t=int;using kern_ctl_ref=void *;using IOLock=std::mutex;
struct sockaddr_ctl {uint32_t sc_unit;};
struct Packet {size_t length;unsigned char bytes[128];};using mbuf_t=Packet *;
struct kern_ctl_reg {
    char ctl_name[96];unsigned ctl_flags,ctl_sendsize,ctl_recvsize;
    errno_t(*ctl_connect)(kern_ctl_ref,sockaddr_ctl *,void **);
    errno_t(*ctl_disconnect)(kern_ctl_ref,uint32_t,void *);
    errno_t(*ctl_send)(kern_ctl_ref,uint32_t,void *,mbuf_t,int);
    void(*ctl_rcvd)(kern_ctl_ref,uint32_t,void *,int);
    errno_t(*ctl_getopt)(kern_ctl_ref,uint32_t,void *,int,void *,size_t *);
};
enum {CTL_FLAG_PRIVILEGED=1,CTL_FLAG_REG_EXTENDED=2,CTL_DATA_EOR=4};
static kern_ctl_reg registered;static bool no_lock,no_client,stop_in_register,copy_error;
static int register_error,deregister_error,enqueue_error,locks,allocations,packets,queues,wakes;
static IOLock *test_lock;
static IOLock *IOLockAlloc(){if(no_lock)return nullptr;locks++;return test_lock=new IOLock;}
static void IOLockFree(IOLock *p){locks--;delete p;test_lock=nullptr;}
static void IOLockLock(IOLock *p){assert(p);p->lock();}
static void IOLockUnlock(IOLock *p){p->unlock();}
static void *IOMalloc(size_t n){if(no_client)return nullptr;allocations++;return malloc(n);}
static void IOFree(void *p,size_t){assert(p&&allocations);allocations--;free(p);}
static void control_stop_begin();
static errno_t ctl_register(kern_ctl_reg *r,kern_ctl_ref *out){registered=*r;if(register_error)return register_error;*out=&registered;if(stop_in_register)control_stop_begin();return 0;}
static errno_t ctl_deregister(kern_ctl_ref r){assert(r==&registered);return deregister_error;}
static errno_t ctl_enqueuedata(kern_ctl_ref r,uint32_t u,void *,size_t,int flags){
    assert(r==&registered&&u==7&&flags==CTL_DATA_EOR);
    assert(test_lock->try_lock());test_lock->unlock();queues++;return enqueue_error;
}
static size_t mbuf_pkthdr_len(mbuf_t p){return p->length;}
static errno_t mbuf_copydata(mbuf_t p,size_t off,size_t n,void *out){if(copy_error)return EIO;assert(!off&&n<=sizeof(p->bytes));memcpy(out,p->bytes,n);return 0;}
static void mbuf_freem(mbuf_t p){assert(p&&packets);packets--;delete p;}
static int context;static void *runtime_context=&context;
static void transport_wake(void *p){assert(p==runtime_context);wakes++;}
#include "ControlNative.inc"
extern "C" {void fixture_init();int fixture_bind();void fixture_pump();void fixture_shutdown();size_t fixture_packet(void *,size_t,uint64_t);unsigned fixture_requests();int fixture_occupy();}
static Packet *packet(uint64_t session){auto *p=new Packet{};packets++;p->length=fixture_packet(p->bytes,sizeof(p->bytes),session);return p;}
int main(int argc,char **argv){
    assert(argc==2);int scenario=atoi(argv[1]);fixture_init();
    assert(fixture_bind()==NW_CONTROL_NOT_READY); // reproduces v165 before any transport
    if(scenario==1){no_lock=true;assert(control_start()==ENOMEM);return 0;}
    if(scenario==2){register_error=EEXIST;assert(control_start()==EEXIST);assert(!locks&&!wifi_control_ref);return 0;}
    if(scenario==3||scenario==4){assert(!fixture_occupy());deregister_error=scenario==4?EBUSY:0;
        assert(control_start()==EWOULDBLOCK);assert(!wifi_control_open());
        assert(locks==(scenario==4));assert(bool(wifi_control_ref)==(scenario==4));fixture_shutdown();return 0;}
    if(scenario==5){control_stop_begin();assert(control_start()==ESHUTDOWN);assert(!locks);return 0;}
    if(scenario==6){stop_in_register=true;assert(control_start()==ESHUTDOWN);assert(!wifi_control_open());return 0;}
    assert(!control_start());assert(!strcmp(registered.ctl_name,NW_CONTROL_NAME));
    assert(registered.ctl_flags==(CTL_FLAG_PRIVILEGED|CTL_FLAG_REG_EXTENDED));
    assert(registered.ctl_sendsize==256*1024&&registered.ctl_recvsize==512*1024);
    assert(control_start()==EALREADY);sockaddr_ctl address{7};void *client=nullptr;
    assert(registered.ctl_connect(wifi_control_ref,&address,&client)==ENXIO&&!client);
    assert(!fixture_bind());assert(fixture_bind()==NW_CONTROL_BUSY);
    no_client=true;assert(registered.ctl_connect(wifi_control_ref,&address,&client)==ENOMEM);no_client=false;
    assert(!registered.ctl_connect(wifi_control_ref,&address,&client)&&client);
    void *other=nullptr;assert(registered.ctl_connect(wifi_control_ref,&address,&other)==EWOULDBLOCK&&!other);
    uint64_t session=0;size_t length=1;
    assert(registered.ctl_getopt(wifi_control_ref,7,client,1,&session,&length)==EMSGSIZE&&length==8);
    assert(!registered.ctl_getopt(wifi_control_ref,7,client,1,&session,&length)&&session);
    assert(registered.ctl_getopt(wifi_control_ref,8,client,1,&session,&length)==ENXIO);
    assert(registered.ctl_getopt(wifi_control_ref,7,client,9,&session,&length)==ENOPROTOOPT);
    assert(registered.ctl_send(wifi_control_ref,7,client,packet(session+1),0)==ESTALE);
    copy_error=true;assert(registered.ctl_send(wifi_control_ref,7,client,packet(session),0)==EINVAL);copy_error=false;
    auto *oversize=packet(session);oversize->length=65537;assert(registered.ctl_send(wifi_control_ref,7,client,oversize,0)==EMSGSIZE);
    assert(registered.ctl_send(wifi_control_ref,8,client,packet(session),0)==ENXIO);
    enqueue_error=ENOBUFS;assert(!registered.ctl_send(wifi_control_ref,7,client,packet(session),0));fixture_pump();
    assert(fixture_requests()==1&&queues==1);enqueue_error=0;registered.ctl_rcvd(wifi_control_ref,7,client,0);fixture_pump();assert(queues==2);
    unsigned char byte=0;assert(wifi_control_send(nullptr,session+1,&byte,1)==NW_CONTROL_SEND_CLOSED);
    enqueue_error=EIO;assert(wifi_control_send(nullptr,session,&byte,1)==NW_CONTROL_SEND_CLOSED);enqueue_error=0;
    assert(!registered.ctl_disconnect(wifi_control_ref,7,client));client=nullptr;fixture_pump();assert(!allocations);
    assert(!registered.ctl_disconnect(wifi_control_ref,7,nullptr));
    assert(!registered.ctl_connect(wifi_control_ref,&address,&client));uint64_t next=0;
    assert(!registered.ctl_getopt(wifi_control_ref,7,client,1,&next,&length)&&next!=session);
    control_stop_begin();assert(!wifi_control_open());assert(registered.ctl_send(wifi_control_ref,7,client,packet(next),0)==ENXIO);
    assert(wifi_control_send(nullptr,next,&byte,1)==NW_CONTROL_SEND_CLOSED);
    assert(registered.ctl_connect(wifi_control_ref,&address,&other)==ENXIO);
    fixture_shutdown();assert(!registered.ctl_disconnect(wifi_control_ref,7,client));
    assert(!allocations&&!packets&&wakes);puts("PASS native socket callbacks + real control bind/queues/session/stop; XNU services modeled");
}
