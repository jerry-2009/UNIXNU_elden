/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * The diagnostic scan belongs to the current control session. A successful
 * socket enqueue proves delivery only, not userspace parsing or connectivity.
 * All state below is protected by the existing native control lock.
 */
static uint64_t wifi_info_delivered_session;
static bool wifi_successful_info_reply(const void *data,size_t bytes,uint64_t session){
    if(!data||bytes<40||bytes>65536||!session)return false;
    const uint8_t *p=static_cast<const uint8_t *>(data);
    uint64_t encoded=wifi_trace_u32(p+24)|(uint64_t(wifi_trace_u32(p+28))<<32);
    return wifi_trace_u32(p)==0x3143574e&&wifi_trace_u16(p+4)==1&&wifi_trace_u16(p+6)==2&&
        wifi_trace_u16(p+8)==1&&wifi_trace_u16(p+10)==0&&wifi_trace_u32(p+16)==bytes&&
        wifi_trace_u32(p+20)==0&&encoded==session;
}
static void wifi_note_info_delivery(int error,uint64_t session,const void *data,size_t bytes){
    if(error||!wifi_successful_info_reply(data,bytes,session))return;
    IOLockLock(wifi_control_lock);
    if(wifi_control_open()&&wifi_control_client&&wifi_control_client->session==session)
        wifi_info_delivered_session=session;
    IOLockUnlock(wifi_control_lock);
}
static uint64_t wifi_service_info_session(){
    IOLockLock(wifi_control_lock);
    uint64_t result=wifi_control_open()&&wifi_control_client&&
        wifi_control_client->session==wifi_info_delivered_session?wifi_info_delivered_session:0;
    IOLockUnlock(wifi_control_lock);return result;
}
