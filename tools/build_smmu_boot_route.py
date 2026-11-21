"""Compile the boot-route registry and derived touch route without hardware writes."""
import argparse,hashlib,importlib.util,json,re,subprocess
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--llvm',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenSmmu'
    spec=importlib.util.spec_from_file_location('touch_smmu',d/'TouchSource.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    (out/'DmaRoute.c').write_bytes(mod.route());(out/'EldenSmmuBootRoute.h').write_bytes((d/'BootRoute.h').read_bytes())
    registry={'_elden_smmu_boot_route_'+n for n in ['state','reserve','commit','poison','seal','expected']}
    touch={'_elden_touch_route_'+n for n in ['attach','observe','detach']};records={};objects=[]
    for name,source in [('BootRoute',d/'BootRoute.c'),('DmaRoute',out/'DmaRoute.c')]:
        obj=out/(name+'.o');objects.append(obj)
        cmd=['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-std=c11','-O2','-Wall','-Wextra','-Werror',
             '-ffreestanding','-fno-builtin','-fno-stack-protector','-mgeneral-regs-only',
             *['-I'+str(v) for v in [out,d,ROOT/'drivers/EldenNvt36536',ROOT/'package',ROOT/'soc/sm8750/include']],'-c',str(source),'-o',str(obj)]
        r=subprocess.run(cmd,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/(name+'.asm')).write_text(asm,encoding='utf-8')
        assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
        assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
        syms=global_symbols(obj);defs={n for n,v in syms.items() if v[0]&0x0e};refs={n for n,v in syms.items() if not v[0]&0x0e}
        assert defs==(registry if name=='BootRoute' else touch)
        assert refs==(set() if name=='BootRoute' else {'_elden_smmu_boot_route_seal','_elden_smmu_boot_route_expected'})
        records[name]={'object_sha256':sha(obj),'source_sha256':sha(source),'exports':sorted(defs),'imports':sorted(refs),'warnings':r.stderr.count(b'warning:')}
    target=out/'TouchSmmuBinding.o'
    r=subprocess.run(['xcrun','ld','-r','-arch','arm64','-platform_version','ios','17.0','17.0','-o',str(target),*map(str,objects)],capture_output=True)
    (out/'link.log').write_bytes(r.stdout+r.stderr);r.check_returncode();symbols=global_symbols(target)
    assert {n for n,v in symbols.items() if v[0]&0x0e}==registry|touch
    assert not {n for n,v in symbols.items() if not v[0]&0x0e}
    files=['drivers/EldenSmmu/'+n for n in ['BootRoute.c','BootRoute.h','TouchSource.py']]
    files+=['drivers/EldenNvt36536/DmaRoute.c','drivers/EldenNvt36536/DmaRoute.h','package/EldenTouchBoard.h','soc/sm8750/include/EldenTouchResources.h']
    result={'compiled':True,'objects':records,'binding_sha256':sha(target),'source_inputs':{n:sha(ROOT/n) for n in files},
            'scalar':True,'native_hardware_provider':False,'kernel_linked':False,'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
