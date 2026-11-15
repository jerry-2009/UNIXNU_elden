"""Check root diagnostic routing without changing recovery or power guards."""
import json,tomllib
import bt_runtime_boot
from battery_boot import arguments
from pcie_root_boot import menu
def main():
    q={'profile':'pcie-root-trial','mode':0,'root_trial':True}
    base=tomllib.loads(bt_runtime_boot.menu({'profile':'ufs-idle-trial'}));actual=tomllib.loads(menu(q))
    before=arguments(base['entry'][0]['args']);after=arguments(actual['entry'][0]['args'])
    removed={'ecp','elden-wcn-power','elden-frame-preview','elden-userfault-log'}
    assert {k:v for k,v in before.items() if k not in removed}=={k:v for k,v in after.items() if k not in {'elden-pcie-root','elden-wlan-power','elden-pcie-full-on'}}
    assert all(after[k]=='1' for k in ['elden-pcie-root','elden-wlan-power','elden-pcie-full-on'])
    assert all(after[k]==v for k,v in {'vdog':'3','smp-hold':'600','elden-thermal':'3','epd':'2','elden-return-fastboot':'1','elden-panic-delay':'180','elden-key-events':'1'}.items())
    assert actual['boot']==base['boot'] and actual['entry'][1:]==base['entry'][1:]
    assert len(actual['entry'][0]['args'].replace('@SESSION@','0'*16).encode())==1011
    for bad in [{},dict(q,mode=4),dict(q,root_trial=False),dict(q,profile='ufs-idle-trial')]:
        try:menu(bad)
        except ValueError:pass
        else:raise AssertionError('Invalid intent accepted')
    assert bt_runtime_boot.menu(q)==menu(q)
    print(json.dumps({'passed':True,'bytes':1011,'guards_preserved':True,'fallbacks_preserved':True,'invalid_intents_rejected':4}))
if __name__=='__main__':main()
