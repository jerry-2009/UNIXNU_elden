"""Exercise the actual new platform entry and PCI callback routing."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from PlatformShutdownPatch import patch,PCI,WIFI
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['component-repository','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    original=subprocess.check_output(['git','-C',str(a.component_repository),'show','5f7f5a8a9f02f7ab45ed10a2f226e348c519a838:src/nw_pci.c'])
    derived=patch('nw_pci.c',original).decode();msi=derived[derived.index('int pci_alloc_irq_vectors('):derived.index('int pci_irq_vector(')]
    lifecycle=derived[derived.index('int pci_register_driver('):]
    source=(ROOT/'drivers/EldenWifi/peach/TestPciLifecycle.c').read_text().split('int main(void){')[0]
    source=source.replace('struct device {const char *name;uint64_t dma_mask;};','struct device {const char *name;uint64_t dma_mask;void *driver_data;};')
    source=source.replace('void(*remove)(struct pci_dev *);};','void(*remove)(struct pci_dev *);void(*shutdown)(struct pci_dev *);};')
    source=source.replace('// @MSI@','static void *pci_get_drvdata(struct pci_dev *p){return p->dev.driver_data;}\n'+msi)
    source=source.replace('// @LIFECYCLE@',lifecycle)
    source=source.replace('int rc=pci_alloc_irq_vectors(d,1,32,2);return rc<0?rc:0;', 'int rc=pci_alloc_irq_vectors(d,1,32,2);if(rc>=0)d->dev.driver_data=d;return rc<0?rc:0;')
    source=source.replace('static struct pci_driver driver={ids,probe,remove_device};','''static unsigned shutdowns;
static void shutdown_device(struct pci_dev *d){CHECK(bound&&d==&g_dev&&pci_get_drvdata(d));event('S');shutdowns++;}
static struct pci_driver driver={ids,probe,remove_device,shutdown_device};
static bool pci_started;
static void nw_mainline_shutdown(void){event('L');}
static void nw_wifi_control_shutdown(void){event('C');}
static uint64_t lx_now_ms(void){return 100;}
'''+WIFI)
    source=source.replace('    cases++;g_drv=0;', '    cases++;g_drv=0;shutdowns=0;pci_started=false;driver.shutdown=shutdown_device;elden_shutdown_started=elden_platform_started=0;elden_platform_deadline=0;elden_shutdown_result=elden_platform_result=-EINPROGRESS;')
    source+='''
int main(void){
 reset();CHECK(!elden_wifi_platform_deadline_ms());CHECK(nw_wifi_platform_shutdown()==-ENODEV&&!events);
 CHECK(elden_nw_pci_platform_shutdown()==-ENODEV&&!events);
 reset();CHECK(!pci_register_driver(&driver));pci_started=true;driver.shutdown=NULL;
 CHECK(nw_wifi_platform_shutdown()==-ENODEV&&shutdowns==0&&removes==0&&bound);
 reset();CHECK(!pci_register_driver(&driver));g_dev.dev.driver_data=NULL;
 CHECK(elden_nw_pci_platform_shutdown()==-ENODEV&&shutdowns==0&&bound);
 reset();CHECK(!pci_register_driver(&driver));pci_started=true;
 CHECK(!nw_wifi_platform_shutdown());CHECK(!strcmp(order,"BPMLCSU"));CHECK(elden_wifi_platform_deadline_ms()==2100);
 CHECK(shutdowns==1&&removes==0&&unbinds==1&&!bound&&g_drv==&driver);
 CHECK(!nw_wifi_platform_shutdown()&&!elden_nw_pci_platform_shutdown());CHECK(shutdowns==1&&unbinds==1);
 reset();CHECK(!pci_register_driver(&driver));pci_started=true;unbind_error=-EBUSY;
 CHECK(nw_wifi_platform_shutdown()==-EBUSY&&bound&&shutdowns==1&&removes==0);
 CHECK(nw_wifi_platform_shutdown()==-EBUSY&&shutdowns==1&&unbinds==1);
 reset();CHECK(!pci_register_driver(&driver));pci_unregister_driver(&driver);
 CHECK(removes==1&&shutdowns==0&&!bound&&!g_drv&&!strcmp(order,"BPMRU"));
 printf("%u platform-routing scenarios / %u checks passed; real entry/shim, driver hardware callback modeled\\n",cases,checks);
}
'''
    (out/'test.c').write_text(source)
    cmd=['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'test.c'),'-o',str(out/'test')]
    r=subprocess.run(cmd,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run([str(out/'test')],capture_output=True,timeout=60);(out/'run.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    files=[ROOT/'drivers/EldenWifi/peach'/n for n in ['PlatformShutdownPatch.py','PciLifecyclePatch.py','PciMsiPatch.py','PciMsi.inc','TestPciLifecycle.c']]+[Path(__file__)]
    result={'passed':True,'asan_ubsan':True,'result':r.stdout.decode().strip(),'hardware':False,'source_inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
