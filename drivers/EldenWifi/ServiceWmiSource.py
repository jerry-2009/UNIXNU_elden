"""Observe native MSI and logical IRQ state once at the first WMI timeout."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def generated():
    spec=importlib.util.spec_from_file_location('wmi_service_scan',ROOT/'drivers/EldenWifi/ServiceScanSource.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);files=m.generated()
    text=files['MhiRuntime.inc'].decode();marker='static void runtime_log(int level,const char *line){'
    assert text.count(marker)==1
    text=text.replace(marker,'#include "WmiSnapshot.inc"\n'+marker,1)
    marker='    Context *c=runtime_context;if(!line)return;';assert text.count(marker)==1
    text=text.replace(marker,marker+'\n    runtime_wmi_snapshot(c,line);',1)
    files['MhiRuntime.inc']=text.encode();return files
