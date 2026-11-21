"""Reject damaged service assets/trust using the actual qualified kernel inputs."""
import argparse,copy,json,shutil
from pathlib import Path
from wifi_service_boot import qualify_assets,trust_append
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kernel-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);rt=out/'runtime';shutil.copytree(a.kernel_build/'runtime',rt)
    report=json.loads((a.kernel_build/'result.json').read_text());native=(a.kernel_build/'native.macho').read_bytes();base=report['service_assets']['input_trust_sha256'];cases=[]
    qualify_assets(report,rt,native,base);cases.append('actual-assets-pass')
    def reject(label,fn):
        try:fn()
        except (ValueError,KeyError,TypeError):cases.append(label)
        else:raise AssertionError('Incorrectly accepted '+label)
    for name in ['launchd.plist','launchd.plist.sig','runtime.trustcache','EldenWifiServiceAssets.h','unixnu-wpa_supplicant','wpa_supplicant.conf']:
        file=rt/name;old=file.read_bytes();file.write_bytes(bytes([old[0]^1])+old[1:])
        reject('reject-'+name,lambda:qualify_assets(report,rt,native,base));file.write_bytes(old)
    reject('absent-embedded-assets',lambda:qualify_assets(report,rt,b'',base))
    reject('wrong-parent-trust',lambda:qualify_assets(report,rt,native,'0'*64))
    changed=copy.deepcopy(report);changed['core']['assets']['jobs']=563
    reject('mismatched-core',lambda:qualify_assets(changed,rt,native,base))
    digest=report['service_assets']['helper_cdhash'];original=(rt/'base-runtime.trustcache').read_bytes()
    reject('duplicate-cdhash',lambda:trust_append(original,[digest,digest]))
    qualify_assets(report,rt,native,base)
    (out/'result.json').write_text(json.dumps({'passed':True,'cases':cases,'kernel_sha256':report['kernel_sha256'],'hardware_tested':False},indent=2)+'\n')
    print('PASS',len(cases),'service asset qualification cases')
if __name__=='__main__':main()
