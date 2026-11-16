"""Trace actual control callback boundaries without altering return semantics."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def generated():
    spec=importlib.util.spec_from_file_location('plain_wifi_service',ROOT/'drivers/EldenWifi/ServiceNativeSource.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);files=m.generated();replace=m.replace
    text=files['ControlNative.inc'].decode()
    text='#include "ControlTrace.inc"\n'+text
    old='static int wifi_control_read_mbuf(void *source,void *destination,size_t bytes){return mbuf_copydata((mbuf_t)source,0,bytes,destination);}'
    new='static int wifi_control_read_mbuf(void *source,void *destination,size_t bytes){int rc=mbuf_copydata((mbuf_t)source,0,bytes,destination);wifi_trace_meta("read",0,rc,rc?nullptr:destination,bytes);return rc;}'
    text=replace(text,old,new)
    text=replace(text,'    mbuf_freem(packet);return result;','    wifi_trace_meta("receive",unit,result,nullptr,0);mbuf_freem(packet);return result;')
    text=replace(text,'static errno_t wifi_control_getopt(kern_ctl_ref,','static errno_t wifi_control_getopt_impl(kern_ctl_ref,')
    marker='static int wifi_control_send(void *,uint64_t session,const void *bytes,size_t length){'
    wrapper='''static errno_t wifi_control_getopt(kern_ctl_ref ref,uint32_t unit,void *info,int option,void *bytes,size_t *length){
    errno_t rc=wifi_control_getopt_impl(ref,unit,info,option,bytes,length);
    wifi_trace_meta("getopt",unit,rc,nullptr,length?*length:0);return rc;
}
'''
    text=replace(text,marker,wrapper+marker)
    line='    errno_t rc=ctl_enqueuedata(wifi_control_ref,unit,const_cast<void *>(bytes),length,CTL_DATA_EOR);'
    text=replace(text,line,'    wifi_trace_meta("send-enter",unit,0,bytes,length);\n'+line+'\n    wifi_trace_meta("send-return",unit,rc,bytes,length);')
    line='    nw_wifi_control_detach(session);IOFree(info,sizeof(WifiControlClient));log("\\nELDEN_WIFI_SERVICE control-disconnected=1\\n");return 0;'
    text=replace(text,line,'    wifi_trace_snapshot(unit);\n'+line)
    files['ControlNative.inc']=text.encode();return files
