"""Execute the frozen and corrected policies with actual verification helpers."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenPmicGlink'))
from VerificationSource import policy,client,CLIENT_PATH

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    include=ROOT/'drivers/EldenPmicGlink';(out/'policy-fixed.c').write_bytes(policy());(out/'PmicClient.cpp').write_bytes(client())
    def observation(source):
        start=source.index('                if(policyEnable==1&&')
        end=source.index('                clock_interval_to_deadline(3000,kMillisecondScale,&nextRefresh);',start)
        return source[start:end]
    old_observe=observation(CLIENT_PATH.read_text())
    new_observe=observation(client().decode())
    fixture=r'''
#include "ChargeVerification.h"
#include "ChargePoll.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void put(unsigned char*p,unsigned v){for(unsigned i=0;i<4;i++)p[i]=(unsigned char)(v>>(8*i));}
static void reply(EldenChargePolicy*s,unsigned value){unsigned char p[24]={0};put(p,32778);put(p+4,1);put(p+8,s->last_opcode);put(p+12,s->last_property);put(p+16,value);assert(elden_charge_policy_receive(s,p,24)==1);}
static void setup(EldenChargePolicy*s){unsigned char p[24];elden_charge_policy_init(s);elden_charge_policy_link(s,true);assert(elden_charge_policy_next(s,true,p)==24);reply(s,95100);assert(elden_charge_policy_next(s,true,p)==24);reply(s,0);elden_charge_policy_observe(s,10,5000,1);}
static void waiting(EldenChargePolicy*s,int window){unsigned char p[24];setup(s);assert(!elden_charge_policy_select(s,window?EldenChargeLimit80:EldenChargeBypass));assert(elden_charge_policy_next(s,true,p)==24);reply(s,0);if(window){assert(elden_charge_policy_next(s,true,p)==24);reply(s,176080);}assert(elden_charge_verify_waiting(s));}
static void actual_native_observe(EldenChargePolicy *s,uint64_t ageMs,unsigned snapshot_epoch){
 EldenChargePolicy chargePolicy=*s;EldenChargePoll poll={0};unsigned policyEnable=1;
 poll.committed.epoch=snapshot_epoch;poll.committed.cycle=12;poll.committed.valid=(UINT64_C(1)<<EldenChargeFieldCount)-1;
 poll.committed.value[EldenChargeCapacity].raw=5000;poll.committed.value[EldenChargeEnabled].raw=0;
@OBSERVE@
 *s=chargePolicy;
}
int main(){
 EldenChargePolicy s;unsigned char p[24];unsigned cases=0;
 for(int window=0;window<2;window++){
  waiting(&s,window);unsigned sequence=s.applied_sequence;uint64_t deadline=0;
  elden_charge_verify_tick(&s,100,false,&deadline);assert(deadline==30100);elden_charge_verify_tick(&s,30099,false,&deadline);assert(elden_charge_verify_waiting(&s));
  elden_charge_verify_tick(&s,30100,false,&deadline);
#ifdef ORIGINAL
  assert(elden_charge_verify_waiting(&s)&&s.timeouts==0); /* old actual timeout ignores an ACKed setting */
#else
  assert(s.phase==EldenPolicyFailed&&s.timeouts==1&&s.errors==1&&s.applied_sequence==sequence);assert(!elden_charge_policy_next(&s,true,p));assert(!elden_charge_verify_available(&s,true));
#endif
  cases++;
 }
 waiting(&s,0);actual_native_observe(&s,10000,s.epoch);
#ifdef ORIGINAL
 assert(s.applied_mode==EldenChargeBypass); /* native caller formerly accepted already-stale full cycles */
#else
 assert(s.phase==EldenPolicyWaitEnable&&s.applied_sequence==0);
 actual_native_observe(&s,0,s.epoch+1);assert(s.phase==EldenPolicyWaitEnable);
 actual_native_observe(&s,9999,s.epoch);assert(s.applied_mode==EldenChargeBypass);
#endif
#ifndef ORIGINAL
 for(int window=0;window<2;window++){
  waiting(&s,window);uint64_t deadline=0;elden_charge_verify_tick(&s,200,false,&deadline);
  if(elden_charge_verify_fresh(10000,1,1,true,true))elden_charge_policy_observe(&s,12,5000,0);
  assert(elden_charge_verify_waiting(&s)&&s.applied_sequence==0);assert(!elden_charge_verify_available(&s,false));
  elden_charge_verify_tick(&s,201,true,&deadline);assert(s.phase==EldenPolicyFailed&&!deadline);
  cases++;
 }
 waiting(&s,0);uint64_t deadline=0;elden_charge_verify_tick(&s,1,false,&deadline);
 assert(elden_charge_verify_fresh(9999,1,1,true,true));elden_charge_policy_observe(&s,12,5000,0);assert(s.phase==EldenPolicyReady&&s.applied_mode==EldenChargeBypass);
 elden_charge_verify_tick(&s,999999,false,&deadline);assert(s.phase==EldenPolicyReady&&!deadline&&s.timeouts==0);
 waiting(&s,1);elden_charge_verify_tick(&s,5,false,&deadline);elden_charge_policy_link(&s,false);elden_charge_verify_tick(&s,60000,true,&deadline);assert(s.phase==EldenPolicyOff&&!deadline&&s.timeouts==0);
 waiting(&s,0);elden_charge_verify_tick(&s,UINT64_MAX-5,false,&deadline);assert(deadline==UINT64_MAX);elden_charge_verify_tick(&s,UINT64_MAX,false,&deadline);assert(s.phase==EldenPolicyFailed);
 assert(!elden_charge_verify_fresh(1,1,2,true,true));assert(!elden_charge_verify_fresh(1,0,0,true,true));assert(!elden_charge_verify_fresh(1,1,1,false,true));assert(!elden_charge_verify_fresh(1,1,1,true,false));
 setup(&s);assert(elden_charge_verify_available(&s,true));assert(!elden_charge_verify_available(&s,false));
 cases+=8;
#endif
 printf("PASS %u policy verification groups\n",cases);
}
'''
    results=[]
    for name,source,flags in [('original',include/'ChargePolicy.c',['-DORIGINAL']),('fixed',out/'policy-fixed.c',[])]:
        test=out/(name+'-test.c');test.write_text(fixture.replace('@OBSERVE@',old_observe if name=='original' else new_observe));exe=out/name
        subprocess.run([a.cc,'-std=c11','-O1','-g','-fsanitize=address,undefined','-I',str(include),*flags,str(test),str(source),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)],capture_output=True);(out/(name+'.log')).write_bytes(run.stdout+run.stderr);run.check_returncode();results.append(run.stdout.decode().strip())
    exe=out/'existing-regression';subprocess.run([a.cc,'-std=c11','-O1','-g','-fsanitize=address,undefined','-I',str(include),str(include/'TestChargePolicy.c'),str(out/'policy-fixed.c'),'-o',str(exe)],check=True)
    run=subprocess.run([str(exe)],capture_output=True);(out/'existing-regression.log').write_bytes(run.stdout+run.stderr);run.check_returncode();results.append(run.stdout.decode().strip())
    (out/'result.json').write_text(json.dumps({'passed':True,'old_wait_timeout_gap_reproduced':True,'asan_ubsan':True,'results':results,'policy_sha256':hashlib.sha256(policy()).hexdigest(),'client_sha256':hashlib.sha256(client()).hexdigest(),'hardware_tested':False},indent=2)+'\n');print(json.dumps({'passed':True,'results':results}))
if __name__=='__main__':main()
