"""Run the actual OEM wake helper with modeled MHI/MMIO/error interleavings."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', type=Path, required=True)
    parser.add_argument('--pci-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / 'drivers/EldenWifi/peach'))
    from UmacWakePatch import patch
    source = args.pci_source.read_bytes()
    derived = patch(source)
    try:
        patch(source + b'\n')
    except ValueError:
        pass
    else:
        raise AssertionError('Unpinned PCI source accepted')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'pci.c').write_bytes(derived)
    helper = ROOT / 'drivers/EldenWifi/UmacWake.inc'
    code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
#include <errno.h>
#include <string.h>
typedef uint32_t u32;
struct mhi_device { unsigned refs; };
struct mhi_controller { struct mhi_device *mhi_dev; };
struct ath12k_pci { struct mhi_controller *mhi_ctrl; };
struct ath12k_base { unsigned hw_rev; struct ath12k_pci *pci; void *mem; size_t mem_len; };
#define ATH12K_HW_PEACH_HW20 17
#define WINDOW_START 0x80000U
#define WINDOW_RANGE_MASK 0x7ffffU
static unsigned requested, get_calls, put_calls, read_calls, writes, delays, elapsed;
static int failure;
static u32 baseline, status;
static unsigned ready_at;
static u32 addresses[4], values[4];
static struct ath12k_pci *ath12k_pci_priv(struct ath12k_base *ab) { return ab->pci; }
int elden_wifi_umac_hold_requested(void) { return requested; }
static int mhi_device_get_sync(struct mhi_device *d) {
    get_calls++; if (failure) return failure; d->refs++; return 0;
}
static void mhi_device_put(struct mhi_device *d) { assert(d->refs); d->refs--; put_calls++; }
static u32 ath12k_pci_read32(struct ath12k_base *ab, u32 offset) {
    assert(ab->pci->mhi_ctrl->mhi_dev->refs);
    assert(offset == 0x01e04040U); read_calls++;
    if (!writes) return baseline;
    return read_calls - 1 >= ready_at ? status : baseline;
}
static void ath12k_pci_write32(struct ath12k_base *ab, u32 offset, u32 value) {
    assert(ab->pci->mhi_ctrl->mhi_dev->refs);
    assert(writes < 4 && offset == 0x3004U && value <= 1);
    addresses[writes] = offset; values[writes++] = value;
}
static void udelay(unsigned us) { assert(us == 5000); delays++; elapsed += us; }
#define ath12k_warn(...) ((void)0)
@HELPER@
static void clear(void) {
    assert(!elden_umac_device && !elden_umac_owner);
    requested=1; get_calls=put_calls=read_calls=writes=delays=elapsed=0;
    failure=0; baseline=1; status=2; ready_at=1;
    memset(addresses,0,sizeof(addresses)); memset(values,0,sizeof(values));
}
int main(void) {
    unsigned cases=0;
    struct mhi_device d={0},d2={0};
    struct mhi_controller c={&d},c2={&d2};
    struct ath12k_pci pci={&c},pci2={&c2};
    struct ath12k_base ab={17,&pci,(void *)1,0x100000},other={17,&pci2,(void *)1,0x100000};
    clear(); requested=0; assert(!elden_umac_wake_get(NULL) && !get_calls && !writes); cases++;
    clear(); assert(elden_umac_wake_get(NULL)==-ENODEV); cases++;
    ab.hw_rev=3; assert(elden_umac_wake_get(&ab)==-ENODEV); ab.hw_rev=17; cases++;
    ab.mem=NULL; assert(elden_umac_wake_get(&ab)==-ENODEV); ab.mem=(void *)1; cases++;
    ab.mem_len=0x84043; assert(elden_umac_wake_get(&ab)==-ENODEV); ab.mem_len=0x100000; cases++;
    ab.pci=NULL; assert(elden_umac_wake_get(&ab)==-ENODEV); ab.pci=&pci; cases++;
    pci.mhi_ctrl=NULL; assert(elden_umac_wake_get(&ab)==-ENODEV); pci.mhi_ctrl=&c; cases++;
    c.mhi_dev=NULL; assert(elden_umac_wake_get(&ab)==-ENODEV); c.mhi_dev=&d; cases++;
    assert(!get_calls && !writes && !put_calls);
    for (int i=0;i<3;i++) {
        clear(); failure=-(5+i); assert(elden_umac_wake_get(&ab)==failure);
        elden_umac_wake_put(&ab); assert(!d.refs && !writes && !put_calls && !read_calls); cases++;
    }
    for (unsigned i=1;i<=11;i++) {
        clear(); ready_at=i;
        assert(!elden_umac_wake_get(&ab) && d.refs==1 && writes==1 && values[0]==1);
        assert(read_calls==i+1 && delays==i-1 && elapsed<=50000);
        unsigned calls=get_calls; assert(!elden_umac_wake_get(&ab) && get_calls==calls && d.refs==1);
        assert(elden_umac_wake_get(&other)==-EBUSY && !d2.refs);
        elden_umac_wake_put(&other); assert(!put_calls && d.refs==1);
        elden_umac_wake_put(&ab); assert(put_calls==1 && !d.refs && writes==2 && values[1]==0);
        elden_umac_wake_put(&ab); assert(put_calls==1 && writes==2); cases++;
    }
    for (unsigned i=0;i<4;i++) {
        clear(); baseline=i==0?0:i==1?1:i==2?3:0xffffffffU; ready_at=100;
        int wanted=baseline==0xffffffffU?-EIO:-ETIMEDOUT;
        assert(elden_umac_wake_get(&ab)==wanted && !d.refs && put_calls==1);
        assert(writes==2 && values[0]==1 && values[1]==0 && !elden_umac_device);
        assert(elapsed<=50000 && read_calls<=12);
        elden_umac_wake_put(&ab); assert(put_calls==1); cases++;
    }
    clear(); ready_at=3; status=0xffffffffU;
    assert(elden_umac_wake_get(&ab)==-EIO && !d.refs && put_calls==1 && writes==2 && delays==2); cases++;
    for (unsigned i=0;i<10;i++) {
        clear(); baseline=2;
        assert(!elden_umac_wake_get(&ab) && !delays); elden_umac_wake_put(&ab);
        assert(!d.refs && values[1]==0); cases++;
    }
    printf("PASS %u actual UMAC wake scenarios; MHI/MMIO modeled; 50ms polling bound and exact cleanup\n",cases);
}
'''.replace('@HELPER@', helper.read_text())
    test = out / 'test.c'
    test.write_text(code)
    command = [str(args.cc), '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
        '-Wno-unused-but-set-variable', '-fsanitize=address,undefined',
        '-fno-sanitize-recover=all', str(test), '-o', str(out / 'test')]
    if sys.platform == 'darwin':
        command[1:1] = ['-isysroot', subprocess.check_output(
            ['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()]
    for name, call in [('compile', command), ('run', [str(out / 'test')])]:
        result = subprocess.run(call, capture_output=True)
        (out / (name + '.log')).write_bytes(result.stdout + result.stderr)
        result.check_returncode()
    proof = dict(passed=True, actual_helper_executed=True, exact_pci_patch_reversible=True,
        mhi_mmio_clock_modeled=True, hardware_tested=False, polling_bound_ms=50,
        summary=(out / 'run.log').read_text().strip(), sanitizers=['ASan', 'UBSan'],
        original_pci_sha256=hashlib.sha256(source).hexdigest(),
        derived_pci_sha256=hashlib.sha256(derived).hexdigest(),
        source_inputs={name:hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
            ['tools/test_wifi_umac_wake.py', 'drivers/EldenWifi/UmacWake.inc',
             'drivers/EldenWifi/peach/UmacWakePatch.py']})
    (out / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
