"""Prepare the real iOS17 supplicant and signed launchd/trust assets, offline."""
import argparse,copy,ctypes,hashlib,json,plistlib,re,shutil,struct,subprocess,sys
from pathlib import Path
from build_elden_bluetool import verify_target
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/legacy-workbench'))
from icon_cpu_trust import parts
KEY='/System/Library/LaunchDaemons/org.unixnu.wifi.supplicant.plist'
BASE_CACHE='d258da13c01861a229fe64153e239750d5e9253ff53b692c2db76e782bbfc98d'
HELPER='f54eb63475c7f3b3cb0d1d1ed78728a941fb8c07e363f88cf8c5095a69adecb7'
CDHASH='b02572b5f0fd9e79790645ad33df708b24530295'
def sha(data):return hashlib.sha256(data).hexdigest()
def host_parse(data,job):
    lib=ctypes.CDLL('/usr/lib/system/libxpc.dylib')
    for name,args,result in [('xpc_create_from_plist',[ctypes.c_void_p,ctypes.c_size_t],ctypes.c_void_p),
        ('xpc_dictionary_get_value',[ctypes.c_void_p,ctypes.c_char_p],ctypes.c_void_p),
        ('xpc_dictionary_get_count',[ctypes.c_void_p],ctypes.c_size_t),
        ('xpc_dictionary_get_string',[ctypes.c_void_p,ctypes.c_char_p],ctypes.c_char_p),
        ('xpc_array_get_string',[ctypes.c_void_p,ctypes.c_size_t],ctypes.c_char_p),
        ('xpc_release',[ctypes.c_void_p],None)]:
        f=getattr(lib,name);f.argtypes=args;f.restype=result
    buf=ctypes.create_string_buffer(data);root=lib.xpc_create_from_plist(buf,len(data));assert root
    try:
        jobs=lib.xpc_dictionary_get_value(root,b'LaunchDaemons');assert lib.xpc_dictionary_get_count(jobs)==562
        item=lib.xpc_dictionary_get_value(jobs,KEY.encode());assert item
        assert lib.xpc_dictionary_get_string(item,b'UserName')==b'root'
        argv=lib.xpc_dictionary_get_value(item,b'ProgramArguments')
        for i,value in enumerate(job['ProgramArguments']):assert lib.xpc_array_get_string(argv,i)==value.encode()
    finally:lib.xpc_release(root)
def main():
    if sys.platform!='darwin' or sys.flags.optimize:raise SystemExit('macOS and enabled assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['base-runtime','userland','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    base=a.base_runtime.resolve();user=a.userland.resolve();report=json.loads((user/'result.json').read_text())
    original=(base/'launchd.plist').read_bytes();trust=(base/'runtime.trustcache').read_bytes()
    assert sha(original)==BASE_CACHE
    assert report['component_revision']=='5f7f5a8a9f02f7ab45ed10a2f226e348c519a838' and not report['authentication_algorithms_modified']
    for name,h in report['files'].items():assert sha((user/name).read_bytes())==h,name
    binary=out/'unixnu-wpa_supplicant';shutil.copyfile(user/binary.name,binary);binary.chmod(0o755)
    assert sha(binary.read_bytes())==HELPER;target=verify_target(binary)
    subprocess.run(['codesign','--verify','--strict',str(binary)],check=True)
    detail=subprocess.run(['codesign','--display','--verbose=4',str(binary)],check=True,capture_output=True,text=True).stderr
    match=re.search(r'^CDHash=([0-9a-f]{40})$',detail,re.M);assert match and match[1]==CDHASH
    job=plistlib.loads((user/'org.unixnu.wifi.supplicant.plist').read_bytes())
    assert job['Label']=='org.unixnu.wifi.supplicant' and job['UserName']=='root'
    assert job['ProgramArguments']==['/usr/libexec/unixnu-wpa_supplicant','-Dsheng','-ien0','-c/private/var/ngpu/etc/wifi/wpa_supplicant.conf','-q','-s']
    config=(user/'wpa_supplicant.conf').read_bytes()
    assert config==b'# Networks arrive from the native Wi-Fi control channel.\nap_scan=1\n'
    before=plistlib.loads(original);assert len(before['LaunchDaemons'])==561 and KEY not in before['LaunchDaemons']
    after=copy.deepcopy(before);after['LaunchDaemons'][KEY]=job
    cache=out/'launchd.plist';cache.write_bytes(plistlib.dumps(after,fmt=plistlib.FMT_XML,sort_keys=False))
    subprocess.run(['plutil','-convert','binary1',str(cache)],check=True)
    data=cache.read_bytes();decoded=plistlib.loads(data);assert decoded['LaunchDaemons'].pop(KEY)==job and decoded==before
    assert len(data)<=1048576;host_parse(data,job)
    sig=out/'launchd.plist.sig'
    subprocess.run(['codesign','--force','--sign','-','--pagesize','4096','--digest-algorithm','sha256','--identifier','org.unixnu.elden.wifi.launchd-cache','--detached',str(sig),str(cache)],check=True)
    subprocess.run(['codesign','--verify','--strict','--detached',str(sig),str(cache)],check=True)
    detail=subprocess.run(['codesign','--display','--verbose=4','--detached',str(sig),str(cache)],check=True,capture_output=True,text=True).stderr
    match=re.search(r'^CDHash=([0-9a-f]{40})$',detail,re.M);assert match
    cache_hash=match[1];old=parts(trust);digests=sorted([bytes.fromhex(CDHASH),bytes.fromhex(cache_hash)])
    assert all(d not in [part[i:i+20] for part in old for i in range(24,len(part),24)] for d in digests)
    added=struct.pack('<I16sI',2,hashlib.sha256(trust+b''.join(digests)).digest()[:16],2)+b''.join(d+bytes([2,0,0,0]) for d in digests)
    modules=old+[added];at=4*(len(modules)+1);offsets=[]
    for module in modules:offsets.append(at);at+=len(module)
    combined=struct.pack('<I',len(modules))+struct.pack('<'+'I'*len(offsets),*offsets)+b''.join(modules)
    assert parts(combined)[:-1]==old and parts(combined)[-1]==added
    (out/'runtime.trustcache').write_bytes(combined);(out/'wpa_supplicant.conf').write_bytes(config)
    (out/'org.unixnu.wifi.supplicant.plist').write_bytes(plistlib.dumps(job))
    header='#include <stdint.h>\n'
    blobs=[('elden_wifi_supplicant',binary.read_bytes()),('elden_wifi_launch_cache',data),('elden_wifi_launch_cache_signature',sig.read_bytes()),('elden_wifi_supplicant_config',config)]
    for name,blob in blobs:header+='static const uint8_t '+name+'[]={\n'+','.join(map(str,blob))+'\n};\n'
    (out/'EldenWifiServiceAssets.h').write_text(header)
    result={'prepared':True,'base_cache_sha256':BASE_CACHE,'input_trust_sha256':sha(trust),'helper_sha256':HELPER,'helper_cdhash':CDHASH,'target':target,
        'cache_sha256':sha(data),'cache_bytes':len(data),'signature_sha256':sha(sig.read_bytes()),'cache_cdhash':cache_hash,'trust_sha256':sha(combined),
        'old_jobs_unchanged':561,'jobs':562,'other_top_level_entries_unchanged':True,'old_trust_modules_unchanged':True,'new_trust_entries':2,
        'job':job,'config_sha256':sha(config),'header_sha256':sha(header.encode()),'host_xpc_passed':True,'signatures_verified':True,
        'credentials_included':False,'installed':False,'hardware_tested':False,'source_sha256':sha(Path(__file__).read_bytes())}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
