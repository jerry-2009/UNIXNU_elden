"""Run the established owner-rule failure fixtures on the actual Wi-Fi predicate."""
import argparse,ast,hashlib,importlib.util,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tree=ast.parse((ROOT/'tools/test_bluetool_launch.py').read_text());strings={}
    for n in ast.walk(tree):
        if isinstance(n,ast.Assign) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str):
            for target in n.targets:
                if isinstance(target,ast.Name) and target.id in ['prefix','suffix']:strings[target.id]=n.value.value
    assert set(strings)=={'prefix','suffix'}
    spec=importlib.util.spec_from_file_location('wifi_owner',ROOT/'drivers/EldenWifi/OwnerLaunchSource.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    prefix=strings['prefix'].replace('elden_bt_runtime_ready','elden_wifi_assets_ready').replace('mode=4','mode=1').replace('/usr/sbin/BlueTool','/usr/libexec/unixnu-wpa_supplicant')
    prefix=prefix.replace('(void)n;(void)bytes;','assert(!strcmp(n,"ewt"));(void)bytes;')
    prefix,count=re.subn(r'const unsigned char h\[20\]=\{[^}]+\};',lambda _:'const unsigned char h[20]={'+','.join('0x'+m.CDHASH[i:i+2] for i in range(0,40,2))+'};',prefix);assert count==1
    suffix=strings['suffix'].replace('elden_bt_owner_launch','elden_wifi_owner_launch').replace('mode=4','mode=1').replace('/usr/sbin/BlueTool','/usr/libexec/unixnu-wpa_supplicant')
    suffix=suffix.replace('REJECT(process.name="bluetoothd",process.name="BlueTool");REJECT(process.name="BlueToolX",process.name="BlueTool");',
        'process.name="unixnu-wpa_suppl";assert(CHECK());process.name="unixnu-wpa_supplicant";assert(CHECK());')
    (out/'test.c').write_text(prefix+m.predicate().decode()+suffix)
    cmd=['cc','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'test.c'),'-o',str(out/'test')]
    for name,args in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(args,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    result={'passed':True,'actual_predicate':True,'prior_fixture_failures_preserved_except_name':True,'name_truncation_accepted_only_with_exact_path_and_cdhash':True,
        'sanitizers':['ASan','UBSan'],'predicate_sha256':hashlib.sha256(m.predicate()).hexdigest(),'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS Wi-Fi exact helper owner predicate')
if __name__=='__main__':main()
