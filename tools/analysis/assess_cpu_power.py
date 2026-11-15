"""Cross-check raw per-CPU load intervals and SCMI reports in a bound v146 capture."""
from pathlib import Path
import argparse,json,re,statistics
from assess_pd_power import assess

def analyze(run):
    pd=assess(run)
    if pd['profile']!='cpu-power-observation':raise ValueError('Not the combined observer')
    raw=next((run/'usb').glob('*.bin'));text=raw.read_bytes().decode('utf-8',errors='replace').replace('\r','')
    starts=re.findall(r'^ELDEN_CPU_POWER begin cpus=8 domains=(\d+) hz=(\d+) tick=(\d+) base=([0-9a-f]+) perf=([0-9a-f]+) PERF_SET=0 LIMITS_SET=0$',text,re.M)
    ends=re.findall(r'^ELDEN_CPU_POWER end ok=(\d+) complete=(\d+) intervals=(\d+) domains=(\d+),(\d+) channel-free=(\d+) access-error=(\d+) transfers=(\d+); levels unchanged$',text,re.M)
    if len(starts)!=1 or len(ends)!=1:raise ValueError('Missing or repeated observer boundary')
    domains,hz,tick=map(int,starts[0][:3]);end=dict(zip(['ok','complete','intervals','domain0','domain1','free','access_error','transfers'],map(int,ends[0])))
    if domains!=2 or not hz or not tick:raise ValueError('Invalid counter/domain description')
    rows={};values={c:[] for c in range(8)}
    for m in re.finditer(r'^ELDEN_CPU_LOAD sample=(\d+) cpu=(\d+) at=(\d+) ticks=(\d+),(\d+),(\d+),(\d+) valid=(\d+) busy-pm=(\d+) delta=(\d+) idle=(\d+)$',text,re.M):
        s,c,at,u,k,idle,nice,valid,busy,total,di=map(int,m.groups())
        if (s,c) in rows or s>8 or c>7:raise ValueError('Duplicate/out-of-range load row')
        rows[s,c]={'at':at,'ticks':[u,k,idle,nice],'valid':valid,'busy_pm':busy,'total':total,'idle':di}
    for (s,c),row in sorted(rows.items()):
        if not s:
            if row['valid']:raise ValueError('Baseline must not be a load interval')
            continue
        prior=rows.get((s-1,c))
        if prior is None:continue
        elapsed=row['at']-prior['at'];delta=[(b-a)&0xffffffff for a,b in zip(prior['ticks'],row['ticks'])]
        total=sum(delta);expected=elapsed//tick
        valid=elapsed>0 and elapsed<=10*hz and 50<=expected<=10000 and total>0 and abs(total-expected)<=3
        if bool(row['valid'])!=valid:raise ValueError('Validity disagrees with captured counters')
        if valid:
            busy=(total-delta[2])*1000//total
            if (row['total'],row['idle'],row['busy_pm'])!=(total,delta[2],busy):raise ValueError('Load computation disagrees')
            values[c].append(busy)
    frequency=[];errors=[]
    for m in re.finditer(r'^ELDEN_CPU_CURRENT sample=(\d+) domain=(\d+) raw=(\d+) index=(\d+) table-khz=(\d+) exact=(\d+)$',text,re.M):
        frequency.append(dict(zip(['sample','domain','raw','index','table_khz','exact'],map(int,m.groups()))))
    for m in re.finditer(r'^ELDEN_CPU_POWER level-error sample=(\d+) domain=(\d+) error=(\d+) status=(-?\d+)$',text,re.M):
        errors.append(dict(zip(['sample','domain','error','status'],map(int,m.groups()))))
    complete_rows=len(rows)==72 and all(len(v)==8 for v in values.values())
    complete_levels=len(frequency)==18 and len({(r['sample'],r['domain']) for r in frequency})==18 and not errors and all(r['sample']<=8 and r['domain']<2 and r['exact']==1 for r in frequency)
    if end['complete'] and not (complete_rows and complete_levels and end['ok'] and end['intervals']==8):raise ValueError('Claimed completion lacks raw evidence')
    summary={str(c):{'intervals':len(v),'median_busy_pm':statistics.median(v) if v else None,'min_busy_pm':min(v) if v else None,'max_busy_pm':max(v) if v else None} for c,v in values.items()}
    return {'pd':pd,'observer':end,'counter_hz':hz,'tick_interval':tick,'load_rows':len(rows),'all_load_intervals_verified':complete_rows,'all_level_samples_received':complete_levels,'cpu_load':summary,'frequency':frequency,'level_errors':errors,
            'limits':'Load is per-core XNU accounting over bounded intervals. PERF table values are firmware-reported levels, not measured instantaneous MHz. Character drops remain in pd.dropped. No DVFS/retention or net-charge acceptance follows from this observation.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=analyze(a.run)
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps({k:r[k] for k in ('observer','all_load_intervals_verified','all_level_samples_received','cpu_load','level_errors')}))
if __name__=='__main__':main()
