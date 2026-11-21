"""Test the exact firmware revision's ADT parser and packed-allocation selection."""
import argparse,copy,hashlib,json,subprocess,sys
from pathlib import Path
from build_v91_boot import encode_adt
import bt_runtime_boot
from data_capacity_boot import packed_adt
ROOT=Path(__file__).resolve().parents[1]
PIN='d099354d0eab34df5088ca1ba89c9c88bc3260bb'
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['darwin-repository','seed','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    assert json.loads((ROOT/'profiles/v91/firmware-build/plan.json').read_text())['darwin_commit']==PIN
    def blob(name):return subprocess.check_output(['git','-C',str(a.darwin_repository),'show',PIN+':DarwinBootPkg/Driver/'+name])
    source=blob('DarwinBoot.c').decode();parser=source[source.index('STATIC\nBOOLEAN\nAdtNode ('):source.index('STATIC\nBOOLEAN\nValidTrustCaches')]
    selection='RamdiskBytes = ALIGN_VALUE (KeepPacked ? Request->RamdiskSize : RamdiskExpandedSize, EFI_PAGE_SIZE);'
    assert source.count(selection)==1
    for name in ['WindowSize.h','PackedRamdisk.h']:(out/name).write_bytes(blob(name))
    base=json.loads((ROOT/'profiles/v91/boot-build/adt.json').read_text());table=json.loads((ROOT/'profiles/bt-address17/runtime-report.json').read_text())['table_hex']
    q={'profile':'data-capacity-2g','expanded_data':True,'expected_data_bytes':2147483648,'keep_packed_data':True,'text_fixups_hex':table}
    dense=bt_runtime_boot.adt(base,dict(q,profile='ufs-idle-trial'));packed=packed_adt(base,q)
    restored=copy.deepcopy(packed)
    def rename(n):
        for prop in n['properties']:
            if prop['name']=='PackedRAMDisk':prop['name']='RAMDisk'
        for c in n['children']:rename(c)
    rename(restored['tree']);assert restored==dense
    for name,obj in [('dense.adt',dense),('packed.adt',packed)]:(out/name).write_bytes(encode_adt(obj['tree']))
    duplicate=copy.deepcopy(packed)
    def duplicate_node(n):
        for prop in list(n['properties']):
            if prop['name']=='PackedRAMDisk':n['properties'].append(dict(prop,name='RAMDisk'))
        for c in n['children']:duplicate_node(c)
    duplicate_node(duplicate['tree']);(out/'duplicate.adt').write_bytes(encode_adt(duplicate['tree']))
    pre=r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <assert.h>
#define STATIC static
#define CONST const
#define TRUE 1
#define FALSE 0
#define MAX_UINTN SIZE_MAX
#define EFI_PAGE_SIZE 4096
#define SIZE_256MB (256ULL<<20)
#define ALIGN_VALUE(a,b) (((a)+(b)-1)&~((b)-1))
#define AsciiStrCmp strcmp
#define CompareMem memcmp
#define CopyMem memcpy
typedef void VOID;typedef uint8_t UINT8;typedef uint32_t UINT32;typedef uint64_t UINT64;typedef size_t UINTN;typedef uint8_t BOOLEAN;typedef char CHAR8;
static const void *ScanMem8(const void *p,size_t n,int v){return memchr(p,v,n);}
static UINT32 U32(const void *p){UINT32 v;memcpy(&v,p,4);return v;}
static UINT64 U64(const void *p){UINT64 v;memcpy(&v,p,8);return v;}
#define ReadUnaligned32 U32
#define ReadUnaligned64 U64
#include "WindowSize.h"
#include "PackedRamdisk.h"
'''
    tail=r'''
static UINT8 *load(const char *path,UINTN *bytes){FILE *f=fopen(path,"rb");assert(f);assert(!fseek(f,0,SEEK_END));long n=ftell(f);assert(n>0);rewind(f);UINT8 *p=malloc(n);assert(p&&fread(p,1,n,f)==(size_t)n);fclose(f);*bytes=n;return p;}
int main(int argc,char **argv){assert(argc==5);UINTN input_size,expanded;BOOLEAN format_packed;
 UINT8 *seed=load(argv[1],&input_size);assert(RamdiskLayout(seed,input_size,&expanded,&format_packed)&&format_packed&&expanded==2147483648ULL);
 for(unsigned test=0;test<3;test++){
  UINTN size,at=0,ram=MAX_UINTN,trust=MAX_UINTN,addon=MAX_UINTN;UINT64 window=0;BOOLEAN KeepPacked=FALSE;
  UINT8 *tree=load(argv[test+2],&size);int okay=AdtNode(tree,size,&at,0,3,&ram,&trust,&addon,&window,&KeepPacked)&&at==size&&ram!=MAX_UINTN;
  if(test==2){assert(!okay);free(tree);continue;}
  assert(okay&&window==6442450944ULL&&KeepPacked==(test==1));
  struct {UINTN RamdiskSize;} request={input_size},*Request=&request;
  UINTN RamdiskExpandedSize=expanded,RamdiskBytes;
'''+'  '+selection+r'''
  assert(RamdiskBytes==(test==1?ALIGN_VALUE(input_size,4096):2147483648ULL));
  printf("PASS mode=%s firmware-allocation=%llu logical=%llu\n",KeepPacked?"packed":"dense",(unsigned long long)RamdiskBytes,(unsigned long long)expanded);
  free(tree);
 }
 free(seed);puts("PASS exact firmware ADT parser, duplicate rejection and allocation expression");
}
'''
    (out/'test.c').write_text(pre+parser+tail)
    cmd=['clang','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'test.c'),'-o',str(out/'test')]
    for name,args in [('compile',cmd),('run',[str(out/'test'),str(a.seed.resolve()),str(out/'dense.adt'),str(out/'packed.adt'),str(out/'duplicate.adt')])]:
        r=subprocess.run(args,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    record={'passed':True,'firmware_commit':PIN,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'only_adt_name_changed':True,'packed_bytes':a.seed.stat().st_size,'logical_bytes':2147483648,'actual_parser_and_allocation_expression':True,'sanitizers':['ASan','UBSan'],'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print((out/'run.log').read_text())
if __name__=='__main__':main()
