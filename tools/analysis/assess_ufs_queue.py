"""Assess complete equal-data QD1/8/32 trials and the verified return path."""
from pathlib import Path
import argparse,json,re,statistics
from assess_pd_power import assess
def parse(text):
    configurations=re.findall(r'^ELDEN_UFS_QUEUE configured slots=(\d+) entries=(\d+) uncached=(\d+) list=([0-9a-f]+) dma-limit=([0-9a-f]+)$',text,re.M)
    mappings=re.findall(r'^ELDEN_UFS_QUEUE list-map va=([0-9a-f]+) pa=([0-9a-f]+) read-par=([0-9a-f]+) write-par=([0-9a-f]+)$',text,re.M)
    if len(configurations)!=1 or configurations[0][:3]!=('32','32','1') or len(mappings)!=1:raise ValueError('Unqualified 32-slot request list')
    address,limit=map(lambda x:int(x,16),configurations[0][3:]);va,pa,r,w=map(lambda x:int(x,16),mappings[0])
    if not va or pa!=address or address&4095 or address>=limit or 4096>limit-address or any(v&1 or (v>>56)&255!=0x44 or v&0x0000fffffffff000!=pa for v in (r,w)):raise ValueError('Request list mapping differs')
    pattern=r'^ELDEN_UFS_QD row name=(OS|SystemOS) qd=(\d+) bytes=(\d+) pass=(\d+) commands=(\d+) io-ns=(\d+) db-peak=(\d+) direct=(\d+) irq=(\d+) sleeps=(\d+) wakes=(\d+) timeouts=(\d+) sha=([0-9a-f]{64})$'
    rows=[];keys=set();digests={}
    for m in re.finditer(pattern,text,re.M):
        names=('qd','bytes','pass','commands','io_ns','db_peak','direct','irq','sleeps','wakes','timeouts')
        row=dict(zip(names,map(int,m.groups()[1:-1])));row.update(name=m[1],sha256=m[13]);key=(m[1],row['qd'],row['bytes'],row['pass'])
        if key in keys:raise ValueError('Duplicate QD row')
        keys.add(key)
        if row['commands']!=32 or row['direct']!=32 or not 0<row['io_ns']<=30000000000 or not 0<row['db_peak']<=row['qd'] or row['wakes']+row['timeouts']>row['sleeps']:raise ValueError('Invalid QD counters')
        digest_key=(m[1],row['bytes'],row['pass'])
        if digest_key in digests and digests[digest_key]!=row['sha256']:raise ValueError('Data differs across queue depths')
        digests[digest_key]=row['sha256'];rows.append(row)
    expected={(name,qd,size,p) for name in ('OS','SystemOS') for qd in (1,8,32) for size in (4096,131072) for p in range(4)}
    if keys!=expected:raise ValueError(f'Incomplete QD rows: {len(keys)}/48')
    ends=re.findall(r'^ELDEN_UFS_QD end name=(OS|SystemOS) good=(\d+)$',text,re.M)
    if sorted(ends)!=[('OS','1'),('SystemOS','1')]:raise ValueError('Trial did not complete')
    summary=[]
    for name in ('OS','SystemOS'):
        marker=f'ELDEN_UFS_QD begin name={name} '
        pin=f'EldenRoot: {name} complete SHA256 accepted;'
        if text.count(marker)!=1 or text.count(pin)!=1 or text.index(pin)>text.index(marker):raise ValueError('Missing whole-image pin before trial')
        for size in (4096,131072):
            baseline=[r['io_ns'] for r in rows if r['name']==name and r['bytes']==size and r['qd']==1]
            for qd in (1,8,32):
                group=[r for r in rows if r['name']==name and r['bytes']==size and r['qd']==qd]
                total=sum(r['io_ns'] for r in group)
                summary.append({'name':name,'bytes':size,'qd':qd,'samples':4,'commands':128,
                                'io_MiB_s':128*size*1e9/total/(1<<20),'median_batch_us':statistics.median(r['io_ns'] for r in group)/1000,
                                'vs_qd1':sum(baseline)/total,'max_observed_doorbells':max(r['db_peak'] for r in group),
                                'sleeps':sum(r['sleeps'] for r in group),'timeouts':sum(r['timeouts'] for r in group)})
    parallel=all(max(r['db_peak'] for r in rows if r['name']==n and r['qd']==32)>1 for n in ('OS','SystemOS'))
    return {'rows':rows,'summary':summary,'equal_data_sets':len(digests),'physical_overlap_observed':parallel,
            'request_list':{'slots':32,'entries':32,'uncached':True,'pa':hex(pa),'va':hex(va),'read_par':hex(r),'write_par':hex(w),'dma_limit':hex(limit)},
            'limits':'Pre-publication driver-owned direct DMA, fixed QD1->8->32 order per dataset; device cache is not controlled. Timed issue/await excludes hashing/logging. Four batches per group. Ratios are observed comparisons, not isolated causal speedups, CPU utilization, sustained filesystem throughput or GUI latency.'}
def analyze(run):
    identity=assess(run)
    if identity['profile']!='ufs-queue-trial':raise ValueError('Wrong image profile')
    text=next((run/'usb').glob('*.bin')).read_bytes().decode(errors='replace').replace('\r','')
    comparison=parse(text);supervisor=json.loads((run/'supervisor.json').read_text());restore=json.loads((run/'restore/result.json').read_text())
    restored=restore.get('success') and restore.get('full_readback_sha256')=='8b8e72dad85a65d3bf6fc2c6b2a88064d0487e4696ae578e9fd4c46a33565890'
    armed=bool(re.search(r'ELDEN_VDOG EARLY_ARM session='+identity['session']+r' rc=0 state=1 ctl=1 ',text))
    adopted=bool(re.search(r'ELDEN_VDOG SMP_ADOPT session='+identity['session']+r' rc=0 state=1 ',text))
    eight='ELDEN_SMP action=2 phase=3 reason=0 expected=ff online=ff work=ff timers=ff ipis=ff error=0 vdog=1' in text
    result=bool(restored and supervisor.get('complete') and identity['reset_after_sync'] and comparison['physical_overlap_observed'] and armed and adopted and eight and 'BSD root:' in text)
    return {'passed':result,'comparison':comparison,'identity':identity,'early_armed':armed,'smp_adopted':adopted,'eight_core_admitted':eight,'stock_restored':bool(restored)}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=analyze(a.run)
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps({'passed':r['passed'],'summary':r['comparison']['summary'],'dropped':r['identity']['dropped']}))
if __name__=='__main__':main()
