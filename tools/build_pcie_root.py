"""Compile and bind root/PHY transaction objects; no native provider or kernel."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from replay_xnu_objects import sections,global_symbols
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--llvm',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenPcie';records={}
    for name in ['Root','Phy']:
        obj=out/(name+'.o');cmd=['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-std=c11','-O2','-Wall','-Wextra','-Werror',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-mgeneral-regs-only','-c',str(d/(name+'.c')),'-o',str(obj)]
        r=subprocess.run(cmd,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/(name+'.asm')).write_text(asm,encoding='utf-8')
        assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
        assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
        syms=global_symbols(obj);exports={n for n,v in syms.items() if v[0]&0x0e};imports={n for n,v in syms.items() if not v[0]&0x0e}
        assert imports==({'_elden_pcie_phy_start'} if name=='Root' else set())
        records[name]={'object_sha256':sha(obj),'exports':sorted(exports),'imports':sorted(imports),'command':cmd,'warnings':r.stderr.count(b'warning:')}
    target=out/'PcieCold.o';r=subprocess.run(['xcrun','ld','-r','-arch','arm64','-platform_version','ios','17.0','17.0','-o',str(target),str(out/'Root.o'),str(out/'Phy.o')],capture_output=True)
    (out/'link.log').write_bytes(r.stdout+r.stderr);r.check_returncode();syms=global_symbols(target)
    assert not {n for n,v in syms.items() if not v[0]&0x0e}
    assert {n for n,v in syms.items() if v[0]&0x0e}=={'_elden_pcie_phy_start','_elden_pcie_root_start','_elden_pcie_config_read32','_elden_pcie_window_base','_elden_pcie_window_bytes'}
    report={'compiled':True,'objects':records,'combined_sha256':sha(target),'root_phy_bound':True,'scalar':True,'kernel_linked':False,'native_provider_implemented':False,'hardware_tested':False,
            'source_sha256':{n:sha(d/n) for n in ['Root.c','Root.h','Phy.c','Phy.h','PhySequence.inc']}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
