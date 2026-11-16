"""Send the bounded diagnostic scan after this session's successful INFO reply."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def generated():
    spec=importlib.util.spec_from_file_location('scan_control_trace',ROOT/'drivers/EldenWifi/ServiceControlTraceSource.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);files=m.generated()
    def replace(text,old,new):
        if text.count(old)!=1:raise ValueError('Scan source anchor differs: '+old[:90])
        return text.replace(old,new,1)
    text=files['ControlNative.inc'].decode()
    marker='static errno_t wifi_control_error(int status){'
    text=replace(text,marker,'#include "ControlScan.inc"\n'+marker)
    text=replace(text,'    if(accepted)wifi_control_client=client;',
        '    if(accepted){wifi_control_client=client;wifi_info_delivered_session=0;}')
    text=replace(text,'    if(owned){session=wifi_control_client->session;wifi_control_client=nullptr;}',
        '    if(owned){session=wifi_control_client->session;wifi_control_client=nullptr;wifi_info_delivered_session=0;}')
    marker='    wifi_trace_meta("send-return",unit,rc,bytes,length);'
    text=replace(text,marker,marker+'\n    wifi_note_info_delivery(rc,session,bytes,length);')
    files['ControlNative.inc']=text.encode()
    text='static uint64_t wifi_service_info_session();\n'+files['MhiRuntime.inc'].decode()
    marker='uint64_t report_at=0,slice=now(nullptr),scan_at=0;bool scan=false;unsigned scan_attempts=0;'
    text=replace(text,marker,marker+'uint64_t scan_session=0;')
    marker='        if(!scan&&scan_attempts<3&&t>=scan_at&&nw_wifi_stats.stage>=4){'
    text=replace(text,marker,'''        uint64_t current_session=wifi_service_info_session();
        if(current_session&&current_session!=scan_session){scan_session=current_session;scan=false;scan_at=t;}
        if(current_session&&!scan&&scan_attempts<3&&t>=scan_at&&nw_wifi_stats.stage>=4){''')
    text=replace(text,'log("\\nELDEN_WIFI_RUNTIME scan=%d\\n",r);','log("\\nELDEN_WIFI_RUNTIME scan=%d info-delivered-current-session=1\\n",r);')
    files['MhiRuntime.inc']=text.encode();return files
