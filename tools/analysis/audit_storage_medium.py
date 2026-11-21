"""Bind nonrotating-media semantics to public IOStorage and the actual XNU inputs."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[2]
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--xnu-source',type=Path);p.add_argument('--family-repository',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.xnu_source and not a.family_repository:p.error('Supply a source input')
    report={'hardware':False,'limits':'Source/ABI evidence only; the existing spec_open log is used for actual ioctl outcomes.'}
    if a.xnu_source:
        plan=json.loads((ROOT/'profiles/v91/object-build/plan.json').read_text());rows={}
        for path in ('bsd/sys/disk.h','bsd/miscfs/specfs/spec_vnops.c','bsd/vfs/vfs_subr.c'):
            item=[v for v in plan['providers'].values() if v.get('kind')=='reconstructed-xnu' and v.get('path')==path];assert len(item)==1
            data=(a.xnu_source/path).read_bytes();assert sha(data)==item[0]['sha256'];rows[path]={'sha256':sha(data),'bytes':len(data)}
        disk=(a.xnu_source/'bsd/sys/disk.h').read_text();assert re.search(r"#define DKIOCISSOLIDSTATE\s+_IOR\('d', 79, uint32_t\)",disk)
        spec=(a.xnu_source/'bsd/miscfs/specfs/spec_vnops.c').read_text();periods={}
        for tier in (1,2,3):
            for kind in ('','SSD_'):
                key=f'LOWPRI_TIER{tier}_IO_PERIOD_{kind}MSECS';m=re.search(r'#define '+key+r'\s+(\d+)',spec);assert m;periods[key]=int(m[1])
        assert 'info->throttle_io_periods = &throttle_io_period_ssd_msecs[0];' in spec and 'vp->v_un.vu_specinfo->si_isssd = isssd ? 1 : 0;' in spec
        vfs=(a.xnu_source/'bsd/vfs/vfs_subr.c').read_text();at=vfs.index('VNOP_IOCTL(devvp, DKIOCISSOLIDSTATE');assert 'mp->mnt_kern_flag |= MNTK_SSD;' in vfs[at:at+220]
        report['xnu_sources']=rows;report['ioctl']=hex(0x40000000|(4<<16)|(ord('d')<<8)|79);report['default_period_ms']=periods;report['mount_sets_mntk_ssd']=True
    if a.family_repository:
        rows=[]
        for tag,commit in [('312','0993ad6b36e85774fb0bc280e7d795f6dcbc641c'),('315','e45fbe30a7879e0b16e26dddb78538f1b00e0bff'),('337.100.1','7edb88fbae296fb7c8ce2f64e115e116e566d51c')]:
            data=subprocess.check_output(['git','-C',str(a.family_repository),'show',commit+':IOMediaBSDClient.cpp']);text=data.decode();start=text.index('        case DKIOCISSOLIDSTATE:');end=text.index('        } break;',start)+len('        } break;');body=text[start:end]
            for token in ('kIOPropertyDeviceCharacteristicsKey','gIOServicePlane','kIOPropertyMediumTypeKey','kIOPropertyMediumTypeSolidStateKey','*(uint32_t *)data = true;'):assert token in body
            rows.append({'tag':tag,'commit':commit,'file_sha256':sha(data),'case_sha256':sha(body.encode())})
        assert len({r['case_sha256'] for r in rows})==1;report['family_sources']=rows;report['same_ioctl_body']=True
    with a.output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('xnu_sources','family_sources')}))
if __name__=='__main__':main()
