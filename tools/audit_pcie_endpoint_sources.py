"""Check endpoint fields against fixed Sheng, TB322FC Linux and stock facts."""
import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINUX = '6f97250ead155fc3b980856323e99a4623dae73d'
SHENG = '24aab96163799cb1db083d94539a5eefc07e0475'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('linux-repository', 'sheng-repository', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--stock-fdt', type=Path)
    args = parser.parse_args()
    inputs = {}
    def get(repo, rev, path):
        data = subprocess.check_output(['git', '-C', str(repo), 'show', rev+':'+path])
        inputs[rev+':'+path] = hashlib.sha256(data).hexdigest()
        return data.decode()
    def linux(path):
        return get(args.linux_repository, LINUX, path)
    dt = linux('arch/arm64/boot/dts/qcom/sm8750.dtsi')
    node = dt.split('pcie0: pcie@1c00000 {', 1)[1].split('bus-range', 1)[0]
    assert '<0x02000000 0x0 0x40300000 0x0 0x40300000 0x0 0x23d00000>' in node
    wifi7 = linux('drivers/net/wireless/ath/ath12k/wifi7/pci.c')
    peach = wifi7.split('case PEACH_DEVICE_ID:', 1)[1].split('case QCC2072_DEVICE_ID:', 1)[0]
    assert 'window_reg_addr = WINDOW_REG_ADDRESS_QCC2072;' in peach
    assert 'ATH12K_PCI_W7_SOC_HW_VERSION_2' in peach and 'ATH12K_HW_PEACH_HW20' in peach
    assert 'ath12k_wifi7_pci_read_hw_version' in peach and 'static_window_map = false' in peach
    for key, value in [('WINDOW_REG_ADDRESS_QCC2072', '0x3278'), ('TCSR_SOC_HW_VERSION', '0x1B00000')]:
        assert re.search(r'#define\s+'+key+r'\s+'+value+r'\b', wifi7)
    assert re.search(r'#define\s+TCSR_SOC_HW_VERSION_MAJOR_MASK\s+GENMASK\(11, 8\)', wifi7)
    common = linux('drivers/net/wireless/ath/ath12k/pci.c')
    assert 'static_window = ab_pci->register_window & WINDOW_STATIC_MASK;' in common
    assert re.search(r'#define\s+WINDOW_ENABLE_BIT\s+0x40000000', common)
    assert re.search(r'#define\s+WINDOW_VALUE_MASK\s+GENMASK\(24, 19\)', common)
    assert re.search(r'#define\s+WINDOW_RANGE_MASK\s+GENMASK\(18, 0\)', common)
    sheng = get(args.sheng_repository, SHENG, 'package/WifiProbe.cpp')
    endpoint = sheng.split('void endpointProbe(', 1)[1].split('// Stage 2', 1)[0]
    assert 'a + 0x200 / 4' in endpoint and 'c[0x10 / 4] = 0xffffffffu;' in endpoint
    assert 'd[0x20 / 4]' in endpoint and 'if ((mask & 6u) == 4u) c[0x14 / 4] = 0;' in endpoint
    dwc = linux('drivers/pci/controller/dwc/pcie-designware.h')
    assert '(((index) << 9)' in dwc
    for name, value in [('REGION_CTRL1', 0), ('REGION_CTRL2', 4), ('LOWER_BASE', 8),
                        ('UPPER_BASE', 12), ('LOWER_LIMIT', 16), ('LOWER_TARGET', 20),
                        ('UPPER_TARGET', 24), ('UPPER_LIMIT', 32)]:
        assert re.search(r'#define\s+PCIE_ATU_UNR_'+name+r'\s+0x'+f'{value:02x}'+r'\b', dwc, re.I)
    assert re.search(r'#define\s+PCIE_ATU_ENABLE\s+BIT\(31\)', dwc)
    facts_path = ROOT/'drivers/EldenPcie/endpoint-facts.json'
    facts = json.loads(facts_path.read_text(encoding='utf-8'))
    assert facts['device'] == 'TB322FC' and facts['soc'] == 'SM8750'
    assert facts['stock_ranges_cells'] == [0x1000000, 0, 0x40200000, 0x40200000, 0, 0x100000,
                                          0x2000000, 0, 0x40300000, 0x40300000, 0, 0x3d00000]
    assert facts['memory_base'] == 0x40300000
    assert facts['stock_memory_end_exclusive'] == 0x44000000
    assert facts['linux_memory_end_exclusive'] == 0x64000000
    if args.stock_fdt:
        sys.path.insert(0, str(ROOT/'tools/legacy-workbench'))
        from fdt_memory_plan import parse_fdt
        raw = args.stock_fdt.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == facts['stock_fdt_sha256']
        nodes, _ = parse_fdt(raw)
        props = nodes[facts['node']]
        assert struct.unpack('>I', props['#address-cells'])[0] == 3
        assert struct.unpack('>I', props['#size-cells'])[0] == 2
        assert struct.unpack('>I', nodes['/soc']['#address-cells'])[0] == 1
        assert list(struct.unpack('>12I', props['ranges'])) == facts['stock_ranges_cells']
    source = (ROOT/'drivers/EldenPcie/Endpoint.c').read_text(encoding='utf-8')
    for value in ('MEM_BASE UINT64_C(0x40300000)', 'MEM_END UINT64_C(0x44000000)',
                  'REMAP 0x3278u', 'VERSION 0x01b00000u', '((e->chip_version>>8)&15)!=2'):
        assert value in source
    assert 'wr(e,EldenPcieConfig,4,e->command|2u)' in source
    assert 'w==EldenPcieConfig&&o==4&&(v&~0xfffau)' in source
    report = {'passed': True, 'linux_revision': LINUX, 'sheng_revision': SHENG,
              'source_inputs': inputs, 'stock_fdt_checked': bool(args.stock_fdt),
              'facts_sha256': hashlib.sha256(facts_path.read_bytes()).hexdigest(),
              'endpoint_source_sha256': hashlib.sha256(source.encode()).hexdigest(),
              'scope': 'Source fields/provenance only; native mapping and hardware not tested'}
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))

if __name__ == '__main__':
    main()
