"""Build one WCN power provider and the raw-PMU adapter; no device operations."""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def exports(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--llvm',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve()
    if out.exists():raise ValueError('New output required')
    out.mkdir(parents=True);bt=ROOT/'drivers/EldenBluetooth';wifi=ROOT/'drivers/EldenWifi';records={}
    for name,source in [('WcnPower',bt/'WcnPower.c'),('OlCprPlan',wifi/'OlCprPlan.c')]:
        target=out/(name+'.o')
        command=['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-O2','-Wall','-Wextra','-Werror',
                 '-ffreestanding','-fno-builtin','-fno-stack-protector','-mgeneral-regs-only','-I'+str(bt),'-I'+str(wifi),'-c',str(source),'-o',str(target)]
        with (out/(name+'.log')).open('x') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'--disassemble','--reloc',str(target)],text=True);(out/(name+'.asm')).write_text(asm)
        ops=re.findall(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(.+)$',asm,re.M)
        if not ops or any(re.search(r'\b[qvdshb]\d+(?:\b|\.)',v) for v in ops):raise ValueError('Unexpected FP/SIMD')
        if any(n.endswith('/__mod_init_func') for n in sections(target)):raise ValueError('Unexpected automatic initializer')
        symbols=global_symbols(target);imports=sorted(n for n,v in symbols.items() if not v[0]&0x0e)
        records[name]={'source_sha256':sha(source),'object_sha256':sha(target),'exports':sorted(exports(target)),'imports':imports,'scalar':True,'command':command}
    shared={'_elden_wcn_cpr_adjust','_elden_wcn_cpr_plan_details','_elden_wcn_cpr_rail_name','_elden_wcn_cpr_pdc_name'}
    owners={'_elden_wcn_shared_acquire','_elden_wcn_shared_stop','_elden_wcn_shared_cpr','_elden_wcn_shared_snapshot'}
    legacy={'_elden_wcn_rail_specs','_elden_wcn_power_acquire','_elden_wcn_power_stop','_elden_wcn_power_finish','_elden_wcn_power_check','_elden_wcn_parent_decode','_elden_wcn_cpr_plan','_elden_wcn_power_cpr'}
    if set(records['WcnPower']['exports'])!=shared|legacy|owners:raise ValueError('Provider exports changed unexpectedly')
    if set(records['OlCprPlan']['exports'])!={'_elden_olcpr_prepare','_elden_olcpr_adjust','_elden_olcpr_rail_name','_elden_olcpr_pdc_name'}:raise ValueError('Adapter exports changed')
    if not shared<=set(records['OlCprPlan']['imports']):raise ValueError('Adapter bypassed shared provider')
    unresolved=(set(records['WcnPower']['imports'])|set(records['OlCprPlan']['imports']))-shared-legacy-owners
    if not unresolved<={'_memcpy','_memset','_bzero','_strcmp'}:raise ValueError('Unexpected external dependency')
    archive=out/'libEldenWcnPower.a'
    subprocess.run(['/usr/bin/ar','rcs',str(archive),str(out/'WcnPower.o')],env=dict(os.environ,ZERO_AR_DATE='1'),check=True)
    result={'objects':records,'headers_sha256':{'WcnPower.h':sha(bt/'WcnPower.h'),'OlCprPlan.h':sha(wifi/'OlCprPlan.h'),
            'WcnSharedPower.h':sha(bt/'WcnSharedPower.h'),'WcnSharedPower.inc':sha(bt/'WcnSharedPower.inc')},'provider_archive_sha256':sha(archive),
            'shared_provider_bound':True,'remaining_imports':sorted(unresolved),'legacy_exports_preserved':True,
            'integration_rule':'Link libEldenWcnPower.a once and OlCprPlan.o; omit any duplicate WcnPower.o from Bluetooth/Wi-Fi archives.',
            'shared_consumer_controller':True,'native_runtime_gateway_added':False,'kernel_linked':False,'hardware_operations':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'shared_provider_bound':True,'remaining_imports':sorted(unresolved),'kernel_linked':False}))
if __name__=='__main__':main()
