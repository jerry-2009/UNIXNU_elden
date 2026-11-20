/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Native privileged socket follows the established Sheng/Elden lock ordering.
 * Only message metadata is logged. Keys/profile/EAPOL never enter the log.
 */
namespace {
struct StationClient {uint64_t session;uint32_t unit;};
static kern_ctl_ref station_ref;
static IOLock *station_lock;
static StationClient *station_client;
static unsigned station_accepting,station_stopping;
static uint64_t station_next_session;
static bool station_open(){return station_accepting&&!station_stopping;}
static void station_take(void *){IOLockLock(station_lock);}
static void station_give(void *){IOLockUnlock(station_lock);}
static bool station_session(void *p,uint32_t unit,uint64_t *out){
    if(!station_lock||!p||!out)return false;IOLockLock(station_lock);
    const bool accepted=station_open()&&station_client==p&&station_client->unit==unit;
    if(accepted)*out=station_client->session;
    IOLockUnlock(station_lock);return accepted;
}
static int station_send(void *,uint64_t session,const void *bytes,uint32_t length){
    if(!station_lock||!bytes||length>PIANO_WIFI_8021X_MSG_MAX)return -22;
    IOLockLock(station_lock);const uint32_t unit=station_open()&&station_client&&station_client->session==session?station_client->unit:0;IOLockUnlock(station_lock);
    if(!unit)return -108;
    const int rc=ctl_enqueuedata(station_ref,unit,const_cast<void *>(bytes),length,CTL_DATA_EOR);
    return rc?(int)(0u-(unsigned)rc):0;
}
static errno_t station_connect(kern_ctl_ref,sockaddr_ctl *address,void **context){
    if(!address||!context||!station_open()||elden_wifi_net_admit())return ENXIO;
    auto *client=(StationClient *)IOMalloc(sizeof(StationClient));if(!client)return ENOMEM;
    IOLockLock(station_lock);
    if(!station_open()||station_client){IOLockUnlock(station_lock);IOFree(client,sizeof(*client));return EBUSY;}
    uint64_t session=++station_next_session;if(!session)session=++station_next_session;
    client->session=session;client->unit=address->sc_unit;station_client=client;
    IOLockUnlock(station_lock);
    const int rc=elden_wifi_station_port_open(session);
    if(rc){IOLockLock(station_lock);if(station_client==client)station_client=nullptr;IOLockUnlock(station_lock);IOFree(client,sizeof(*client));return (int)(0u-(unsigned)rc);}
    *context=client;return 0;
}
static errno_t station_disconnect(kern_ctl_ref,uint32_t unit,void *context){
    if(!context||!station_lock)return 0;auto *client=(StationClient *)context;uint64_t session=0;
    IOLockLock(station_lock);if(station_client==client&&client->unit==unit){session=client->session;station_client=nullptr;}IOLockUnlock(station_lock);
    if(session)elden_wifi_station_port_close(session);
    IOFree(client,sizeof(*client));return 0;
}
static errno_t station_receive(kern_ctl_ref,uint32_t unit,void *context,mbuf_t packet,int){
    if(!packet)return EINVAL;uint64_t session=0;int result=ENXIO;
    if(station_session(context,unit,&session)&&!elden_wifi_net_admit()){
        const size_t length=mbuf_pkthdr_len(packet);
        if(length>PIANO_WIFI_8021X_MSG_MAX)result=EMSGSIZE;
        else{
            auto *bytes=(uint8_t *)IOMalloc(length?length:1);
            if(!bytes)result=ENOMEM;
            else{
                result=mbuf_copydata(packet,0,length,bytes);
                if(!result){int rc=elden_wifi_station_port_receive(session,bytes,(uint32_t)length);result=rc<0?(int)(0u-(unsigned)rc):rc;}
                for(size_t i=0;i<length;i++)((volatile uint8_t *)bytes)[i]=0;
                IOFree(bytes,length?length:1);
            }
        }
    }
    mbuf_freem(packet);if(runtime_context)transport_wake(runtime_context);return result;
}
}
extern "C" int elden_wifi_station_native_start(void){
    if(station_ref)return station_open()?0:-108;
    station_lock=IOLockAlloc();if(!station_lock)return -12;
    kern_ctl_reg registration={};
    snprintf(registration.ctl_name,sizeof(registration.ctl_name),"%s",PIANO_WIFI_8021X_CONTROL);
    registration.ctl_flags=CTL_FLAG_PRIVILEGED;registration.ctl_sendsize=64*1024;registration.ctl_recvsize=256*1024;
    registration.ctl_connect=station_connect;registration.ctl_disconnect=station_disconnect;registration.ctl_send=station_receive;
    int rc=ctl_register(&registration,&station_ref);if(rc){IOLockFree(station_lock);station_lock=nullptr;return (int)(0u-(unsigned)rc);}
    EldenStationPort io={station_lock,station_take,station_give,station_send};
    rc=elden_wifi_station_port_install(&io);if(rc)return rc;
    station_accepting=1;
    log("\nELDEN_STATION native-control=0 privileged=1\n");return 0;
}
extern "C" void elden_wifi_station_native_stop(void){
    station_stopping=1;station_accepting=0;
    /* Retain locks/reference/client until the original reset; socket callbacks
     * can still close and wipe their own outstanding data. */
}
