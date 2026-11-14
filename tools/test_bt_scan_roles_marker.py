"""Test the exact capability snapshot marker with bounded copyin doubles."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    marker=(ROOT/'drivers/EldenBluetooth/diagnostics/NativeScanRolesMarker.inc').read_text()
    pre=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
using user_addr_t=uint64_t;
struct Proc{int pid;const char *name;bool hash;};using proc_t=Proc*;
uint32_t cs_text_fixup_parsed=40,cs_text_fixup_applied=40;
int calls,copies,copy_error;uint64_t page=0x100945000;uint32_t result_seen;
int proc_pid(proc_t p){return p->pid;}const char*proc_best_name(proc_t p){return p->name;}
int proc_getcdhash(proc_t p,unsigned char *out){const unsigned char h[]={0xfe,0x7b,0xc1,0x82,0x38,0x6a,0x27,0x66,0xc7,0x57,0x4f,0x8b,0x48,0x41,0x2f,0xf9,0xdf,0x11,0x35,0x64};memcpy(out,h,20);out[0]^=!p->hash;return 0;}
int elden_bt_native_init_result(proc_t,uint32_t result){++calls;result_seen=result;return result==0;}
int copyin(user_addr_t address,void *out,size_t n){
 ++copies;
 assert((address==page+0x820&&n==64)||(address==page-0x7000+0x8b0&&n==1)||(address==page-0x9000+0x32d&&n==2)||(address==page-0x66f344&&n==4)||(address==page-0x72e120&&n==4));
 if(copy_error)return copy_error;
 memset(out,0,n);if(n==64){((uint8_t*)out)[18]=8;((uint8_t*)out)[37]=0x60;}else if(n<4)*(uint8_t*)out=1;else *(uint32_t*)out=0x14000001;return 0;
}
void invoke(proc_t p,uint32_t code,uint64_t status,uint64_t mode,uint64_t version,uint64_t magic){
'''
    post=r'''
}
int main(){
 Proc p{79,"bluetoothd",true};
 for(int bad=0;bad<8;++bad){Proc q=p;uint32_t code=0xfe700020;uint64_t ver=page,status=1,magic=0x4843;
  switch(bad){case 0:code++;break;case 1:status=2;break;case 2:ver=0;break;case 3:ver++;break;case 4:ver=UINT64_C(0xfffffff000000000);break;case 5:magic++;break;case 6:q.name="other";break;case 7:q.hash=false;break;}
  invoke(&q,code,status,0,ver,magic);assert(calls==0&&copies==0);
 }
 invoke(nullptr,0xfe700020,1,0,page,0x4843);assert(calls==0&&copies==0);
 for(int i=0;i<20;++i){copy_error=i&1?14:0;invoke(&p,0xfe700020,1,i&1?page:0,page,0x4843);assert(calls==i+1);assert(result_seen==(i&1?(uint32_t)page:0));assert(copies==5*(i<16?i+1:16));}
 puts("PASS exact marker guards, bounded reads, faults and log limit");
}
'''
    f=a.output/'marker.cpp';f.write_text(pre+marker+post);exe=a.output/'marker'
    build=subprocess.run([a.cxx,'-std=c++17','-O1','-g','-fsanitize=address,undefined',str(f),'-o',str(exe)],capture_output=True);(a.output/'compile.log').write_bytes(build.stdout+build.stderr);build.check_returncode()
    run=subprocess.run([str(exe)],capture_output=True);(a.output/'run.log').write_bytes(run.stdout+run.stderr);run.check_returncode()
    result={'passed':True,'actual_marker_sha256':hashlib.sha256(marker.encode()).hexdigest(),'asan_ubsan':True,'copyin_regions':5,'copyin_errors_preserved':True,'log_limit_not_state_limit':True}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
