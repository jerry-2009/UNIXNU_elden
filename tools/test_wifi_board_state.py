"""Exercise existing WCN pin/rail reads, stale ownership and I/O failure retention."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('cc', 'core-source', 'wmi-source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT / 'drivers/EldenWifi/peach'))
    from BoardStatePatch import patch
    for name, path in [('core.c', args.core_source), ('wmi.c', args.wmi_source)]:
        (out / name).write_bytes(patch(name, path.read_bytes()))
    code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <limits.h>
#include <cstdint>
enum {EldenWcnRailCount=6,EldenWcnWlan=1};
typedef unsigned EldenWcnRail;
struct EldenWcnRailState {uint16_t mv;uint8_t status,enable,mode;};
static unsigned reads,rail_calls,checks,logs,gate,leaves;
static int fail_read,fail_rail,enter_error,check_error;static bool interrupt;
struct Region {uintptr_t va=1;uint32_t value[3]={};uint32_t read(unsigned off){assert(off<=8&&!(off&3));if((int)reads++==fail_read)return UINT32_MAX;return value[off/4];}};
struct Context {Region wlan,sideband_maps[3];struct {bool ready=true;}sideband;struct {unsigned x;}shared;struct {uint16_t target[6];}power;};
static Context *active;static uint64_t wlan_epoch;static unsigned platform_stopping;
static bool ml_at_interrupt_context(){return interrupt;}
static int platform_enter(){if(enter_error)return enter_error;assert(!gate);gate=1;return 0;}
static void platform_leave(){assert(gate);gate=0;leaves++;}
static int elden_wcn_shared_check(void *,unsigned,uint64_t){checks++;return check_error;}
static int rail_read(void *,EldenWcnRail rail,EldenWcnRailState *state){assert(gate&&rail<6);if((int)rail_calls++==fail_rail)return -5;*state={876,0x87,0x80,7};return 0;}
static int parents(void *,uint32_t *main,uint32_t *even){assert(gate);*main=600000000;*even=300000000;return 0;}
static void log(const char *format,...){char b[320];va_list args;va_start(args,format);int n=vsnprintf(b,sizeof b,format,args);va_end(args);assert(n>0&&(unsigned)n<sizeof b);logs++;}
@HELPER@
static Context c;
static void reset(){reads=rail_calls=checks=logs=gate=leaves=0;fail_read=fail_rail=-1;enter_error=check_error=0;interrupt=false;platform_stopping=0;wlan_epoch=1;c=Context{};active=&c;}
int main(){unsigned cases=0;
 for(unsigned stage: {12U,9U,90U}){reset();assert(!board_state(stage)&&reads==12&&rail_calls==6&&checks==2&&logs==11&&leaves==1&&!gate);cases++;}
 for(unsigned fault=0;fault<6;fault++){
  reset();if(fault==0)interrupt=true;else if(fault==1)active=nullptr;else if(fault==2)wlan_epoch=0;else if(fault==3)c.sideband.ready=false;else if(fault==4)platform_stopping=1;else c.sideband_maps[1].va=0;
  assert(board_state(9)==-19&&!reads&&!rail_calls&&!gate);cases++;
 }
 reset();assert(board_state(3)==-22&&!reads);cases++;
 reset();enter_error=-11;assert(board_state(9)==-11&&!reads&&!leaves);cases++;
 reset();check_error=-11;assert(board_state(9)==-11&&!reads&&!rail_calls&&leaves==1);cases++;
 for(unsigned i=0;i<12;i++){reset();fail_read=i;assert(board_state(9)==-5&&reads==i+1&&!rail_calls&&leaves==1&&!gate);cases++;}
 for(unsigned i=0;i<6;i++){reset();fail_rail=i;assert(board_state(9)==-5&&reads==12&&rail_calls==i+1&&leaves==1&&!gate);cases++;}
 printf("PASS %u existing WCN state cases; no control writes, ownership and read errors preserved\n",cases);
}
'''.replace('@HELPER@', (ROOT / 'drivers/EldenWifi/BoardState.inc').read_text())
    code = code.replace('#include <cstdint>', '#include <cstdint>\n#include <initializer_list>')
    src = out / 'test.cpp'
    src.write_text(code)
    command = [str(args.cc), '-std=gnu++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', str(src), '-o', str(out / 'test')]
    if sys.platform == 'darwin':
        command[1:1] = ['-isysroot', subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()]
    for name, cmd in [('compile', command), ('run', [str(out / 'test')])]:
        r = subprocess.run(cmd, capture_output=True)
        (out / (name + '.log')).write_bytes(r.stdout + r.stderr)
        r.check_returncode()
    own = ['tools/test_wifi_board_state.py', 'drivers/EldenWifi/BoardState.inc', 'drivers/EldenWifi/SidebandSource.py', 'drivers/EldenWifi/peach/BoardStatePatch.py']
    proof = dict(passed=True, actual_helper=True, asan_ubsan=True, spmi_mmio_modeled=True, no_control_writes=True, hardware_tested=False, summary=(out / 'run.log').read_text().strip(), source_inputs={n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in own})
    (out / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
