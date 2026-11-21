"""Assess actual early arming/adoption or passive watchdog-stall return evidence."""
from pathlib import Path
import argparse,datetime,json,re
from assess_pd_power import assess
def analyze(run):
    identity=assess(run);profile=identity['profile']
    if profile not in ('early-storage-guard','early-storage-stall'):raise ValueError('Wrong early guard profile')
    text=next((run/'usb').glob('*.bin')).read_bytes().decode('utf-8',errors='replace').replace('\r','')
    supervisor=json.loads((run/'supervisor.json').read_text());events=supervisor['events']
    def stamp(name):
        rows=[x for x in events if x['event']==name]
        if len(rows)!=1:return None
        return datetime.datetime.fromisoformat(rows[0]['utc'])
    arms=re.findall(r'ELDEN_VDOG EARLY_ARM session=([0-9a-f]+) rc=(-?\d+) state=(\d+) ctl=([0-9a-f]+) elapsed-ms=(\d+) expired=(\d+) calls=(\d+) op=([0-9a-f]+) raw=(-?\d+)',text)
    valid_arm=len(arms)==1 and arms[0][0]==identity['session'] and arms[0][1:3]==('0','1') and int(arms[0][3],16)&1 and arms[0][5]=='0'
    result={'identity':identity,'arm':arms,'arm_verified':bool(valid_arm),'supervisor_complete':supervisor.get('complete',False),'scope':'Kernel UFS-entry guard only; UEFI and earlier kernel stages are not covered.'}
    if profile=='early-storage-guard':
        adopts=re.findall(r'ELDEN_VDOG SMP_ADOPT session=([0-9a-f]+) rc=(-?\d+) state=(\d+) ctl=([0-9a-f]+) elapsed-ms=(\d+) expired=(\d+) calls=(\d+) op=([0-9a-f]+) raw=(-?\d+)',text)
        ordered='ELDEN_EARLY protected UFS entry;' in text and 'BSD root:' in text and text.index('ELDEN_VDOG EARLY_ARM')<text.index('ELDEN_EARLY protected UFS entry;')<text.index('BSD root:')
        good=len(adopts)==1 and adopts[0][0]==identity['session'] and adopts[0][1:3]==('0','1') and adopts[0][5]=='0'
        admitted='ELDEN_SMP action=2 phase=3 reason=0 expected=ff online=ff work=ff timers=ff ipis=ff error=0 vdog=1' in text
        result.update(adopt=adopts,early_before_root=ordered,eight_core_admission=admitted,normal_passed=bool(valid_arm and good and ordered and admitted and identity['reset_after_sync'] and supervisor.get('complete')))
    else:
        marker=stamp('stall-marker-observed');back=stamp('responsive-fastboot');delta=(back-marker).total_seconds() if marker and back else None
        marked='ELDEN_EARLY STALL before-ufs=1 irq-masked=1 no-periodic-pet=1 fallback-seconds=120' in text
        fallback='ELDEN_EARLY STALL_FALLBACK' in text
        no_root='BSD root:' not in text and 'ELDEN_VDOG SMP_ADOPT' not in text
        no_rpc='ELDEN_RPC ACK_COMMITTED' not in text and 'ELDEN_RPC RESET_AFTER_SYNC' not in text
        # Fastboot responsiveness includes bootloader/re-enumeration time; it
        # is not the watchdog's30s hardware interval. Use a30s margin before
        # the source's120s software fallback rather than an arbitrary45s cap.
        disruptions=identity['discontinuities']
        boundary=(datetime.datetime.fromisoformat(disruptions[0]['utc'])-marker).total_seconds() if disruptions and marker else None
        result.update(stall_marker=marked,fallback_observed=fallback,marker_to_responsive_fastboot_seconds=delta,no_root_or_adoption=no_root,no_pc_reboot_observed=no_rpc,
                      first_transport_error_after_marker_seconds=boundary,
                      stall_passed=bool(valid_arm and marked and not fallback and no_root and no_rpc and delta is not None and 20<=delta<90 and supervisor.get('complete')))
    return result
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=analyze(a.run)
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in r.items() if k not in ('identity','arm','adopt')}))
if __name__=='__main__':main()
