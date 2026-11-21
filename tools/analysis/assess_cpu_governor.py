"""Assess the session-bound governor lifecycle; power windows are descriptive."""
from pathlib import Path
import argparse,json,re,statistics
from assess_pd_power import assess
def analyze(run):
    pd=assess(run)
    if pd['profile']!='cpu-governor':raise ValueError('Wrong governor candidate')
    text=next((run/'usb').glob('*.bin')).read_bytes().decode('utf-8',errors='replace').replace('\r','')
    rows=[];batteries=[];release=[];copies=[]
    pattern=r'ELDEN_CPU_GOV phase=(\w+) elapsed-ms=(\d+) state=(\d+) error=(\d+) scmi=(\d+)/(-?\d+) windows=(\d+) sets=(\d+) confirmed=(\d+) restore=(\d+)/(\d+) levels=(\d+),(\d+) table-khz=(\d+),(\d+) caps=(\d+),(\d+)'
    keys=['elapsed_ms','state','error','scmi_error','scmi_status','windows','sets','confirmed','restored','restore_sets','level0','level1','khz0','khz1','cap0','cap1']
    for line,s in enumerate(text.splitlines()):
        m=re.fullmatch(pattern,s)
        if m:rows.append({'line':line,'phase':m[1],**dict(zip(keys,map(int,m.groups()[1:])))})
        m=re.fullmatch(r'ELDEN_BATTERY published cycle=(\d+) percent=(\d+) mv=(\d+) ma=(-?\d+) temp-centi-C=(\d+) external=(\d+) net-charging=(\d+) raw-gauges=independent writes=0',s)
        if m:batteries.append({'line':line,**dict(zip(['cycle','percent','mv','ma','temperature','external','charging'],map(int,m.groups())))})
        m=re.fullmatch(r'ELDEN_CPU_GOV release clean=(\d+) held=(\d+) transfers=(\d+)',s)
        if m:release.append(dict(zip(['clean','held','transfers'],map(int,m.groups()))))
        m=re.fullmatch(r'ELDEN_DISPLAY CPU copy bytes=(\d+) ticks=(\d+)',s)
        if m:copies.append({'line':line,'bytes':int(m[1]),'ticks':int(m[2])})
    begin=[r for r in rows if r['phase']=='active'];end=[r for r in rows if r['phase']=='end']
    lifecycle=False;active_power=[];restored_power=[]
    if len(begin)==len(end)==1:
        a,b=begin[0],end[0]
        lifecycle=(b['state']==4 and b['error']==0 and b['confirmed']>0 and b['sets']==b['confirmed']+b['restore_sets'] and b['restore_sets']==b['restored'] and b['restored']>0 and (a['level0'],a['level1'])==(b['level0'],b['level1']))
        active_power=[p for p in batteries if a['line']<p['line']<b['line']][-10:]
        restored_power=[p for p in batteries if p['line']>b['line']][:10]
    cleanup=(len(release)==1 and release[0]['clean']==1 and release[0]['held']==0 and 'ELDEN_CPU_GOV RPC stop=1;' in text)
    def summarize(samples):
        return {'count':len(samples),'median_published_ma':statistics.median(p['ma'] for p in samples) if samples else None,'cycles':[p['cycle'] for p in samples],'percent':[p['percent'] for p in samples]}
    timing={}
    if len(begin)==len(end)==1:
        for name,samples in [('before',[x for x in copies if x['line']<begin[0]['line']]),('active',[x for x in copies if begin[0]['line']<x['line']<end[0]['line']]),('after',[x for x in copies if x['line']>end[0]['line']])]:
            # Runtime refuses any timebase other than the established19.2MHz.
            values=[x['ticks']/19200 for x in samples]
            timing[name]={'count':len(values),'bytes':sorted({x['bytes'] for x in samples}),'median_ms':statistics.median(values) if values else None,'min_ms':min(values) if values else None,'max_ms':max(values) if values else None}
    return {'pd':pd,'governor_lifecycle_passed':bool(lifecycle),'cleanup_passed':cleanup,'rows':rows,'release':release,'active_tail':summarize(active_power),'after_restore_first':summarize(restored_power),'display_copy':timing,'limits':'Sparse reported levels are confirmed controller states, not instantaneous measured clocks. Publisher power/copy windows may differ in GUI/workload and are not a causal A/B benchmark. Copy time is not end-to-end frame latency. Drops remain recorded; no full-cycle/peak-PD acceptance.'}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=analyze(a.run)
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps({k:r[k] for k in ('governor_lifecycle_passed','cleanup_passed','active_tail','after_restore_first')}))
if __name__=='__main__':main()
