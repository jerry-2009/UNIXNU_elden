"""Build/sign the typed-phase helper from the original owned C source."""
from pathlib import Path
import argparse,hashlib,json,plistlib,re,subprocess,sys
from build_elden_bluetool import verify_target
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth/userland'))
from TraceSource import source
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
    if out.exists():raise ValueError('Fresh output required')
    out.mkdir(parents=True);text=out/'BlueTool.c';text.write_bytes(source())
    sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip();owned=ROOT/'drivers/EldenBluetooth/userland'
    cmd=['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-isysroot',sdk,'-O2','-Wall','-Wextra','-Werror','-fblocks','-fstack-protector-strong','-I',str(owned),'-I',str(owned.parent),str(text),str(owned/'BootReply.c'),'-o',str(out/'BlueTool')]
    r=subprocess.run(cmd,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    ent=out/'entitlements.plist';ent.write_bytes(plistlib.dumps({'com.apple.private.security.no-container':True}))
    subprocess.run(['codesign','--force','--sign','-','--pagesize','4096','--identifier','org.unixnu.elden.BlueTool','--entitlements',str(ent),str(out/'BlueTool')],check=True)
    subprocess.run(['codesign','--verify','--strict',str(out/'BlueTool')],check=True);target=verify_target(out/'BlueTool')
    detail=subprocess.run(['codesign','--display','--verbose=4',str(out/'BlueTool')],capture_output=True,text=True,check=True).stderr
    digest=re.search(r'^CDHash=([0-9a-f]{40})$',detail,re.M)
    if not digest:raise ValueError('No CodeDirectory hash')
    inputs=[owned/'BlueTool.c',owned/'BootReply.c',owned/'BootReply.h',owned.parent/'BootstrapStatus.h',owned/'TraceSource.py',owned/'TraceMarker.h',Path(__file__).resolve()]
    report={'profile':'bluetool-trace-helper','helper_sha256':sha(out/'BlueTool'),'cdhash':digest[1],'generated_source_sha256':sha(text),'target':target,'source_inputs':{str(f.relative_to(ROOT)):sha(f) for f in inputs},'command':cmd,'reply_logic_unchanged':True,'installed':False,'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['source_inputs','command']},indent=2))
if __name__=='__main__':main()
