/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Native control transport adapted from UniXNU-sheng WifiProbe.cpp.
 * Copyright (c) 2026, UniXNU contributors. See EldenWifi/LICENSE.sheng.
 * Wire payloads can contain keys/EAPOL and are never logged here.
 */
struct WifiControlClient {uint64_t session;uint32_t unit;};
static kern_ctl_ref wifi_control_ref;
static IOLock *wifi_control_lock;
static WifiControlClient *wifi_control_client;
static unsigned wifi_control_accepting,wifi_control_stopping;
static bool wifi_control_open(){return __atomic_load_n(&wifi_control_accepting,__ATOMIC_ACQUIRE)&&!__atomic_load_n(&wifi_control_stopping,__ATOMIC_ACQUIRE);}
static errno_t wifi_control_error(int status){
    switch(status){
        case NW_CONTROL_OK:return 0;case NW_CONTROL_INVALID:return EINVAL;
        case NW_CONTROL_BUSY:return EWOULDBLOCK;case NW_CONTROL_NOT_READY:return ENXIO;
        case NW_CONTROL_AUTH_FAILED:return EACCES;case NW_CONTROL_TIMED_OUT:return ETIMEDOUT;
        case NW_CONTROL_UNSUPPORTED:return EOPNOTSUPP;case NW_CONTROL_NO_MEMORY:return ENOBUFS;
        case NW_CONTROL_NOT_FOUND:return ENOENT;case NW_CONTROL_STALE:return ESTALE;default:return EIO;
    }
}
static bool wifi_control_session(void *info,uint32_t unit,uint64_t *session){
    if(!info||!wifi_control_open())return false;
    IOLockLock(wifi_control_lock);
    bool valid=wifi_control_client==info&&wifi_control_client->unit==unit;
    if(valid)*session=wifi_control_client->session;
    IOLockUnlock(wifi_control_lock);return valid;
}
static errno_t wifi_control_connect(kern_ctl_ref,sockaddr_ctl *address,void **info){
    if(!address||!info)return EINVAL;*info=nullptr;
    if(!wifi_control_open())return ENXIO;
    auto *client=static_cast<WifiControlClient *>(IOMalloc(sizeof(WifiControlClient)));if(!client)return ENOMEM;
    int rc=nw_wifi_control_attach(&client->session);if(rc){IOFree(client,sizeof(*client));return wifi_control_error(rc);}
    client->unit=address->sc_unit;IOLockLock(wifi_control_lock);
    bool accepted=wifi_control_open()&&!wifi_control_client;
    if(accepted)wifi_control_client=client;
    IOLockUnlock(wifi_control_lock);
    if(!accepted){nw_wifi_control_detach(client->session);IOFree(client,sizeof(*client));return EBUSY;}
    *info=client;return 0;
}
static errno_t wifi_control_disconnect(kern_ctl_ref,uint32_t unit,void *info){
    if(!info)return 0;
    uint64_t session=0;IOLockLock(wifi_control_lock);
    bool owned=wifi_control_client==info&&wifi_control_client->unit==unit;
    if(owned){session=wifi_control_client->session;wifi_control_client=nullptr;}
    IOLockUnlock(wifi_control_lock);
    if(!owned)return EINVAL;
    nw_wifi_control_detach(session);IOFree(info,sizeof(WifiControlClient));return 0;
}
static int wifi_control_read_mbuf(void *source,void *destination,size_t bytes){return mbuf_copydata((mbuf_t)source,0,bytes,destination);}
static errno_t wifi_control_receive(kern_ctl_ref,uint32_t unit,void *info,mbuf_t packet,int){
    if(!packet)return EINVAL;uint64_t session=0;errno_t result=ENXIO;
    if(wifi_control_session(info,unit,&session)){
        size_t bytes=mbuf_pkthdr_len(packet);
        result=bytes>NW_CONTROL_MAX_MESSAGE?EMSGSIZE:wifi_control_error(nw_wifi_control_receive(session,bytes,wifi_control_read_mbuf,packet));
    }
    mbuf_freem(packet);return result;
}
static void wifi_control_received(kern_ctl_ref,uint32_t unit,void *info,int){uint64_t session=0;if(wifi_control_session(info,unit,&session))nw_wifi_control_writable(session);}
static errno_t wifi_control_getopt(kern_ctl_ref,uint32_t unit,void *info,int option,void *bytes,size_t *length){
    if(option!=NW_CONTROL_GET_SESSION)return ENOPROTOOPT;if(!length)return EINVAL;
    if(!bytes||*length<sizeof(uint64_t)){*length=sizeof(uint64_t);return EMSGSIZE;}
    uint64_t session=0;if(!wifi_control_session(info,unit,&session))return ENXIO;
    memcpy(bytes,&session,sizeof(session));*length=sizeof(session);return 0;
}
static int wifi_control_send(void *,uint64_t session,const void *bytes,size_t length){
    if(!wifi_control_open()||!bytes||length>NW_CONTROL_MAX_MESSAGE)return NW_CONTROL_SEND_CLOSED;
    IOLockLock(wifi_control_lock);
    bool active=wifi_control_client&&wifi_control_client->session==session;
    uint32_t unit=active?wifi_control_client->unit:0;
    IOLockUnlock(wifi_control_lock);
    if(!active)return NW_CONTROL_SEND_CLOSED;
    /* Keep the upstream lock ordering: never hold our lock while kctl locks
     * its socket. The unchanged wire protocol validates the encoded session. */
    errno_t rc=ctl_enqueuedata(wifi_control_ref,unit,const_cast<void *>(bytes),length,CTL_DATA_EOR);
    if(!rc)return NW_CONTROL_SEND_OK;
    return rc==ENOBUFS||rc==EWOULDBLOCK?NW_CONTROL_SEND_AGAIN:NW_CONTROL_SEND_CLOSED;
}
static void wifi_control_wake(void *){if(runtime_context)transport_wake(runtime_context);}
static void control_stop_begin(){__atomic_store_n(&wifi_control_stopping,1u,__ATOMIC_RELEASE);__atomic_store_n(&wifi_control_accepting,0u,__ATOMIC_RELEASE);}
static int control_start(){
    if(__atomic_load_n(&wifi_control_stopping,__ATOMIC_ACQUIRE))return ESHUTDOWN;
    if(wifi_control_ref)return EALREADY;
    wifi_control_lock=IOLockAlloc();if(!wifi_control_lock)return ENOMEM;
    kern_ctl_reg registration={};
    snprintf(registration.ctl_name,sizeof(registration.ctl_name),"%s",NW_CONTROL_NAME);
    registration.ctl_flags=CTL_FLAG_PRIVILEGED|CTL_FLAG_REG_EXTENDED;
    registration.ctl_sendsize=256*1024;registration.ctl_recvsize=512*1024;
    registration.ctl_connect=wifi_control_connect;registration.ctl_disconnect=wifi_control_disconnect;
    registration.ctl_send=wifi_control_receive;registration.ctl_rcvd=wifi_control_received;registration.ctl_getopt=wifi_control_getopt;
    errno_t rc=ctl_register(&registration,&wifi_control_ref);
    if(rc){IOLockFree(wifi_control_lock);wifi_control_lock=nullptr;return rc;}
    nw_control_transport transport={nullptr,wifi_control_send,wifi_control_wake};
    int status=nw_wifi_control_transport_set(&transport);
    if(status){
        /* No client can have connected: accepting remains false. If XNU
         * refuses deregistration retain the reference and lock until reset. */
        if(!ctl_deregister(wifi_control_ref)){wifi_control_ref=nullptr;IOLockFree(wifi_control_lock);wifi_control_lock=nullptr;}
        return wifi_control_error(status);
    }
    __atomic_store_n(&wifi_control_accepting,1u,__ATOMIC_RELEASE);
    return wifi_control_open()?0:ESHUTDOWN;
}
