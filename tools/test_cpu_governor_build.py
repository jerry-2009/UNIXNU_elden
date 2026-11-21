"""Check CPU-governor menu, exact current recovery bindings and stop-link rejection."""
from pathlib import Path
import argparse,copy,hashlib,json,struct,tomllib
from cpu_governor_build import recovery_overlay,audit_stop_link
from bt_runtime_boot import menu
from battery_boot import arguments
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);checks=0
    before=tomllib.loads(menu({'profile':'cpu-power-observation'}));after=tomllib.loads(menu({'profile':'cpu-governor'}))
    old,new=arguments(before['entry'][0]['args']),arguments(after['entry'][0]['args']);assert old['ecp']=='2' and new==old|{'ecp':'3'}
    assert len(after['entry'][0]['args'].replace('@SESSION@','0'*16).encode())==1023
    after['entry'][0]['args']=before['entry'][0]['args'];assert after==before;checks+=1
    plan=json.loads((ROOT/'profiles/current-build/plan.json').read_text());job=next(j for j in plan['jobs'] if j['name']=='ShengUfs')
    bindings=[n for n in plan['mappings'][job['mapping']] if n.endswith('/EldenSdamRecovery.inc')];assert len(bindings)==2
    current=ROOT/'profiles/v97-wcn/EldenSdamRecovery.inc';legacy=ROOT/'profiles/v91/sources/usb/EldenSdamRecovery.inc'
    overlay={'fallthrough':False,'roots':[{'type':'file','name':n,'external-contents':str(current)} for n in bindings]+[{'type':'file','name':'/other/source','external-contents':str(ROOT/'drivers/EldenCpuPower/CpuLoad.h')} ]}
    selected=copy.deepcopy(overlay);b,inputs=recovery_overlay(selected,out/'new.inc');assert b==bindings and selected['roots'][-1]==overlay['roots'][-1] and len(inputs)==2;checks+=1
    for kind in range(3):
        bad=copy.deepcopy(overlay)
        if kind==0:bad['fallthrough']=True
        if kind==1:bad['roots'][0]['external-contents']=str(legacy)
        if kind==2:bad['roots']=bad['roots'][-1:]
        try:recovery_overlay(bad,out/'new.inc')
        except ValueError:checks+=1
        else:raise AssertionError('Invalid recovery overlay accepted')
    # Small native-code fixture: one BL to a defined function, with both words
    # in a file-backed executable section. This tests the verifier, not a kernel.
    data=bytearray(0x400);struct.pack_into('<8I',data,0,0xfeedfacf,0x100000c,0,2,2,176,0,0)
    at=32;struct.pack_into('<II16sQQQQIIII',data,at,0x19,152,b'__TEXT',0x1000,0x100,0x200,0x100,5,5,1,0)
    struct.pack_into('<16s16sQQ8I',data,at+72,b'__text',b'__TEXT',0x1000,0x100,0x200,2,0,0,0x80000400,0,0,0)
    struct.pack_into('<6I',data,184,2,24,0x300,1,0x320,64)
    struct.pack_into('<IBBHQ',data,0x300,1,15,1,0,0x1020)
    name=b'\0_elden_cpu_governor_request_stop\0';data[0x320:0x320+len(name)]=name
    struct.pack_into('<I',data,0x200,0x94000008);struct.pack_into('<I',data,0x220,0xd65f03c0)
    native=out/'native.fixture';kernel=out/'kernel.fixture';native.write_bytes(data);kernel.write_bytes(data)
    assert audit_stop_link(native,kernel)=={'provider':'0x1020','calls':['0x1000'],'prelink_preserved':True};checks+=1
    for kind in range(4):
        n=bytearray(data);k=bytearray(data)
        if kind==0:n[0x321]=ord('X')
        if kind==1:struct.pack_into('<I',n,0x200,0xd503201f)
        if kind==2:struct.pack_into('<I',k,0x200,0xd503201f)
        if kind==3:struct.pack_into('<I',k,0x220,0xd503201f)
        native.write_bytes(n);kernel.write_bytes(k)
        try:audit_stop_link(native,kernel)
        except ValueError:checks+=1
        else:raise AssertionError('Invalid stop linkage accepted')
    result={'passed':True,'checks':checks,'real_current_recovery_aliases':bindings,'legacy_recovery_rejected':True,'menu_bytes':1023,'only_menu_semantic_delta':'ecp=2 -> ecp=3','native_compiled':False,'hardware':False,'limits':'Source mapping and synthetic Mach-O verifier tests only.'}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
