"""Assess session-bound paired UFS reads; do not infer hardware CPU utilization."""
from pathlib import Path
import argparse,collections,json,math,re,statistics
from assess_pd_power import assess
ROOT=Path(__file__).resolve().parents[2]

def parse(text):
    pin_text=(ROOT/'scripts/driver-patches/EldenPinnedRoot.h').read_text()
    sizes={name:int(size)//4096 for name,size in re.findall(r'\{"(OS|SystemOS)",(\d+)ULL,',pin_text)}
    if set(sizes)!={'OS','SystemOS'}:raise ValueError('Unexpected image pins')
    pattern=r'^ELDEN_UFS_TRIAL row name=(OS|SystemOS) seq=(\d+) mode=(\d+) block=(\d+) bytes=(\d+) ns=(\d+) irqs=(\d+) sleeps=(\d+) wakes=(\d+) timeouts=(\d+) sha=([0-9a-f]{64})$'
    rows=[]
    for m in re.finditer(pattern,text,re.M):
        row=dict(zip(('seq','mode','block','bytes','ns','irqs','sleeps','wakes','timeouts'),map(int,m.groups()[1:-1])))
        row.update(name=m[1],sha256=m[11]);rows.append(row)
    ends=re.findall(r'^ELDEN_UFS_TRIAL end name=(OS|SystemOS) good=(\d+) rows=(\d+) poll-restored=(\d+)$',text,re.M)
    if len(rows)!=128 or sorted(ends)!=[('OS','1','64','1'),('SystemOS','1','64','1')]:
        raise ValueError('Incomplete, duplicated or failed read trial')
    pairs={};groups=collections.defaultdict(list)
    for name,total in sizes.items():
        selected=[r for r in rows if r['name']==name]
        if [r['seq'] for r in selected]!=list(range(64)):raise ValueError('Read sequence differs')
        marker=f'ELDEN_UFS_TRIAL begin name={name} blocks={total} samples=64 modes=poll,hybrid IRQ=both warm=4 QD=1'
        if text.count(marker)!=1:raise ValueError('Missing trial configuration')
        pin=f'EldenRoot: {name} complete SHA256 accepted; {total} protected block hashes;'
        if text.count(pin)!=1 or text.index(pin)>text.index(marker):raise ValueError('Unproven pinned data')
        for row in selected:
            site=row['seq']//4;size=(row['seq']//2)%2;order=row['seq']%2
            expected_block=(site*(total-32)//15)&~31
            if row['block']!=expected_block or row['bytes']!=(131072 if size else 4096) or row['mode']!=(site+order)%2:
                raise ValueError('Dataset/order changed')
            if not 0<row['ns']<=1000000000 or row['wakes']+row['timeouts']>row['sleeps']:
                raise ValueError('Invalid duration or counters')
            if row['mode']==0 and (row['sleeps'] or row['wakes'] or row['timeouts']):raise ValueError('Polling slept')
            key=(name,row['block'],row['bytes'])
            if key in pairs and pairs[key]!=row['sha256']:raise ValueError('Paired data hashes differ')
            pairs[key]=row['sha256'];groups[(name,row['bytes'],row['mode'])].append(row)
    if len(pairs)!=64:raise ValueError('Missing matched data')
    summary=[]
    for (name,size,mode),group in sorted(groups.items()):
        values=sorted(r['ns'] for r in group)
        summary.append({'name':name,'bytes':size,'mode':mode,'samples':len(group),
                        'median_us':statistics.median(values)/1000,'p95_us':values[math.ceil(len(values)*.95)-1]/1000,
                        'transport_copy_MiB_s':sum(r['bytes'] for r in group)*1e9/sum(values)/(1<<20),
                        **{k:sum(r[k] for r in group) for k in ('irqs','sleeps','wakes','timeouts')}})
    irq=sum(r['irqs'] for r in rows);wakes=sum(r['wakes'] for r in rows)
    return {'rows':rows,'groups':summary,'paired_hashes':len(pairs),'data_comparison_passed':True,
            'irq_observed':irq>0,'irq_wake_observed':wakes>0,
            'limits':'Warm pre-publication QD1; transport+copy timing excludes hashing/logging. Both modes retain IRQs. Not sustained throughput, CPU utilization, multi-slot or user-visible latency.'}

def analyze(run):
    identity=assess(run)
    if identity['profile']!='ufs-wait-trial':raise ValueError('Wrong profile')
    text=next((run/'usb').glob('*.bin')).read_bytes().decode(errors='replace').replace('\r','')
    comparison=parse(text)
    supervisor=json.loads((run/'supervisor.json').read_text())
    root='BSD root:' in text
    ordered=text.index('ELDEN_VDOG EARLY_ARM')<text.index('ELDEN_UFS_TRIAL begin')<text.index('BSD root:') if root else False
    armed=bool(re.search(r'ELDEN_VDOG EARLY_ARM session='+identity['session']+r' rc=0 state=1 ctl=1 elapsed-ms=\d+ expired=0 ',text))
    adopted=bool(re.search(r'ELDEN_VDOG SMP_ADOPT session='+identity['session']+r' rc=0 state=1 ',text))
    eight='ELDEN_SMP action=2 phase=3 reason=0 expected=ff online=ff work=ff timers=ff ipis=ff error=0 vdog=1' in text
    restore=json.loads((run/'restore/result.json').read_text())
    restored=restore.get('success') and restore.get('full_readback_sha256')=='8b8e72dad85a65d3bf6fc2c6b2a88064d0487e4696ae578e9fd4c46a33565890'
    stop=re.findall(r'^ELDEN_UFS_IRQ stop commands=(\d+) wait-us=(\d+) irqs=(\d+) sleeps=(\d+) wakes=(\d+) timeouts=(\d+) other=(\d+) spurious=(\d+); polling remains, DMA retained$',text,re.M)
    totals=dict(zip(('commands','wait_us','irqs','sleeps','wakes','timeouts','other','spurious'),map(int,stop[0]))) if len(stop)==1 else None
    good=bool(comparison['irq_observed'] and comparison['irq_wake_observed'] and root and ordered and armed and adopted and eight
              and totals and identity['reset_after_sync'] and supervisor.get('complete') and restored)
    return {'passed':good,'comparison':comparison,'identity':identity,'root':root,'early_guard_order':ordered,
            'early_armed':armed,'eight_core_admitted':eight,'smp_adopted':adopted,'stop_totals':totals,'stock_restored':bool(restored),'supervisor_complete':supervisor.get('complete',False)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=analyze(a.run)
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps({'passed':r['passed'],'groups':r['comparison']['groups'],'irq_wake_observed':r['comparison']['irq_wake_observed'],'dropped':r['identity']['dropped']}))
if __name__=='__main__':main()
