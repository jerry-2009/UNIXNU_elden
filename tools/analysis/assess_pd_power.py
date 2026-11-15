"""Assess current clean-build PD handoff logs without a legacy packet.json."""
from pathlib import Path
import argparse,hashlib,json,re

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def assess(run):
    metas=list((run/'usb').glob('*.json'))
    if len(metas)!=1:raise ValueError('Expected one capture')
    meta=read(metas[0]);raw=metas[0].with_suffix('.bin');data=raw.read_bytes()
    if not meta.get('elapsed_seconds') or meta.get('raw_sha256')!=sha(raw):raise ValueError('Incomplete or changed capture')
    flash=read(run/'flash/result.json');image=Path(flash['image']);build=read(image.parent/'result.json');audit=read(image.parent/'audit.json')
    digest=sha(image);session=meta['candidate_session']
    if not flash['success'] or flash['full_readback_sha256']!=digest or build['image_sha256']!=digest or audit['image_sha256']!=digest or not audit['accepted_static']:
        raise ValueError('Image/readback/audit mismatch')
    profile=build['bluetooth_runtime']['profile']
    if build['session']!=session or audit['session']!=session or profile not in ('pd-power-trial','pd-gui','cpu-power-observation','cpu-governor','storage-medium'):raise ValueError('Wrong candidate')
    if profile=='pd-gui' and (not build['bluetooth_runtime'].get('menu_only_gui') or build['bluetooth_runtime'].get('native_profile')!='pd-power-trial' or audit['bluetooth_runtime']['profile']!='pd-gui'):raise ValueError('Wrong GUI qualification')
    text=data.decode('utf-8',errors='replace').replace('\r','');lines=text.splitlines()
    if set(re.findall(r'ELDEN STATUS v1 session=([0-9a-f]{16})',text))!={session}:raise ValueError('Mixed session')
    boots=set(re.findall(r'ELDEN STATUS v1 session='+session+r' boot=([0-9a-f]{16})',text))
    if len(boots)!=1 or meta.get('boot_nonce') not in boots:raise ValueError('Mixed boot')
    phases=[];gates=[];observations=[];first_measurement=None;finished=None
    for index,line in enumerate(lines):
        m=re.fullmatch(r'ELDEN_PD_BOOT phase=(\d+) error=(\d+) pulse=(\d+) high=(\d+) cycle=(\d+) deadline=(\d+) suspend=(\d+) restored=(\d+)',line)
        if m:phases.append(dict(line=index,**dict(zip(['phase','error','pulse','high','cycle','deadline','suspend','restored'],map(int,m.groups())))))
        m=re.fullmatch(r'ELDEN_PD_GATE cycle=(\d+) phase=(\d+) qualified=(\d+) raw=(\d+) ucsi=(\d+) budget=(\d+) owned=(\d+) pending=(\d+) icl=(\d+)/(\d+) pulse=(\d+) high=(\d+) left=(\d+)',line)
        if m:gates.append(dict(zip(['cycle','phase','qualified','raw','ucsi','budget','owned','pending','applied','observed','pulse','high','left'],map(int,m.groups()))))
        m=re.fullmatch(r'ELDEN_PD_POWER state=(\d+) phase=(\d+) error=(\d+) epoch=(\d+) cycle=(\d+)',line)
        if m:observations.append(dict(line=index,**dict(zip(['state','phase','error','epoch','cycle'],map(int,m.groups())))))
        if line.startswith('ELDEN_BACKLIGHT load-phase=settle '):first_measurement=index
        if line.startswith('ELDEN_BACKLIGHT power-finished=0 restore=0 confirmed=1 '):finished=index
    complete=[p for p in phases if p['phase']==6 and p['error']==0 and p['restored']==1]
    zeros=[];interrupted=False;last_cycle=-1
    for g in gates:
        if g['phase']!=4:continue
        if g['cycle']<=last_cycle:continue
        last_cycle=g['cycle']
        if zeros and g['observed']!=0:interrupted=True
        if not g['pending'] and g['applied']==g['observed']==0:zeros.append(g['cycle'])
    pulses=re.findall(r'ELDEN_PD_PULSE low result=(-?\d+) elapsed-us=(\d+) held=(\d+)',text)
    attempted=any(p['phase']==2 for p in phases)
    pulse_ok=(len(pulses)==1 and int(pulses[0][0])==0 and int(pulses[0][1])<=1000000 and int(pulses[0][2])==0) if attempted else not pulses
    ready_before=first_measurement is not None and any(o['state']==2 and o['phase']==6 and o['error']==0 and o['line']<first_measurement for o in observations)
    observed_loss=first_measurement is not None and finished is not None and any(o['state']!=2 and first_measurement<=o['line']<=finished for o in observations)
    contracts=list(dict.fromkeys(l for l in lines if l.startswith('ELDEN_PD_CONTRACT port=2 result=0 ')))
    nine=any('type=0 range-mv=9000/9000 exact-v=1 requested-mv=9000 ' in l for l in contracts)
    return {'profile':profile,'session':session,'boot_nonce':next(iter(boots)),'image_sha256':digest,'raw_sha256':sha(raw),'bytes':len(data),
        'phases':phases,'zero_cycles':zeros,'zero_readback_interrupted':interrupted,'pulse_attempted':attempted,'pulse':pulses,'pulse_restored_or_unneeded':pulse_ok,
        'controller_completed':len(complete)==1 and len(zeros)>=2 and not interrupted and pulse_ok and nine,
        'pd_contracts':contracts,'pd_ready_observed':any(o['state']==2 for o in observations),
        'ready_before_measurement':ready_before if profile=='pd-power-trial' else None,'observation_loss_during_measurement':observed_loss if profile=='pd-power-trial' else None,
        'backlight_trial_finished':finished is not None if profile=='pd-power-trial' else None,'observations':observations,'stopped_cleanly':'ELDEN_PD_BOOT stop=1;' in text,
        'reset_after_sync':'ELDEN_RPC RESET_AFTER_SYNC' in text,'dropped':max(map(int,re.findall(r'\bdropped=(\d+)',text)),default=None),
        'discontinuities':meta.get('discontinuities',[]),'reconnections':meta.get('reconnections',[]),
        'limits':'Critical received markers and readbacks, not proof of every instant or individual-port watts. Character drops remain reported. Net charging is assessed separately from complete battery samples.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=assess(a.run)
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps({k:r[k] for k in ('controller_completed','ready_before_measurement','observation_loss_during_measurement','backlight_trial_finished','dropped','stopped_cleanly')}))
if __name__=='__main__':main()
