"""Verify published media properties and the existing kernel's ioctl outcomes."""
from pathlib import Path
import argparse,json,re,statistics
from assess_pd_power import assess
def analyze(run):
    pd=assess(run)
    if pd['profile']!='storage-medium':raise ValueError('Wrong storage profile')
    text=next((run/'usb').glob('*.bin')).read_bytes().decode('utf-8',errors='replace').replace('\r','')
    published=[{'medium':a,'solid':int(b),'bytes':int(c)} for a,b,c in re.findall(r'^ELDEN_STORAGE medium=(ufs|ram) solid=(\d+) bytes=(\d+)$',text,re.M)]
    ioctls=[{'unit':int(a),'mask':b,'isssd':int(c)} for a,b,c in re.findall(r'^spec_open : si_devbsdunit initialized to \((\d+)\), throttle_mask is \((0x[0-9a-f]+)\), isssd is \((\d+)\)$',text,re.M)]
    expected={('ram',536870912),('ufs',3303014400),('ufs',6077546496)}
    pub_ok=len(published)==3 and {(x['medium'],x['bytes']) for x in published}==expected and all(x['solid']==1 for x in published)
    ioctl_ok={(x['unit'],x['mask']) for x in ioctls}=={(0,'0x3'),(2,'0xc'),(4,'0x30')} and len(ioctls)==6 and all(x['isssd']==1 for x in ioctls)
    copies=[int(t)/19200 for t in re.findall(r'^ELDEN_DISPLAY CPU copy bytes=23152640 ticks=(\d+)$',text,re.M)]
    currents=[int(x) for x in re.findall(r'^ELDEN_BATTERY published cycle=\d+ percent=\d+ mv=\d+ ma=(-?\d+) ',text,re.M)]
    return {'pd':pd,'properties_verified':pub_ok,'ioctl_verified':ioctl_ok,'published':published,'ioctls':ioctls,'bsd_root':re.findall(r'^BSD root: (.*)$',text,re.M),'display_copy':{'samples':len(copies),'median_ms':statistics.median(copies) if copies else None},'battery_tail10':{'samples':len(currents[-10:]),'median_published_ma':statistics.median(currents[-10:]) if currents else None},'limits':'The actual 17 kernel recorded SSD classification; mount flags were not separately read. No storage throughput, tail-latency or power-saving benchmark is claimed; memory-backed Data is not persistent flash. Drops remain reported.'}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=analyze(a.run)
    with a.output.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps({k:r[k] for k in ('properties_verified','ioctl_verified','display_copy','battery_tail10')}))
if __name__=='__main__':main()
