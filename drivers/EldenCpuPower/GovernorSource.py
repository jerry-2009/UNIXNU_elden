"""Extract the frozen upstream demand policy; do not import its I/O/retry layer."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent

def policy():
    origin=HERE/'upstream';lock=json.loads((origin/'source.json').read_text(encoding='utf-8'))
    data=(origin/'CpuFreqGovernor.h').read_bytes()
    if hashlib.sha256(data).hexdigest()!=lock['files']['CpuFreqGovernor.h']['sha256']:
        raise ValueError('Frozen upstream governor differs')
    text=data.decode();marker='enum Op : uint8_t { kOpStart, kOpSet, kOpCheck, kOpLimits };'
    if text.count(marker)!=1 or text.count('#include "ScmiPerf.h"')!=1:raise ValueError('Policy boundary differs')
    # Up to this marker is arithmetic and CPU-load conversion. All Control,
    # retry, setLevel/controlCheck and best-effort restore functions follow it.
    pure=text[:text.index(marker)].replace('#include "ScmiPerf.h"','#include "EldenScmiPerf.h"')
    return (pure+'\n} // namespace cpufreq\n#endif\n').encode()
