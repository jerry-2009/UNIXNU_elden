"""Build the proven Piano WPA2 helper for iOS17 and its exact launch assets.

The source comes from the fixed donor in-repository, with only control/path
and branding substitutions. All authentication/crypto algorithms stay exact.
No credentials are read, written or included by this tool.
"""
import argparse,copy,ctypes,hashlib,json,plistlib,re,subprocess,sys
from pathlib import Path
from build_elden_bluetool import verify_target
from wifi_service_boot import trust_append
ROOT=Path(__file__).resolve().parents[1]
STATION=ROOT/'drivers/EldenWifi/portable/station'
KEY='/System/Library/LaunchDaemons/org.unixnu.wifi.supplicant.plist'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def run(cmd,out,name):
    r=subprocess.run(cmd,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode();return r

def source():
    text=(STATION/'upstream/piano-wifi-supplicant.c').read_text()
    old=text
    text=text.replace('#include "../../../package/PianoWifi/PianoWifiNet.h"','#include "StationApi.h"')
    text=text.replace('"/private/var/db/piano-wifi/profile"','"/private/var/ngpu/etc/wifi/wpa_supplicant.conf"')
    text=text.replace('piano-wifi-supplicant','elden-wifi-supplicant')
    restored=text.replace('elden-wifi-supplicant','piano-wifi-supplicant').replace('"/private/var/ngpu/etc/wifi/wpa_supplicant.conf"','"/private/var/db/piano-wifi/profile"').replace('#include "StationApi.h"','#include "../../../package/PianoWifi/PianoWifiNet.h"')
    if restored!=old:raise ValueError('Authentication source changed')
    return text.encode()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['base-runtime','clang','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base,out=a.base_runtime.resolve(),a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    lock=read(STATION/'upstream/source.json')
    for row in lock['files']:
        if sha(STATION/'upstream'/row['path'])!=row['sha256']:raise ValueError('Station donor changed')
    code=out/'elden-wifi-supplicant.c';code.write_bytes(source())
    binary=out/'unixnu-wpa_supplicant'
    sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
    mac_sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
    # iOS SDK omits these public XNU control headers. Add only their identical
    # public definitions, never a whole macOS SDK or target libc headers.
    include=out/'headers/sys';include.mkdir(parents=True)
    for name in ['kern_control.h','sys_domain.h']:
        (include/name).write_bytes((Path(mac_sdk)/'usr/include/sys'/name).read_bytes())
    # CommonCrypto and kernel-control ABI are public C interfaces on both OSes;
    # no Foundation/macOS-only API is referenced by the selected helper.
    cmd=[str(a.clang),'-target','arm64-apple-ios17.0','-isysroot',sdk,'-std=c11','-O2','-g0','-Wno-deprecated-declarations',
         '-Wall','-Wextra','-Werror','-I',str(out/'headers'),'-I',str(STATION),'-I',str(ROOT/'drivers/EldenWifi/portable/upstream'),str(code),'-o',str(binary)]
    run(cmd,out,'helper-build');target=verify_target(binary)
    run(['codesign','--force','--sign','-','--pagesize','4096','--digest-algorithm','sha256','--identifier','org.unixnu.elden.wifi.supplicant',str(binary)],out,'helper-sign')
    run(['codesign','--verify','--strict',str(binary)],out,'helper-verify')
    detail=subprocess.check_output(['codesign','--display','--verbose=4',str(binary)],stderr=subprocess.STDOUT,text=True)
    cdhash=re.search(r'^CDHash=([0-9a-f]{40})$',detail,re.M)[1]
    # The unchanged donor's crypto self-test runs with the host SDK build,
    # since a target iOS17 executable cannot be executed on the Mac host.
    native=out/'helper-host'
    hostcmd=['xcrun','--sdk','macosx','clang','-std=c11','-O1','-g','-Wno-deprecated-declarations','-fsanitize=address,undefined',
        '-I',str(STATION),'-I',str(ROOT/'drivers/EldenWifi/portable/upstream'),str(code),'-o',str(native)]
    run(hostcmd,out,'crypto-host-build');run([str(native),'--self-test'],out,'crypto-self-test')
    before=plistlib.loads((base/'base-launchd.plist').read_bytes());assert len(before['LaunchDaemons'])==561 and KEY not in before['LaunchDaemons']
    job={'Label':'org.unixnu.wifi.supplicant','ProgramArguments':['/usr/libexec/unixnu-wpa_supplicant','--profile','/private/var/ngpu/etc/wifi/wpa_supplicant.conf'],
        'RunAtLoad':True,'KeepAlive':True,'UserName':'root','ProcessType':'Background','ThrottleInterval':10}
    after=copy.deepcopy(before);after['LaunchDaemons'][KEY]=job
    cache=out/'launchd.plist';cache.write_bytes(plistlib.dumps(after,fmt=plistlib.FMT_XML,sort_keys=False));run(['plutil','-convert','binary1',str(cache)],out,'cache-convert')
    decoded=plistlib.loads(cache.read_bytes());assert decoded['LaunchDaemons'].pop(KEY)==job and decoded==before
    sig=out/'launchd.plist.sig';run(['codesign','--force','--sign','-','--pagesize','4096','--digest-algorithm','sha256','--identifier','org.unixnu.elden.wifi.launchd-cache','--detached',str(sig),str(cache)],out,'cache-sign')
    run(['codesign','--verify','--strict','--detached',str(sig),str(cache)],out,'cache-verify')
    detail=subprocess.check_output(['codesign','--display','--verbose=4','--detached',str(sig),str(cache)],stderr=subprocess.STDOUT,text=True)
    cachehash=re.search(r'^CDHash=([0-9a-f]{40})$',detail,re.M)[1]
    trust=trust_append((base/'base-runtime.trustcache').read_bytes(),[cdhash,cachehash]);(out/'runtime.trustcache').write_bytes(trust)
    config=b'# Profile arrives through the privileged station control channel.\n'
    (out/'wpa_supplicant.conf').write_bytes(config);(out/'org.unixnu.wifi.supplicant.plist').write_bytes(plistlib.dumps(job))
    for name in ['base-launchd.plist','base-runtime.trustcache']:(out/name).write_bytes((base/name).read_bytes())
    header='#include <stdint.h>\n'
    for name,data in [('elden_wifi_supplicant',binary.read_bytes()),('elden_wifi_launch_cache',cache.read_bytes()),('elden_wifi_launch_cache_signature',sig.read_bytes()),('elden_wifi_supplicant_config',config)]:
        header+='static const uint8_t '+name+'[]={\n'+','.join(map(str,data))+'\n};\n'
    (out/'EldenWifiServiceAssets.h').write_text(header)
    result=dict(prepared=True,station_assets=True,helper_sha256=sha(binary),helper_cdhash=cdhash,target=target,cache_sha256=sha(cache),cache_bytes=cache.stat().st_size,
       signature_sha256=sha(sig),cache_cdhash=cachehash,trust_sha256=sha(out/'runtime.trustcache'),input_trust_sha256=sha(base/'base-runtime.trustcache'),
       base_cache_sha256=sha(base/'base-launchd.plist'),old_jobs_unchanged=561,jobs=562,new_trust_entries=2,other_top_level_entries_unchanged=True,
       old_trust_modules_unchanged=True,job=job,config_sha256=sha(out/'wpa_supplicant.conf'),header_sha256=sha(out/'EldenWifiServiceAssets.h'),
       signatures_verified=True,credentials_included=False,crypto_source_unchanged=True,crypto_self_test=True,helper_source_sha256=sha(code),
       source_inputs={n:sha(ROOT/n) for n in ['tools/build_wifi_station_assets.py','drivers/EldenWifi/portable/station/StationApi.h','drivers/EldenWifi/portable/station/upstream/source.json']},
       hardware_tested=False,installed=False)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['helper_sha256','helper_cdhash','crypto_self_test','jobs']}))

if __name__=='__main__':main()
