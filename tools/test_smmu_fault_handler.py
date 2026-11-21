"""Run the actual extracted native fault/status functions with MMIO/GIC models."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def function(text,signature):
    start=text.index(signature);begin=text.index('{',start);depth=1;end=begin+1
    while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenSmmu';source=(d/'Native.cpp').read_text(encoding='utf-8')
    bodies='\n'.join(function(source,s) for s in ['static void fault(', 'extern "C" int elden_wifi_smmu_ready(', 'extern "C" int elden_wifi_smmu_status('])
    (out/'NativeFaultFunctions.inc').write_text(bodies,encoding='utf-8');(out/'Test.cpp').write_bytes((d/'TestFault.cpp').read_bytes())
    cmd=['clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I'+str(out),'-I'+str(d),str(out/'Test.cpp'),'-o',str(out/'test')]
    for name,args in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(args,capture_output=True,timeout=60);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    result={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'native_source_sha256':hashlib.sha256(source.encode()).hexdigest(),'extracted_functions_sha256':hashlib.sha256(bodies.encode()).hexdigest(),'hardware':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
