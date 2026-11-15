"""Execute the actual bounded power-trial function with cancellation/error I/O."""
from pathlib import Path
import argparse,json,subprocess,sys,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBacklight'))
from PowerTrialSource import source
from BootSource import source as baseline

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    text=source().decode();old=baseline().decode();start='static void powerTrial(Context *c){';end='static void run(unsigned mode){'
    before,body=text.split(start,1);body,after=body.split(end,1);old_before,old_body=old.split(start,1);old_body,old_after=old_body.split(end,1)
    assert before==old_before and after==old_after
    for token in ('if(left<300||left>900)','applyLevel(c,c->original/2)','int restored=restoreOriginal(c);'):
        assert body.count(token)==old_body.count(token)==1
    fixture=r'''
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstring>
struct Context {unsigned original=1597;struct {unsigned level=1597,writes=0;} chip;};
static unsigned remaining=500,restoreConfirmed=1,elapsed,holds,lowers,restores;
static int failedHold,restoreError,finishError;static bool stopped,stopAfterBaseline;
static unsigned remainingFn(){return remaining;}
static unsigned (*elden_recovery_deadline_remaining)()=remainingFn;
static bool stopping(){return stopped;}
static int hold(Context*c,const char*phase,unsigned ms){
 const char*names[]={"settle","baseline","dim","restored"};unsigned expected[]={30000,45000,45000,45000};
 assert(holds<4&&!strcmp(phase,names[holds])&&ms==expected[holds]);
 assert(c->chip.level==(holds==2?c->original/2:c->original));elapsed+=ms;++holds;
 if(holds==2&&stopAfterBaseline)stopped=true;
 return failedHold==(int)holds?-7:0;
}
static int applyLevel(Context*c,unsigned level){assert(level==c->original/2&&level<=c->original);c->chip.level=level;c->chip.writes++;lowers++;return 0;}
static int restoreOriginal(Context*c){restores++;restoreConfirmed=!restoreError;if(!restoreError)c->chip.level=c->original;return restoreError;}
static void report(const char*fmt,...){if(strstr(fmt,"power-finished=")){va_list a;va_start(a,fmt);finishError=va_arg(a,int);va_end(a);}}
@ACTUAL@
static void reset(){remaining=500;restoreConfirmed=1;elapsed=holds=lowers=restores=0;failedHold=restoreError=finishError=0;stopped=stopAfterBaseline=false;}
int main(){
 reset();Context c;powerTrial(&c);assert(elapsed==165000&&holds==4&&lowers==1&&restores==1&&restoreConfirmed&&c.chip.level==1597&&!finishError);
 for(unsigned value: {0u,299u,901u}){reset();remaining=value;c={};powerTrial(&c);assert(!holds&&!lowers&&!restores);}
 for(int fail=1;fail<=4;fail++){reset();failedHold=fail;c={};powerTrial(&c);assert(finishError==-7&&restores==1&&c.chip.level==1597);assert(lowers==(fail>=3?1u:0u));}
 reset();stopAfterBaseline=true;c={};powerTrial(&c);assert(finishError==-7&&!lowers&&restores==1&&c.chip.level==1597);
 reset();restoreError=-5;c={};powerTrial(&c);assert(finishError==-5&&holds==3&&!restoreConfirmed&&c.chip.level==798);
 puts("PASS 10 actual power-trial scenarios; bounded timing and restoration");
}
'''.replace('@ACTUAL@',start+body).replace('#include <cstring>','#include <cstring>\n#include <initializer_list>')
    src=out/'trial.cpp';src.write_text(fixture,encoding='utf-8');exe=out/'trial'
    cmd=[a.cxx,'-std=c++17','-O1','-g','-fsanitize=address,undefined',str(src),'-o',str(exe)]
    r=subprocess.run(cmd,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run([str(exe)],capture_output=True);(out/'run.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    report={'passed':True,'actual_function':True,'asan_ubsan':True,'output':r.stdout.decode().strip(),'derived_source_sha256':hashlib.sha256(source()).hexdigest(),'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
