"""Validate battery menu semantics; optionally execute the exact XNU parser.

Use a reconstructed pexpert/gen/bootargs.c and a new explicit scratch folder.
Nothing accesses the tablet or alters a frozen profile.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
import tomllib
from battery_boot import BATTERY, COMPACT, arguments, template, verify
from fbwc_boot import template as baseline

class MenuTests(unittest.TestCase):
    def test_original_menus_and_option_values(self):
        for fbwc, size in ((False, 1015), (True, 1020)):
            old = baseline(fbwc)
            new = template(old)
            self.assertEqual(verify(old, new)['boot_args_bytes'], size)
            a, b = map(tomllib.loads, (old, new))
            self.assertEqual(a['entry'][1:], b['entry'][1:])
            self.assertEqual(arguments(b['entry'][0]['args']), arguments(a['entry'][0]['args']) | BATTERY)
            self.assertIn('amfi_get_out_of_my_way=1', new)
            self.assertIn('security-mode-change-enable=1', new)

    def test_reject_malformed_or_unintended_changes(self):
        old = baseline(True)
        for new in (
            template(old).replace('elden-battery-current=-1', 'elden-battery-current=1'),
            template(old).replace('elden-thermal=2', 'elden-thermal=3'),
            template(old).replace('timeout = 8', 'timeout = 0'),
            template(old).replace('cpus=8', 'cpus=8 cpus=8'),
            template(old).replace('fbwc ', ''),
            template(old).replace('native-ufs-diagnostics=1', 'native-ufs-diagnostics=0'),
        ):
            with self.assertRaises(ValueError): verify(old, new)
        with self.assertRaises(ValueError): template(template(old))
        with self.assertRaises(ValueError): template(old.replace('elden-ui=1', 'elden-ui=2'))
        with self.assertRaises(ValueError): template(old.replace('smp-hold=240', 'smp-hold=' + '1' * 100))

def actual_parser(source, work, cc, extra_menus=()):
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != '814d2f779300bfbf7ef13c8c830ae0f98ada271586518b808d43a019a7e7db3a':
        raise ValueError('Not the parser used by the frozen XNU build')
    work.mkdir(parents=True, exist_ok=False)
    headers = work / 'pexpert'
    headers.mkdir()
    (headers / 'pexpert.h').write_text('''#include <stdint.h>
#include <stdbool.h>
#include <string.h>
typedef int boolean_t;
#define TRUE 1
#define FALSE 0
char *PE_boot_args(void);
''')
    (headers / 'device_tree.h').write_text('''typedef void *DTEntry;
#define kSuccess 0
static int SecureDTLookupEntry(void *a,const char *b,DTEntry *c){return -1;}
static int SecureDTGetProperty(DTEntry a,const char *b,const void **c,unsigned *d){return -1;}
''')
    c = ['#include <stdio.h>', '#include <stdlib.h>', '#include <stdint.h>',
         'static char *active_args;', 'char *PE_boot_args(void){return active_args;}',
         'int IODTGetDefault(const char *a,void *b,unsigned c){return 0;}',
         '#include ' + json.dumps(source.resolve().as_posix()),
         'static unsigned checks;',
         'static void check(const char *key,long long expected,unsigned size){',
         'uint64_t value=0;',
         'if(!PE_parse_boot_argn(key,&value,size) || (size==4?(int32_t)value:(int64_t)value)!=expected){',
         'fprintf(stderr,"parser mismatch %s/%u\\n",key,size);exit(1);}++checks;}',
         'int main(void){']
    for fbwc in (False, True):
        before = baseline(fbwc)
        for is_new, menu in ((False, before), (True, template(before))):
            args = tomllib.loads(menu)['entry'][0]['args'].replace('@SESSION@', '0123456789abcdef')
            c.append('active_args=' + json.dumps(args) + ';')
            for key in sorted(COMPACT):
                c.append(f'check({json.dumps(key)},1,4);check({json.dumps(key)},1,8);')
                c.append('{char s[16]={0};if(!PE_parse_boot_arg_str(' + json.dumps(key) + ',s,sizeof(s))||strcmp(s,"1"))return 2;++checks;}')
            if is_new:
                for key, value in BATTERY.items():
                    c.append(f'check({json.dumps(key)},{value},4);check({json.dumps(key)},{value},8);')
    for args, values in extra_menus:
        c.append('active_args=' + json.dumps(args) + ';')
        for key,value in values.items():
            c.append(f'check({json.dumps(key)},{value},4);check({json.dumps(key)},{value},8);')
    c += ['printf("XNU parser: %u checks passed\\n",checks);return 0;}']
    harness = work / 'parser-test.c'
    harness.write_text('\n'.join(c) + '\n')
    binary = work / 'parser-test'
    command = [cc, '-x', 'c', '-std=c11', '-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie', '-I', str(work), str(harness), '-o', str(binary)]
    subprocess.run(command, check=True)
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    report = {'parser_sha256': digest, 'command': command, 'stdout': result.stdout,
              'device_operations': False, 'new_menu_bytes': verify(baseline(True), template(baseline(True)))['boot_args_bytes']}
    (work / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(result.stdout, end='')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parser-source', type=Path)
    p.add_argument('--work', type=Path)
    p.add_argument('--cc', default='gcc')
    a = p.parse_args()
    if bool(a.parser_source) != bool(a.work): p.error('Supply both --parser-source and --work')
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MenuTests)
    if not unittest.TextTestRunner().run(suite).wasSuccessful(): raise SystemExit(1)
    if a.parser_source: actual_parser(a.parser_source, a.work, a.cc)
