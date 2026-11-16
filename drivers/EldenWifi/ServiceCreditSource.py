"""Add the first-failure copy of passive HTC/CE/WMI counters."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def generated():
    spec=importlib.util.spec_from_file_location('credit_wmi_source',ROOT/'drivers/EldenWifi/ServiceWmiSource.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);files=m.generated()
    text=(ROOT/'drivers/EldenWifi/WmiSnapshot.inc').read_text()
    marker='static unsigned wmi_snapshot_done;';assert text.count(marker)==1
    text=text.replace(marker,'#include "CreditSnapshot.inc"\n'+marker,1)
    marker='(unsigned long long)c->msi.affinity);';assert text.count(marker)==1
    text=text.replace(marker,marker+'\n    runtime_credit_snapshot();',1)
    files['WmiSnapshot.inc']=text.encode();return files
