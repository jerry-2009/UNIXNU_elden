"""Run the actual publication helper with ownership/failure and inherited-property tests."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    fixture=r'''
#include <cassert>
#include <cstdio>
#include <map>
#include <string>
static unsigned live;static bool dictFail,stringFail,objectFail,propertyFail,discardWrite;
struct OSObject{unsigned refs=1;OSObject(){live++;}virtual ~OSObject(){live--;}void retain(){refs++;}void release(){assert(refs);if(!--refs)delete this;}};
struct OSString:OSObject{std::string text;OSString(const char*s):text(s){}static OSString*withCString(const char*s){return stringFail?nullptr:new OSString(s);}bool isEqualTo(const char*s){return text==s;}};
struct OSDictionary:OSObject{
 std::map<std::string,OSObject*>values;
 ~OSDictionary(){for(auto&p:values)p.second->release();}
 static OSDictionary*withCapacity(unsigned){return dictFail?nullptr:new OSDictionary;}
 static OSDictionary*withDictionary(OSDictionary*d){if(dictFail)return nullptr;auto*n=new OSDictionary;for(auto&p:d->values){p.second->retain();n->values[p.first]=p.second;}return n;}
 bool setObject(const char*k,OSObject*v){if(objectFail)return false;v->retain();auto&i=values[k];if(i)i->release();i=v;return true;}
 OSObject*getObject(const char*k){auto p=values.find(k);return p==values.end()?nullptr:p->second;}
};
#define OSDynamicCast(t,p) dynamic_cast<t*>(p)
static int *gIOServicePlane;
struct IORegistryEntry{
 OSObject*own=nullptr;IORegistryEntry*parent=nullptr;
 ~IORegistryEntry(){if(own)own->release();}
 OSObject*copyProperty(const char*,int*){OSObject*p=own;if(!p&&parent)p=parent->own;if(p)p->retain();return p;}
 OSObject*copyProperty(const char*){if(own)own->retain();return own;}
 bool setProperty(const char*,OSObject*p){if(propertyFail)return false;if(discardWrite)return true;p->retain();if(own)own->release();own=p;return true;}
};
#include "EldenStorageMedium.h"
static void reset(){assert(live==0);dictFail=stringFail=objectFail=propertyFail=discardWrite=false;}
static void seed(IORegistryEntry&d){auto*p=new OSDictionary;auto*v=new OSString("Lenovo");assert(p->setObject("Vendor Name",v));v->release();v=new OSString("Rotational");assert(p->setObject("Medium Type",v));v->release();d.own=p;}
static bool solid(IORegistryEntry&d){auto*p=dynamic_cast<OSDictionary*>(d.own);auto*s=p?dynamic_cast<OSString*>(p->getObject("Medium Type")):nullptr;return s&&s->isEqualTo("Solid State");}
int main(){unsigned cases=0;reset();assert(!elden_storage_solid_state(nullptr));cases++;
 {IORegistryEntry d;assert(elden_storage_solid_state(&d)&&solid(d));assert(elden_storage_solid_state(&d)&&solid(d));cases++;}reset();
 {IORegistryEntry d;seed(d);assert(elden_storage_solid_state(&d)&&solid(d));auto*p=dynamic_cast<OSDictionary*>(d.own);assert(dynamic_cast<OSString*>(p->getObject("Vendor Name"))->isEqualTo("Lenovo"));cases++;}reset();
 {IORegistryEntry parent,child;seed(parent);child.parent=&parent;assert(elden_storage_solid_state(&child)&&solid(child)&&!solid(parent));auto*p=dynamic_cast<OSDictionary*>(child.own);assert(p->getObject("Vendor Name"));cases++;}reset();
 {IORegistryEntry d;d.own=new OSString("invalid dictionary");auto*old=d.own;assert(!elden_storage_solid_state(&d)&&d.own==old);cases++;}reset();
 for(unsigned failure=0;failure<5;failure++){IORegistryEntry d;seed(d);auto*old=d.own;if(failure==0)dictFail=true;if(failure==1)stringFail=true;if(failure==2)objectFail=true;if(failure==3)propertyFail=true;if(failure==4)discardWrite=true;assert(!elden_storage_solid_state(&d)&&d.own==old&&!solid(d));cases++;dictFail=stringFail=objectFail=propertyFail=discardWrite=false;}reset();
 printf("PASS %u medium publication/ownership cases\n",cases);
}
'''
    src=out/'medium.cpp';src.write_text(fixture);exe=out/'medium'
    cmd=[a.cxx,'-std=c++17','-O1','-g','-fsanitize=address,undefined','-I',str(ROOT/'drivers/EldenStorageMedium'),str(src),'-o',str(exe)]
    for name,command in [('compile',cmd),('run',[str(exe)])]:
        r=subprocess.run(command,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    report={'passed':True,'result':r.stdout.decode().strip(),'actual_helper':True,'asan_ubsan':True,'helper_sha256':hashlib.sha256((ROOT/'drivers/EldenStorageMedium/EldenStorageMedium.h').read_bytes()).hexdigest(),'hardware':False,'limits':'Fake object ownership and allocation; real IOKit/ioctl requires hardware verification.'}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
