"""Observe the owned helper without changing its reply decisions or XPC calls."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[3]
ORIGINAL='608672ec4937c6f8ff19369bcd132c0fb26d948e56a7170c7aa929410b8476bf'
def source():
    data=(ROOT/'drivers/EldenBluetooth/userland/BlueTool.c').read_bytes()
    if hashlib.sha256(data).hexdigest()!=ORIGINAL:raise ValueError('Owned helper source changed')
    text=data.decode();edits=[]
    def change(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('Ambiguous helper trace boundary')
        text=text.replace(old,new);edits.append((old,new))
    change('static os_log_t logger;', '#include "TraceMarker.h"\nstatic os_log_t logger;')
    change('    EldenBtBootStatus status={0};size_t bytes=sizeof(status);','''    unsigned trace_script=!script?0:!strcmp(script,"boot")?1:!strcmp(script,"init")?2:!strcmp(script,"deepsleep")?3:0;
    elden_bt_trace(1,trace_script,0,0,0);
    EldenBtBootStatus status={0};size_t bytes=sizeof(status);''')
    change('    EldenBtBootReply result=elden_bt_boot_reply', '    elden_bt_trace(2,trace_script,error,status.state,0);\n    EldenBtBootReply result=elden_bt_boot_reply')
    change('    xpc_dictionary_set_int64(reply,"result",result.error?1:0);','    elden_bt_trace(3,trace_script,result.error,status.state,result.identity);\n    xpc_dictionary_set_int64(reply,"result",result.error?1:0);')
    change('    os_log(logger,','    elden_bt_trace(4,trace_script,result.error,status.state,result.identity);\n    os_log(logger,')
    change('    xpc_connection_t peer=xpc_dictionary_get_remote_connection(message);','''    elden_bt_trace(5,trace_script,result.error,status.state,result.identity);
    xpc_connection_t peer=xpc_dictionary_get_remote_connection(message);
    elden_bt_trace(6,trace_script,peer?0:ENOTCONN,status.state,result.identity);''')
    change('    xpc_release(reply);','''    elden_bt_trace(7,trace_script,peer?0:ENOTCONN,status.state,result.identity);
    xpc_release(reply);
    elden_bt_trace(8,trace_script,result.error,status.state,result.identity);''')
    original=text
    for before,after in reversed(edits):
        if original.count(after)!=1:raise ValueError('Trace edits overlap')
        original=original.replace(after,before)
    if original.encode()!=data:raise ValueError('Undeclared helper behavior change')
    return text.encode()
