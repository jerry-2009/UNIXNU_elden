"""Assess actual Hibern8 counters, authenticated wake reads and restoration."""
from pathlib import Path
import argparse,json,re
from assess_pd_power import assess
def parse(text):
    enables=re.findall(r'^ELDEN_UFS_IDLE enable=(-?\d+) phase=(\d+) ahit=([0-9a-f]+) cfg=([0-9a-f]+) ie=([0-9a-f]+)$',text,re.M)
    if len(enables)!=2 or any(rc!='0' or phase!='2' or int(timer,16)!=0x5f4 or int(cfg,16)&0x3c!=0x3c or int(ie,16)!=0x61 for rc,phase,timer,cfg,ie in enables):raise ValueError('AH8 enable unproven')
    rows=[]
    for m in re.finditer(r'^ELDEN_UFS_IDLE row name=(OS|SystemOS) seq=(\d+) blocks=(\d+) status=([0-9a-f]+) verified=(\d+) ns=(\d+) hw-enter=(\d+) hw-exit=(\d+) enters=(\d+) exits=(\d+)$',text,re.M):
        row={'name':m[1],'seq':int(m[2]),'blocks':int(m[3]),'status':int(m[4],16),**dict(zip(('verified','ns','hw_enter','hw_exit','enters','exits'),map(int,m.groups()[4:])))}
        if row['status'] or row['verified']!=1 or row['blocks']!=(32 if row['seq']&1 else 1) or not 0<row['enters']<1024 or not 0<row['exits']<1024:raise ValueError('Idle wake read or transition failed')
        rows.append(row)
    if len(rows)!=32:raise ValueError('Incomplete wake records')
    for name in ('OS','SystemOS'):
        group=[r for r in rows if r['name']==name]
        if [r['seq'] for r in group]!=list(range(16)):raise ValueError('Duplicate/reordered wake rows')
        if any(not 0<=r[k]<=0xffffffff for r in group for k in ('hw_enter','hw_exit')):raise ValueError('Counter outside hardware width')
        for old,new in zip(group,group[1:]):
            if ((new['hw_enter']-old['hw_enter'])&0xffffffff)!=new['enters'] or ((new['hw_exit']-old['hw_exit'])&0xffffffff)!=new['exits']:raise ValueError('Counter delta differs from raw values')
        pin=f'EldenRoot: {name} complete SHA256 accepted;';start=f'ELDEN_UFS_IDLE prepare name={name} '
        if text.count(pin)!=1 or text.count(start)!=1 or text.index(pin)>text.index(start):raise ValueError('Missing pinned image before idle test')
        if text.count(f'ELDEN_UFS_IDLE end name={name} good=1 transitions=16')!=1:raise ValueError('Incomplete per-window proof')
    stops=re.findall(r'^ELDEN_UFS_IDLE stop=(-?\d+) phase=(\d+) error=(\d+) active=(\d+)$',text,re.M)
    return {'rows':rows,'hardware_enters':sum(r['enters'] for r in rows),'hardware_exits':sum(r['exits'] for r in rows),
            'restored':stops==[('0','4','0','0')],'stop_records':stops,'limits':'Counters and authenticated read-after-idle, not total tablet energy savings or complete charger-cycle acceptance.'}
def analyze(run):
    identity=assess(run)
    if identity['profile']!='ufs-idle-trial':raise ValueError('Wrong profile')
    text=next((run/'usb').glob('*.bin')).read_bytes().decode(errors='replace').replace('\r','');result=parse(text)
    supervisor=json.loads((run/'supervisor.json').read_text());restore=json.loads((run/'restore/result.json').read_text())
    stock=restore.get('success') and restore.get('full_readback_sha256')=='8b8e72dad85a65d3bf6fc2c6b2a88064d0487e4696ae578e9fd4c46a33565890'
    good=bool(result['restored'] and identity['reset_after_sync'] and supervisor.get('complete') and stock and 'BSD root:' in text)
    return {'passed':good,'idle':result,'identity':identity,'stock_restored':bool(stock)}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=analyze(a.run)
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps({'passed':r['passed'],'enters':r['idle']['hardware_enters'],'exits':r['idle']['hardware_exits'],'restored':r['idle']['restored'],'dropped':r['identity']['dropped']}))
if __name__=='__main__':main()
