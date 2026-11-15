"""Compare real original/repaired MSI entrypoints with failing PCI callbacks."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from PciMsiPatch import patch
PIN='5f7f5a8a9f02f7ab45ed10a2f226e348c519a838'
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--component-repository',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    original=subprocess.check_output(['git','-C',str(a.component_repository),'show',PIN+':src/nw_pci.c']);derived=patch(original)
    fixture=(ROOT/'drivers/EldenWifi/peach/TestPciMsi.c').read_text(encoding='utf-8');results={}
    for name,data in [('original',original),('repaired',derived)]:
        text=data.decode();start=text.index('int pci_alloc_irq_vectors(');end=text.index('int pci_irq_vector(',start)
        code=fixture.replace('// @PCI_MSI_FUNCTIONS@',text[start:end]);file=out/(name+'.c');file.write_text(code,encoding='utf-8',newline='\n');binary=out/name
        cmd=['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-fno-omit-frame-pointer','-DORIGINAL='+str(int(name=='original')),str(file),'-o',str(binary)]
        r=subprocess.run(cmd,capture_output=True,timeout=60);(out/(name+'.compile.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        r=subprocess.run([str(binary)],capture_output=True,timeout=60);(out/(name+'.run.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        results[name]={'passed':True,'result':r.stdout.decode().strip(),'source_sha256':hashlib.sha256(data).hexdigest()}
    result={'results':results,'asan_ubsan':True,'actual_entrypoints':True,'hardware':False,
            'source_inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [ROOT/'drivers/EldenWifi/peach'/n for n in ['PciMsi.inc','PciMsiPatch.py','TestPciMsi.c']]+[Path(__file__)]}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
