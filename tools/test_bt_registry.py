"""Exercise actual radio publication/retraction with registry failure doubles."""
from pathlib import Path
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth'))
from RegistrySource import source
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
    text=source().decode();body=text[text.index('static bool publish('):text.index('static void finish(')]
    prefix=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <map>
#include <string>
#include <vector>
struct OSObject;static std::vector<OSObject*> objects;static unsigned set_calls,fail_set,logs;static bool fail_init,fail_attach,fail_start;
struct OSObject{int refs=1;bool released=false;OSObject(){objects.push_back(this);}virtual ~OSObject()=default;void retain(){refs++;}void release(){assert(refs>0);refs--;released=true;}};
struct OSData:OSObject{std::vector<uint8_t> bytes;static OSData *withBytes(const void *p,size_t n){auto d=new OSData;d->bytes.assign((const uint8_t*)p,(const uint8_t*)p+n);return d;}size_t getLength(){return bytes.size();}void *getBytesNoCopy(){return bytes.data();}};
struct OSString:OSObject{std::string text;explicit OSString(const char *p):text(p){}};
struct IORegistryEntry;static IORegistryEntry *chosen,*product,*radio;static void *gIODTPlane;
struct IORegistryEntry:OSObject{
std::map<std::string,OSObject*> props;
static IORegistryEntry *fromPath(const char *p,void*){if(!strcmp(p,"/chosen"))return chosen;if(!strcmp(p,"/product"))return product;if(!strcmp(p,"/arm-io/bluetooth"))return radio;return nullptr;}
OSObject *getProperty(const char *p){auto i=props.find(p);return i==props.end()?nullptr:i->second;}
bool setProperty(const char *p,OSObject *v){if(++set_calls==fail_set)return false;auto old=getProperty(p);if(old)old->release();v->retain();props[p]=v;return true;}
bool setProperty(const char *p,const void *v,size_t n){return setProperty(p,OSData::withBytes(v,n));}
bool setProperty(const char *p,const char *v){return setProperty(p,new OSString(v));}
void removeProperty(const char *p){auto old=getProperty(p);if(old)old->release();props.erase(p);}
};
struct IOService;static IOService *platform;
struct IOService:IORegistryEntry{IOService *parent=nullptr;bool registered=false,stopped=false;std::string name;
static IOService *getPlatform(){return platform;}bool init(){return !fail_init;}void setName(const char *p){name=p;}
bool attach(IOService *p){assert(p==platform);if(fail_attach)return false;parent=p;return true;}
void detach(IOService *p){assert(p==parent);parent=nullptr;}bool start(IOService *p){assert(p==parent);return !fail_start;}
void registerService(){registered=true;}void terminate(unsigned){stopped=true;}
};
#define OSDynamicCast(T,x) dynamic_cast<T*>(x)
enum{kIOServiceRequired=1,kIOServiceSynchronous=2};
static const char *ServiceName="bluetooth";static unsigned host_public_state;
struct Host{IORegistryEntry *chosen=nullptr,*product=nullptr,*radio_node=nullptr;OSObject *old_address=nullptr,*old_le=nullptr,*old_radio_address=nullptr;OSData *address_property=nullptr,*le_property=nullptr;IOService *service=nullptr;bool withdrawing=false;};
static void pb_bdaddr_written(const uint8_t *wire,uint8_t *address){for(unsigned i=0;i<6;i++)address[i]=wire[5-i];}
static void log(const char*){logs++;}
static void clean(){for(auto p:objects)delete p;objects.clear();}
static void setup(){fail_set=set_calls=logs=0;fail_init=fail_attach=fail_start=false;chosen=new IORegistryEntry;product=new IORegistryEntry;radio=new IORegistryEntry;platform=new IOService;
uint32_t one=1,baud=8000000;radio->setProperty("transport-encoding",&one,4);radio->setProperty("transport-speed",&baud,4);
uint8_t v=9;chosen->setProperty("mac-address-bluetooth0",&v,1);v=8;product->setProperty("bluetooth-le",&v,1);v=7;radio->setProperty("local-mac-address",&v,1);set_calls=0;host_public_state=0;}
'''
    suffix=r'''
int main(){unsigned cases=0;uint8_t wire[6]={1,2,3,4,5,6};
for(unsigned mode=0;mode<10;mode++){
setup();auto c=chosen->getProperty("mac-address-bluetooth0"),l=product->getProperty("bluetooth-le"),r=radio->getProperty("local-mac-address");
if(mode==1)radio=nullptr;uint32_t zero=0,bad=3200000;
if(mode==2)radio->setProperty("transport-encoding",&zero,4);
if(mode==3)radio->setProperty("transport-speed",&bad,4);
if(mode==4)radio->setProperty("transport-encoding",&bad,3);
if(mode==5)radio->setProperty("transport-encoding","wrong type");
if(mode==6)platform=nullptr;fail_init=mode==7;fail_attach=mode==8;fail_start=mode==9;set_calls=0;
Host h;bool ok=publish(&h,wire);assert(ok==(mode==0));
if(ok){assert(h.service&&h.service->registered&&h.service->parent==platform&&logs==1);auto dtype=dynamic_cast<OSString*>(h.service->getProperty("device_type"));assert(dtype&&dtype->text=="bluetooth");assert(chosen->getProperty("mac-address-bluetooth0")==radio->getProperty("local-mac-address"));assert(h.address_property->bytes==std::vector<uint8_t>({6,5,4,3,2,1}));}
retract(&h);assert(chosen->getProperty("mac-address-bluetooth0")==c&&product->getProperty("bluetooth-le")==l);if(radio)assert(radio->getProperty("local-mac-address")==r);assert(host_public_state==2);cases++;clean();}
for(unsigned fail=1;fail<=8;fail++){setup();auto c=chosen->getProperty("mac-address-bluetooth0"),l=product->getProperty("bluetooth-le"),r=radio->getProperty("local-mac-address");fail_set=fail;Host h;assert(!publish(&h,wire));fail_set=0;retract(&h);assert(chosen->getProperty("mac-address-bluetooth0")==c&&product->getProperty("bluetooth-le")==l&&radio->getProperty("local-mac-address")==r);cases++;clean();}
setup();Host h;assert(publish(&h,wire));uint8_t x=42;auto foreign=OSData::withBytes(&x,1);radio->setProperty("local-mac-address",foreign);retract(&h);assert(radio->getProperty("local-mac-address")==foreign);cases++;clean();assert(cases==19);
}
'''
    f=o/'test.cpp';f.write_text(prefix+body+suffix)
    cmd=['c++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(f),'-o',str(o/'test')]
    for n,c in [('compile',cmd),('run',[str(o/'test')])]:
        r=subprocess.run(c,capture_output=True);(o/(n+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    (o/'result.json').write_text(json.dumps({'passed':True,'cases':19,'actual_publish_and_retract':True,'sanitizers':['ASan','UBSan'],'scope':'registry/type/property/parent/failure/withdrawal model, not hardware'},indent=2)+'\n');print('PASS registry19 cases')
if __name__=='__main__':main()
