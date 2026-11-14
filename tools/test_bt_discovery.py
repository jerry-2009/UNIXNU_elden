"""Exercise the actual discovery parser without retaining device addresses."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    body=(ROOT/'drivers/EldenBluetooth/Discovery.inc').read_text()
    pre='''#include <cstdint>
#include <cassert>
#include <cstring>
#include <vector>
#include <cstdio>
enum {PbLinkUp=2,PbH4Evt=4,PbEvtCommandComplete=14,PbEvtCommandStatus=15};
struct PbBridge {int link;};static int depth;
void lock(PbBridge*){assert(!depth);depth++;}void unlock(PbBridge*){assert(depth==1);depth--;}
'''
    test=r'''
int main(){
 PbBridge b{PbLinkUp},other{PbLinkUp};uint32_t out[20];discovery_init(&b);
 assert(!elden_bt_discovery_read(&b,out,20)&&out[10]==UINT32_MAX);assert(elden_bt_discovery_read(&other,out,20)==-19);
 for(unsigned op: {0x0401u,0x200bu,0x200cu,0x2041u,0x2042u})discovery_tx(&b,(uint16_t)op);
 discovery_tx(&other,0x2041);discovery_tx(&b,0xfc00);for(int i=0;i<5;i++)assert(discovery_values[i]==1);
 uint8_t cc[]={4,14,4,1,0x41,0x20,0};discovery_up(&b,cc,sizeof(cc));assert(discovery_values[8]==1&&discovery_values[13]==0);
 uint8_t cs[]={4,15,4,12,1,0x42,0x20};discovery_up(&b,cs,sizeof(cs));assert(discovery_values[9]==1&&discovery_values[14]==12);
 uint8_t credit[]={4,14,3,1,0,0};discovery_up(&b,credit,sizeof(credit));assert(discovery_values[19]==0);
 for(int extended=0;extended<2;extended++){
  unsigned header=extended?24:10;std::vector<uint8_t> f(5+2*(header+3));f[0]=4;f[1]=0x3e;f[2]=(uint8_t)(f.size()-3);f[3]=extended?0x0d:2;f[4]=2;
  for(int n=0;n<2;n++){unsigned pos=5+n*(header+3);f[pos+(extended?23:8)]=3;if(extended&&n)f[pos]=0x20;}
  unsigned index=extended?17:16,previous=discovery_values[index];discovery_up(&b,f.data(),(uint32_t)f.size());assert(discovery_values[index]==previous+2);
  for(size_t size=0;size<f.size();size++){auto truncated=f;if(size>=3)truncated[2]=(uint8_t)(size-3);auto prior=discovery_values[index];discovery_up(&b,truncated.data(),(uint32_t)size);assert(discovery_values[index]==prior);}
  auto extra=f;extra.push_back(0);extra[2]++;auto prior=discovery_values[index];discovery_up(&b,extra.data(),(uint32_t)extra.size());assert(discovery_values[index]==prior);
  auto bad=f;bad[5+(extended?23:8)]=255;discovery_up(&b,bad.data(),(uint32_t)bad.size());assert(discovery_values[index]==prior);
 }
 assert(discovery_values[18]==1);unsigned old=discovery_values[17];b.link=0;uint8_t empty[]={4,0x3e,2,0x0d,0};discovery_up(&b,empty,sizeof(empty));assert(discovery_values[17]==old);
 discovery_values[0]=UINT32_MAX;discovery_add(0,1);assert(discovery_values[0]==UINT32_MAX);discovery_values[1]=UINT32_MAX-1;discovery_add(1,2);assert(discovery_values[1]==UINT32_MAX);
 assert(!elden_bt_discovery_read(&b,out,20));assert(elden_bt_discovery_read(&b,out,19)==-22);assert(!depth);puts("PASS actual discovery parser, malformed packets, saturation and snapshot");
}
'''
    f=a.output/'discovery.cpp';f.write_text(pre+body+test);exe=a.output/'discovery'
    subprocess.run([a.cxx,'-std=c++17','-O1','-g','-fsanitize=address,undefined',str(f),'-o',str(exe)],check=True)
    result=subprocess.run([str(exe)],capture_output=True);(a.output/'run.log').write_bytes(result.stdout+result.stderr);result.check_returncode()
    (a.output/'result.json').write_text(json.dumps({'passed':True,'actual_body_sha256':hashlib.sha256(body.encode()).hexdigest(),'asan_ubsan':True,'transport_integration_not_modeled':True},indent=2)+'\n');print('PASS actual discovery parser')
if __name__=='__main__':main()
