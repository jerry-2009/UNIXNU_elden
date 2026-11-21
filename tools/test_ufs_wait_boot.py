"""Check UFS trial menu keeps the qualified early guard's exact arguments."""
import json,tomllib
from bt_runtime_boot import menu
from battery_boot import arguments
def main():
    old=tomllib.loads(menu({'profile':'early-storage-guard'}))
    new=tomllib.loads(menu({'profile':'ufs-wait-trial'}))
    assert new['entry'][0]['title']=='UFS completion read trial - TEST'
    assert arguments(old['entry'][0]['args'])==arguments(new['entry'][0]['args'])
    assert arguments(new['entry'][0]['args'])['vdog']=='3'
    assert len(new['entry'][0]['args'].replace('@SESSION@','0'*16).encode())==1023
    new['entry'][0]['title']=old['entry'][0]['title'];assert new==old
    print(json.dumps({'passed':True,'arguments_identical':True,'bytes':1023,'watchdog_mode':3,'fallbacks_preserved':True}))
if __name__=='__main__':main()
