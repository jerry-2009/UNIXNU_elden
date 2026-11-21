"""Qualify the2GiB seed and actual sparse helpers without creating a boot image."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from verify_v91_assets import verify_packed_seed
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['seed','report','legacy-seed','legacy-report','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    legacy=verify_packed_seed(a.legacy_seed,a.legacy_report)
    try:verify_packed_seed(a.seed,a.report)
    except ValueError as e:assert str(e)=='Invalid packed Data header'
    else:raise AssertionError('Legacy verifier accepted expanded capacity implicitly')
    expanded=verify_packed_seed(a.seed,a.report,expected_bytes=2147483648)
    header=ROOT/'profiles/v91/native-build/extra/5ab6516488b7/SparseDisk.h'
    code=r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <vector>
#include "SparseDisk.h"
struct Ops {
 bool fail=false;std::vector<uint8_t> input,output;
 uint8_t *allocate(){return fail?nullptr:(uint8_t*)calloc(1,4096);}
 uint64_t read(uint64_t off,void *p,uint64_t n){assert(off+n<=input.size());memcpy(p,input.data()+off,n);return n;}
 uint64_t copy(uint64_t off,const void *p,uint64_t n){assert(off+n<=output.size());memcpy(output.data()+off,p,n);return n;}
};
int main(int argc,char **argv){
 assert(argc==2);std::ifstream f(argv[1],std::ios::binary);assert(f);std::vector<uint8_t> b((std::istreambuf_iterator<char>(f)),{});
 uint64_t logical=0;assert(ramPackedLayout(b.data(),b.size(),&logical)&&logical==0x80000000ULL);
 std::vector<uint8_t*> pages(logical/4096,nullptr);RamSparseDisk disk={pages.data(),logical,0};Ops ops;
 assert(ramSparseImport(disk,b.data(),b.size(),ops));assert(disk.resident&&disk.resident<logical/8);
 ops.input.assign(64,0xa5);ops.output.assign(64,0);bool noMemory=false;uint64_t off=logical-4097;
 assert(ramSparseIO(disk,true,off,64,ops,noMemory)==64&&!noMemory);
 assert(ramSparseIO(disk,false,off,64,ops,noMemory)==64&&!noMemory&&ops.input==ops.output);
 assert(!ramSparseIO(disk,true,logical-1,2,ops,noMemory));
 uint64_t zero=pages.size()-1;while(pages[zero]){assert(zero);zero--;}
 ops.output.assign(64,0xff);assert(ramSparseIO(disk,false,zero*4096,64,ops,noMemory)==64&&!noMemory);
 for(auto v:ops.output)assert(!v);ops.fail=true;
 assert(!ramSparseIO(disk,true,zero*4096,64,ops,noMemory)&&noMemory&&!pages[zero]);
 printf("PASS actual sparse import/end-range/cross-page/zero-read/allocation-failure; logical=%llu resident=%llu pointer-table=%llu\n",(unsigned long long)logical,(unsigned long long)disk.resident,(unsigned long long)(pages.size()*sizeof(void*)));
 for(auto p:pages)free(p);
}
'''
    src=out/'test.cpp';src.write_text(code)
    cmd=['clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(header.parent),str(src),'-o',str(out/'test')]
    for name,args in [('compile',cmd),('run',[str(out/'test'),str(a.seed.resolve())])]:
        r=subprocess.run(args,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    report={'passed':True,'legacy_default_preserved':True,'expanded_requires_explicit_capacity':True,'expanded':expanded,'legacy':legacy,
        'sparse_helper_sha256':hashlib.sha256(header.read_bytes()).hexdigest(),'actual_sparse_functions':True,'summary':(out/'run.log').read_text().strip(),'sanitizers':['ASan','UBSan'],'kernel_guard_changes_not_built':True,'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['summary'])
if __name__=='__main__':main()
