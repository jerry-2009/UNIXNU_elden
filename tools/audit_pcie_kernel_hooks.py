"""Verify direct root start/stop/transaction calls and their preserved prelink bytes."""
import argparse,json,struct
from pathlib import Path
from replay_xnu_objects import global_symbols
def audit(native,kernel,endpoint=False,smmu=False,mhi=False,control=False,cleanup=False,platform=False,budget=False):
    data=Path(native).read_bytes();after=Path(kernel).read_bytes();at=32;sections={};code=[]
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        cmd,size=struct.unpack_from('<II',data,at)
        if cmd==0x19:
            for i in range(struct.unpack_from('<I',data,at+64)[0]):
                s=at+72+i*80;name=data[s:s+16].split(b'\0')[0].decode();seg=data[s+16:s+32].split(b'\0')[0].decode()
                va,n,off=struct.unpack_from('<QQI',data,s+32);flags=struct.unpack_from('<I',data,s+64)[0];sections[seg+'/'+name]=va
                if flags&0x80000400:code.append((va,n,off))
        at+=size
    syms=global_symbols(Path(native))
    def address(name):
        s=syms[name];return sections[s[1]]+s[2]
    def word(blob,va):
        at=32
        for _ in range(struct.unpack_from('<I',blob,16)[0]):
            cmd,n=struct.unpack_from('<II',blob,at)
            if cmd==0x19:
                base,_,off,size=struct.unpack_from('<QQQQ',blob,at+24)
                if base<=va and va+4<=base+size:return blob[off+va-base:off+va-base+4]
            at+=n
        raise ValueError('Address not file-backed')
    result={}
    targets=[('_elden_pcie_native_start','_elden_wcn_power_start',256),('_elden_pcie_native_stop_begin','_elden_wcn_request_stop',512),
             ('_elden_pcie_root_start',None,0),('_elden_wlan_root_power',None,0)]
    if endpoint:targets+=[('_elden_pcie_endpoint_identify',None,0),('_elden_wlan_power_confirm_endpoint',None,0)]
    if smmu:targets+=[('_elden_wifi_smmu_early_initialize','_elden_wifi_smmu_early_invoke',256),('_elden_wifi_smmu_early_invoke',None,0),('_elden_wifi_smmu_stop_begin',None if mhi else '_elden_wcn_request_stop',0 if mhi else 512),
                      ('_elden_smmu_domain_start',None,0),('_elden_smmu_select_boot_domain',None,0)]
    expected_counts={}
    if mhi:
        for name,count in [('_nw_wifi_start',1),('_nw_wifi_stop',1 if platform else 2),('_elden_mhi_stop',1),('_elden_wifi_runtime_enable_master',1),('_elden_wlan_qmi_bind',1),('_elden_wlan_qmi_unbind',1)]:
            targets.append((name,None,0));expected_counts[name]=count
    if control:
        if not mhi:raise ValueError('Control endpoint requires MHI runtime')
        for name in ['_nw_wifi_control_transport_set','_nwk_nw_wifi_control_bind','_nw_wifi_control_attach','_nw_wifi_control_receive']:
            targets.append((name,None,0));expected_counts[name]=1
    if cleanup:
        if not mhi:raise ValueError('Cleanup requires MHI runtime')
        for name,count in [('_elden_wifi_dma_cleanup_begin',1),('_elden_wifi_dma_close_admission',2)]:
            targets.append((name,None,0));expected_counts[name]=count
    if platform:
        if not cleanup:raise ValueError('Platform shutdown requires owned cleanup')
        for name in ['_nw_wifi_platform_shutdown','_elden_nw_pci_platform_shutdown']:
            targets.append((name,None,0));expected_counts[name]=1
    if budget:
        if not platform:raise ValueError('Budget requires platform shutdown')
        targets.append(('_elden_wifi_platform_deadline_ms',None,0));expected_counts['_elden_wifi_platform_deadline_ms']=1
    for target,caller,bound in targets:
        dest=address(target);calls=[]
        for base,size,off in code:
            for p in range(0,size-3,4):
                ins=struct.unpack_from('<I',data,off+p)[0]
                if ins&0x7c000000!=0x14000000:continue
                delta=ins&0x3ffffff
                if delta&(1<<25):delta-=1<<26
                if base+p+(delta<<2)==dest:calls.append(base+p)
        if len(calls)!=expected_counts.get(target,1):raise ValueError('Unexpected actual call count to '+target+': '+str(len(calls)))
        if caller and not address(caller)<=calls[0]<address(caller)+bound:raise ValueError('Wrong caller '+target)
        for va in [dest,*calls]:
            if word(data,va)!=word(after,va):raise ValueError('Prelink changed branch/provider')
        result[target]={'address':hex(dest),'calls':[hex(v) for v in calls],'caller':caller,'prelink_preserved':True}
    return result
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['native','kernel','output']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--endpoint',action='store_true')
    p.add_argument('--smmu',action='store_true')
    p.add_argument('--mhi',action='store_true')
    a=p.parse_args();r=audit(a.native,a.kernel,a.endpoint,a.smmu,a.mhi);a.output.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps(r))
if __name__=='__main__':main()
