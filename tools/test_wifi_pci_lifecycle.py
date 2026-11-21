"""Verify exact native-binding sites in the prepared Linux PCI adapter."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from PciLifecyclePatch import patch
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['component-repository','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    original=subprocess.check_output(['git','-C',str(a.component_repository),'show','5f7f5a8a9f02f7ab45ed10a2f226e348c519a838:src/nw_pci.c']);derived=patch(original);text=derived.decode()
    msi=text[text.index('int pci_alloc_irq_vectors('):text.index('int pci_irq_vector(')]
    lifecycle=text[text.index('int pci_register_driver('):]
    fixture=(ROOT/'drivers/EldenWifi/peach/TestPciLifecycle.c').read_text(encoding='utf-8').replace('// @MSI@',msi).replace('// @LIFECYCLE@',lifecycle)
    source=out/'test.c';source.write_text(fixture,encoding='utf-8',newline='\n')
    cmd=['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(source),'-o',str(out/'test')]
    r=subprocess.run(cmd,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run([str(out/'test')],capture_output=True,timeout=60);(out/'run.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    files=[ROOT/'drivers/EldenWifi/peach'/n for n in ['PciMsiPatch.py','PciMsi.inc','PciLifecyclePatch.py','TestPciLifecycle.c']]+[Path(__file__)]
    result={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'hardware':False,'derived_pci_sha256':hashlib.sha256(derived).hexdigest(),
            'source_inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
