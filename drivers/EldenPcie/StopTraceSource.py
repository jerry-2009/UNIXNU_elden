"""Sample existing dispatcher location during the unchanged quiesce wait."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[2]
def generated():
    spec=importlib.util.spec_from_file_location('stop_control',ROOT/'drivers/EldenPcie/ControlNativeSource.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);files=mod.generated()
    def replace(text,old,new):
        if text.count(old)!=1:raise ValueError('Stop sampling anchor differs')
        return text.replace(old,new,1)
    text=files['Native.cpp'].decode()
    text=replace(text,'void elden_usb_log_putc(char);','void elden_usb_log_putc(char);\nextern volatile uint64_t nw_wifi_where[4];')
    text=replace(text,'#include "NativeRuntime.inc"','#include "StopWhere.inc"\n#include "NativeRuntime.inc"');files['Native.cpp']=text.encode()
    text=files['NativeRuntime.inc'].decode()
    old='for(unsigned i=0;i<9000&&__atomic_load_n(&run,__ATOMIC_ACQUIRE)!=2&&now(nullptr)<deadline;i++)IOSleep(1);'
    new='for(unsigned i=0;i<9000&&__atomic_load_n(&run,__ATOMIC_ACQUIRE)!=2&&now(nullptr)<deadline;i++){if(i%2000==0)stop_where();IOSleep(1);}'
    text=replace(text,old,new);files['NativeRuntime.inc']=text.encode();return files
