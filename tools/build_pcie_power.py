"""Compile the PCIe budget plan and bind the real native/RPMh providers."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def defs(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(p).items() if not v[0]&0x0e}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['clean-build','native-build','wcn-build','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    d=ROOT/'drivers/EldenPcie';headers=ROOT/'profiles/current-build/sources/a39f9324d152faf7';obj=out/'Power.o'
    command=['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-std=c11','-O2','-Wall','-Wextra','-Werror',
             '-ffreestanding','-fno-builtin','-fno-stack-protector','-mgeneral-regs-only','-I'+str(headers),'-c',str(d/'Power.c'),'-o',str(obj)]
    r=subprocess.run(command,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/'Power.asm').write_text(asm,encoding='utf-8')
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    assert defs(obj)=={'_elden_pcie_power_plan'} and not any(k.endswith('/__mod_init_func') for k in sections(obj))
    native=a.native_build/'WcnPowerNative.o';nr=read(a.native_build/'result.json')
    assert nr['root_power_provider'] and sha(native)==nr['object_sha256']
    for file,h in nr['source_inputs'].items():assert sha(ROOT/file)==h,file
    wcn=a.wcn_build/'WcnPower.o';wr=read(a.wcn_build/'result.json');assert sha(wcn)==wr['objects']['WcnPower']['object_sha256']
    row=read(a.clean_build/'units/result.json')['units']['Sm8750Rpmh'];rpmh=Path(row['object']);assert row['accepted'] and sha(rpmh)==row['sha256']
    cmd=row['command'];overlay=read(Path(cmd[cmd.index('-ivfsoverlay')+1]));matched=[]
    for item in overlay['roots']:
        if item['name'].endswith('/Sm8750Rpmh.c'):matched.append(sha(Path(item['external-contents'])))
    assert matched and set(matched)=={'8d4d7196b922512633ec37915fee24a96a735c5b9892de400055ab7c3c96f565'}
    all_objects=[obj,native,wcn,rpmh];expected_defs=set().union(*(defs(f) for f in all_objects));expected_refs=set().union(*(refs(f) for f in all_objects))-expected_defs
    required={'_elden_pcie_power_plan','_Sm8750CmdDbArc','_Sm8750CmdDbBcm','_Sm8750CmdDbVrm','_Sm8750RpmhWriteActive','_Sm8750RpmhArcTop','_Sm8750BcmCommand'}
    assert required<=expected_defs and not required&expected_refs
    target=out/'PciePowerBinding.o';link=['xcrun','ld','-r','-arch','arm64','-platform_version','ios','17.0','17.0','-o',str(target),*map(str,all_objects)]
    result=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(result.stdout+result.stderr);result.check_returncode()
    assert defs(target)==expected_defs and refs(target)==expected_refs
    report={'compiled':True,'plan_object_sha256':sha(obj),'native_object_sha256':sha(native),'binding_sha256':sha(target),
            'actual_rpmh_provider_bound':True,'rpmh_object_sha256':sha(rpmh),'remaining_imports':sorted(expected_refs),'plan_warnings':r.stderr.count(b'warning:'),
            'scalar':True,'kernel_linked':False,'hardware_votes_tested':False,'root_caller_connected':False,
            'source_sha256':{str(f.relative_to(ROOT)):sha(f) for f in [d/'Power.c',d/'Power.h',headers/'Sm8750Rpmh.h']},'command':command,'link':link}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k in ['compiled','plan_object_sha256','native_object_sha256','binding_sha256','actual_rpmh_provider_bound','plan_warnings']}))
if __name__=='__main__':main()
