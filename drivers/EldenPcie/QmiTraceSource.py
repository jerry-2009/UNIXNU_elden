"""Read-only combined native/dispatcher/QMI metadata during shutdown."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[2]
def generated():
    spec=importlib.util.spec_from_file_location('qmi_stop',ROOT/'drivers/EldenPcie/StopTraceSource.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);files=mod.generated()
    def replace(text,old,new):
        if text.count(old)!=1:raise ValueError('QMI native anchor differs')
        return text.replace(old,new,1)
    text=files['Native.cpp'].decode();text=replace(text,'#include "ControlApi.h"','#include "ControlApi.h"\n#include "EldenQmiTrace.h"');files['Native.cpp']=text.encode()
    text=files['NativeRuntime.inc'].decode()
    sampler='''{
        stop_where();uint32_t masks[5]={},hardware=UINT32_MAX,enable=UINT32_MAX,mask=UINT32_MAX,mhi=UINT32_MAX;
        elden_wifi_irq_trace((uint32_t)c->runtime_board.irq_base,masks);
        int read_status=c->maps[EldenPcieDbi].read(EldenMsiStatus,&hardware);
        int re=c->maps[EldenPcieDbi].read(EldenMsiEnable,&enable),rm=c->maps[EldenPcieDbi].read(EldenMsiMask,&mask),rh=c->bar0_map.read(0x48,&mhi);
        log("\\nELDEN_QMI_IRQ base=%d used=%x enabled=%x pending=%x strict=%x disabled=%x HW=%x/%x/%x MHI=%x reads=%d/%d/%d/%d count=%u native-pending=%x error=%d\\n",
            c->runtime_board.irq_base,masks[0],masks[1],masks[2],masks[3],masks[4],hardware,enable,mask,mhi,read_status,re,rm,rh,
            __atomic_load_n(&c->msi.irq_count,__ATOMIC_RELAXED),__atomic_load_n(&c->msi.pending,__ATOMIC_ACQUIRE),__atomic_load_n(&c->msi.irq_error,__ATOMIC_ACQUIRE));
        uint64_t q[EldenQmiTraceCount];for(unsigned j=0;j<EldenQmiTraceCount;j++)q[j]=__atomic_load_n(&elden_wifi_qmi_trace[j],__ATOMIC_RELAXED);
        log("\\nELDEN_QMI_STATE phase=%llu txn=%llu queue=%llu UL=%llu/%lld DL=%llu/%lld RX=%llu complete=%llu/%lld\\n",
            (unsigned long long)q[EldenQmiPhase],(unsigned long long)q[EldenQmiTxn],(unsigned long long)q[EldenQmiQueued],
            (unsigned long long)q[EldenQmiUlDone],(long long)q[EldenQmiUlStatus],(unsigned long long)q[EldenQmiDlDone],
            (long long)q[EldenQmiDlStatus],(unsigned long long)q[EldenQmiResponses],(unsigned long long)q[EldenQmiCompleted],(long long)q[EldenQmiResult]);
    }'''
    text=replace(text,'if(i%2000==0)stop_where();','if(i%2000==0)'+sampler);files['NativeRuntime.inc']=text.encode();return files
