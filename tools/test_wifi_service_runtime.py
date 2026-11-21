"""Failure injection on the complete production service staging functions.

The XNU VFS services below are modeled; this is not a live mount/signature test.
"""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=ROOT/'drivers/EldenWifi/ServiceRuntime.inc'
    shim=ROOT/'drivers/EldenWifi/TestServiceRuntime.c'
    text=shim.read_text().replace('/* PRODUCTION_SOURCE */',source.read_text())
    test=out/'test.c';test.write_text(text)
    cmd=['cc','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=address,undefined',
        '-fno-sanitize-recover=all',str(test),'-o',str(out/'test')]
    for name,args in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(args,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    result={'passed':True,'actual_complete_functions':True,'scope':'modeled VFS failures, ready-state and owned rollback',
        'sanitizers':['ASan','UBSan'],'summary':(out/'run.log').read_text().splitlines()[-1],
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'test_sha256':hashlib.sha256(shim.read_bytes()).hexdigest(),'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['summary'])
if __name__=='__main__':main()
