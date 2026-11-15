"""Run the actual parser/init with the old and new bounded table capacities."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth'))
from FixupCapacitySource import source

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    original=(ROOT/'profiles/current-build/sources/5cb9daa1c883ebd2/ubc_subr.c').read_bytes();results=[]
    for label,data,capacity in [('original',original,32),('scan',source(original),40)]:
        text=data.decode();start=text.index('#define CS_TEXT_FIXUP_MAX');end=text.index('STARTUP(EARLY_BOOT, STARTUP_RANK_MIDDLE, cs_text_fixup_init);',start);body=text[start:end]
        pre=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#define PAGE_SIZE 4096
#define PAGE_MASK 4095
#define TUNABLE_STR(name,size,key,value) char name[size]=value
using DTEntry=void*;constexpr int kSuccess=0;static std::string table;
int SecureDTLookupEntry(void*,const char*,DTEntry *p){*p=nullptr;return 0;}
int SecureDTGetProperty(DTEntry,const char*,const void **p,unsigned *n){*p=table.data();*n=(unsigned)table.size();return 0;}
'''
        body=body.replace('const char *s = table, *end = s + size;','const char *s = (const char*)table, *end = s + size;')
        test=r'''
int main(){
 for(unsigned count: {0u,1u,31u,32u,33u,38u,39u,40u,41u,100u}){
  table.clear();cs_text_fixup_count=0;memset(cs_text_fixups,0,sizeof(cs_text_fixups));
  for(unsigned i=0;i<count;i++){char b[100];snprintf(b,sizeof(b),"bluetoothd,%x,00010203,04050607",i*16);table.append(b);table.push_back(0);}
  cs_text_fixup_init();assert(cs_text_fixup_count==(count<CS_TEXT_FIXUP_MAX?count:CS_TEXT_FIXUP_MAX));
  for(unsigned i=0;i<cs_text_fixup_count;i++){assert(cs_text_fixups[i].offset==i*16);assert(cs_text_fixups[i].length==4);assert(cs_text_fixups[i].replacement[3]==7);}
 }
 for(const char *bad: {"",",1,00,01","file,xx,00,01","file,1,0,01","file,1,00,0102","file,fff,0001,0203","file,1,0000000000000000000000000000000000ff,0000000000000000000000000000000000ff"}){
  cs_text_fixup f={};assert(!cs_text_fixup_parse(bad,&f));
 }
 // Firmware entries and eight boot-arg entries share one bound.
 table.clear();cs_text_fixup_count=0;strcpy(cs_text_fixup_arg0,"file,20,00,01");cs_text_fixup_init();assert(cs_text_fixup_count==1);
 puts("PASS real parser bounds and malformed fields");
}
'''
        f=a.output/(label+'.cpp');f.write_text(pre+body+test);exe=a.output/label
        subprocess.run([a.cxx,'-std=c++17','-O1','-g','-fsanitize=address,undefined',str(f),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)],capture_output=True);(a.output/(label+'.log')).write_bytes(run.stdout+run.stderr);run.check_returncode()
        results.append({'variant':label,'capacity':capacity,'actual_body_sha256':hashlib.sha256(body.encode()).hexdigest(),'passed':True})
    (a.output/'result.json').write_text(json.dumps({'passed':True,'asan_ubsan':True,'records':results},indent=2)+'\n');print('PASS original32 and scan40 parser boundaries')
if __name__=='__main__':main()
