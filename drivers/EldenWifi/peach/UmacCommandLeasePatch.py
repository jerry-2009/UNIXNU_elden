"""Keep exact OEM MHI/UMAC access ownership around each original WMI send."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[1]
EXPECTED={'pci.c':'d50605c5a03a0c5b2b8b949a2ebc02c3329cd7e683746f47d8765eeb38acb84c',
          'wmi.c':'14794e784a472315a57640d4b21c1ae2b53019f3d08ebb4199aa42deb4f2611a'}


def patch(name,data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED.get(name):raise ValueError('Exact command-lease parent changed: '+name)
    original=text=data.decode()
    if name=='pci.c':
        old='int ath12k_pci_hif_suspend(struct ath12k_base *ab)'
        new=(ROOT/'UmacCommandLease.inc').read_text(encoding='utf-8')+'\n'+old
    else:
        start=text.index('int ath12k_wmi_cmd_send(');end=text.index('\n}\n',start)+3;old=text[start:end]
        new=old.replace('\tint ret = -EOPNOTSUPP;', '''\tint ret = -EOPNOTSUPP;
\tbool umac_taken=false;
\textern int elden_wifi_umac_command_begin(struct ath12k_base *,u32,bool *);
\textern void elden_wifi_umac_command_end(struct ath12k_base *,bool);''',1)
        new=new.replace('\tmight_sleep();','''\tmight_sleep();
\tret=elden_wifi_umac_command_begin(wmi_ab->ab,cmd_id,&umac_taken);
\tif(ret)return ret;''',1)
        new=new.replace('\treturn ret;','\telden_wifi_umac_command_end(wmi_ab->ab,umac_taken);\n\treturn ret;',1)
    if text.count(old)!=1:raise ValueError('Command-lease boundary changed')
    text=text.replace(old,new,1)
    if text.replace(new,old,1)!=original:raise ValueError('Unexpected command-lease operations')
    return text.encode()
