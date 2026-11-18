"""Compare the actual independently compiled KeyStore gate across capacity change."""
from pathlib import Path
import argparse,json,subprocess,re
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['old-source','new-source','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    def function(path,name):
        text=path.read_text();match=re.search(r'extern "C" bool native_aks_state_enabled\(void\)\{.*?\n\}',text,re.S);assert match
        return match[0].replace('native_aks_state_enabled',name)
    source='''#include <stdint.h>
#include <assert.h>
#include <stdio.h>
static unsigned stateRequested,admitted,native_data_persist_state;
static int native_owner_data_status,native_owner_data_readonly;
static uint64_t native_owner_data_seed_size;
'''+function(a.old_source,'old_gate')+'\n'+function(a.new_source,'new_gate')+'''
int main(){unsigned cases=0;uint64_t sizes[]={0,536870912ULL,2147483648ULL,3221225472ULL};
for(stateRequested=0;stateRequested<4;stateRequested++)for(admitted=0;admitted<2;admitted++)
for(native_owner_data_status=-1;native_owner_data_status<=1;native_owner_data_status++)
for(native_owner_data_readonly=0;native_owner_data_readonly<2;native_owner_data_readonly++)
for(native_data_persist_state=0;native_data_persist_state<2;native_data_persist_state++)for(auto size:sizes){
 native_owner_data_seed_size=size;bool after=new_gate();
 native_owner_data_seed_size=size==2147483648ULL?536870912ULL:size==536870912ULL?2147483648ULL:size;
 assert(after==old_gate());cases++;
}
stateRequested=2;admitted=1;native_owner_data_status=0;native_owner_data_readonly=0;native_data_persist_state=0;
native_owner_data_seed_size=2147483648ULL;assert(new_gate()&&!old_gate());
native_owner_data_seed_size=536870912ULL;assert(old_gate()&&!new_gate());
printf("PASS %u actual KeyStore gate equivalence cases; only admitted capacity changes\\n",cases);
}
'''
    (out/'test.cpp').write_text(source)
    for name,cmd in [('compile',['clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'test.cpp'),'-o',str(out/'test')]),('run',[str(out/'test')])]:
        r=subprocess.run(cmd,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    report={'passed':True,'actual_functions':True,'only_capacity_predicate_changes':True,'summary':(out/'run.log').read_text().strip(),'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['summary'])
if __name__=='__main__':main()
