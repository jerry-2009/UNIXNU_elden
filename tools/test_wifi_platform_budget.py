"""Test real old/new MHI register-poll bodies with modeled registers and clock."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from PlatformShutdownPatch import patch
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['runtime-build','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    original=a.runtime_build/'component/out/mhi-src/main.c';data=original.read_bytes()
    def body(text):
        start=text.index('int __must_check mhi_poll_reg_field(');return text[start:text.index('\n}',start)+2]
    old=body(data.decode());new=body(patch('main.c',data).decode())
    fixture='''#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <assert.h>
typedef uint32_t u32;typedef uint64_t u64;
#define __must_check
#define __iomem
struct mhi_controller {int unused;};
static u64 clock_us,deadline,clear_at;static unsigned reads,sleeps;static int read_error,stuck_clock;
static u64 lx_now_ms(void){return clock_us/1000;}
static u64 elden_wifi_platform_deadline_ms(void){return deadline;}
static void fsleep(u32 us){sleeps++;if(!stuck_clock)clock_us+=us;}
static void lx_log(int level,const char *format,...){(void)level;(void)format;}
static int mhi_read_reg_field(struct mhi_controller *c,void *base,u32 offset,u32 mask,u32 *out){
 (void)c;(void)base;(void)offset;(void)mask;reads++;if(read_error)return read_error;*out=clock_us<clear_at;return 0;
}
static void reset(void){clock_us=deadline=reads=sleeps=0;clear_at=UINT64_MAX;read_error=stuck_clock=0;}
'''+old.replace('mhi_poll_reg_field','original_poll',1)+'\n'+new+'''
int main(void){
 reset();clear_at=2500000;assert(!original_poll(0,0,0x38,2,0,25000,90000));u64 t=clock_us;unsigned r=reads,s=sleeps;
 reset();clear_at=2500000;assert(!mhi_poll_reg_field(0,0,0x38,2,0,25000,90000));assert(clock_us==t&&reads==r&&sleeps==s);
 reset();deadline=2000;clear_at=100000;assert(!mhi_poll_reg_field(0,0,0x38,2,0,25000,90000)&&clock_us==100000);
 reset();deadline=2000;assert(mhi_poll_reg_field(0,0,0x38,2,0,25000,90000)==-ETIMEDOUT&&clock_us==2000000);
 r=reads;s=sleeps;assert(mhi_poll_reg_field(0,0,0x48,1,0,25000,90000)==-ETIMEDOUT&&reads==r+1&&sleeps==s);
 clear_at=0;r=reads;assert(!mhi_poll_reg_field(0,0,0x48,1,0,25000,90000)&&reads==r+1&&sleeps==s);
 reset();deadline=2000;read_error=-EIO;assert(mhi_poll_reg_field(0,0,0x38,2,0,25000,90000)==-EIO&&!sleeps);
 reset();deadline=2000;stuck_clock=1;assert(mhi_poll_reg_field(0,0,0x38,2,0,25000,90000)==-ETIMEDOUT&&sleeps<=81);
 reset();deadline=2000;assert(mhi_poll_reg_field(0,0,0x38,2,0,0,90000)==-EINVAL&&!reads);
 puts("PASS8 poll checks: original startup timing, observed clear/error, aggregate deadline, final fresh read and stalled-clock bound");
}
'''
    (out/'test.c').write_text(fixture)
    for name,cmd in [('compile',['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'test.c'),'-o',str(out/'test')]),('run',[str(out/'test')])]:
        r=subprocess.run(cmd,capture_output=True,timeout=60);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    result={'passed':True,'asan_ubsan':True,'result':r.stdout.decode().strip(),'hardware':False,'clock_and_mmio_modeled':True,'original_source_sha256':hashlib.sha256(data).hexdigest(),'source_inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [ROOT/'drivers/EldenWifi/peach/PlatformShutdownPatch.py',Path(__file__)]}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
