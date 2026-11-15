"""Wire the root worker into existing WCN start/stop, without static init."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def source():
    spec=importlib.util.spec_from_file_location('root_power_source',ROOT/'drivers/EldenPcie/PowerNativeSource.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);text=mod.source().decode()
    declaration='int elden_recovery_armed(void);';assert text.count(declaration)==1
    text=text.replace(declaration,declaration+'\nvoid elden_pcie_native_start(void);\nvoid elden_pcie_native_stop_begin(void);',1)
    start='extern "C" void elden_wcn_power_start(void){';assert text.count(start)==1
    text=text.replace(start,start+'\n    elden_pcie_native_start();',1)
    stop='    __atomic_store_n(&platform_stopping,1,__ATOMIC_RELEASE);';assert text.count(stop)==1
    text=text.replace(stop,'    elden_pcie_native_stop_begin();\n'+stop,1)
    return text.encode()
