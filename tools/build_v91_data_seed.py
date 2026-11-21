#!/usr/bin/env python3
"""Create the initial v91 APFS Data fixture from the verified original OS image.

Only newly created regular image files are modified. The volume UUID adjustment
is limited to checksummed, unencrypted APFS volume superblocks. The default stays
512MiB; the explicit 2048MiB variant requires separately qualified native guards.
"""
from pathlib import Path
import argparse,hashlib,json,os,plistlib,shutil,stat,struct,subprocess,uuid
from seed_ownership import audit_image
ROOT=Path(__file__).resolve().parents[1];PROFILE=ROOT/'profiles/v91/boot-build/data-seed.json'
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while block:=f.read(8<<20):h.update(block)
    return h.hexdigest()
def attach(image,mount):
    info=plistlib.loads(subprocess.check_output(['hdiutil','attach','-readonly' if mount.name=='verify-mount' or mount.name=='os-mount' else '-readwrite','-nobrowse','-owners','off','-imagekey','diskimage-class=CRawDiskImage','-mountpoint',str(mount),'-plist',str(image)]))
    entities=info['system-entities'];volumes=[v for v in entities if v.get('mount-point')==str(mount)]
    if len(volumes)!=1:raise RuntimeError('Unexpected owned-image mount')
    return next(v['dev-entry'] for v in entities if 'dev-entry' in v)
def detach(dev):subprocess.run(['hdiutil','detach',dev],check=True,stdout=subprocess.DEVNULL)
def fletcher(block):
    a=b=0;mod=0xffffffff
    for value in struct.unpack('<1022I',block[8:]):a=(a+value)%mod;b=(b+a)%mod
    x=mod-(a+b)%mod;y=mod-(a+x)%mod;return (y<<32)|x
def retag_copy(source,dest,old_uuid,new_uuid,*,expected_bytes=536870912):
    if expected_bytes not in (536870912,2147483648) or source.stat().st_size!=expected_bytes or dest.exists() or not source.is_file():raise RuntimeError('Only a fresh explicitly sized seed image copy is permitted')
    old=uuid.UUID(old_uuid).bytes;new=uuid.UUID(new_uuid).bytes;changed=[]
    with source.open('rb') as src,dest.open('xb') as target:
        offset=0
        while block:=src.read(4096):
            if len(block)!=4096:raise RuntimeError('Partial APFS block')
            if block[32:36]==b'APSB':
                if struct.unpack_from('<I',block,24)[0]&0xffff!=13 or block[240:256]!=old or not struct.unpack_from('<Q',block,264)[0]&1 or fletcher(block)!=struct.unpack_from('<Q',block)[0]:raise RuntimeError('Unexpected, encrypted or corrupt APFS superblock')
                data=bytearray(block);data[240:256]=new;struct.pack_into('<Q',data,0,fletcher(data));block=bytes(data);changed.append(offset)
            if block==bytes(4096):target.seek(4096,1)
            else:target.write(block)
            offset+=4096
        target.truncate(offset)
    if not changed:raise RuntimeError('No volume superblock found')
    return changed
def verify_tree(mount,profile):
    observed={}
    for root,dirs,files in os.walk(mount,followlinks=False):
        if Path(root)==mount:dirs[:]=[n for n in dirs if n not in profile['ignored_host_metadata']]
        for name in dirs+files:
            path=Path(root)/name;s=path.lstat();rel=path.relative_to(mount).as_posix();item={'mode':stat.S_IMODE(s.st_mode)}
            if path.is_symlink():item.update(kind='symlink',target=os.readlink(path))
            elif path.is_dir():item['kind']='directory'
            elif path.is_file():item.update(kind='file',bytes=path.stat().st_size,sha256=digest(path))
            else:raise RuntimeError('Unexpected fixture file type')
            observed[rel]=item
    expected={name:{k:v for k,v in item.items() if k not in ('uid','gid')} for name,item in profile['entries'].items()}
    if observed!=expected:
        different=[n for n in set(observed)|set(expected) if observed.get(n)!=expected.get(n)]
        raise RuntimeError('Data fixture logical mismatch: '+', '.join(sorted(different)[:12]))
    return len(observed)
def pack(source,dest):
    extents=[];offset=0
    with source.open('rb') as f:
        while data:=f.read(4096):
            if data!=bytes(4096):
                if extents and extents[-1][0]+extents[-1][1]==offset:extents[-1][1]+=4096
                else:extents.append([offset,4096])
            offset+=4096
    with dest.open('xb') as target,source.open('rb') as src:
        target.write(struct.pack('<8sIIQQ',b'DBRDISK1',1,4096,offset,len(extents)))
        for start,count in extents:target.write(struct.pack('<QQ',start,count))
        for start,count in extents:src.seek(start);target.write(src.read(count))
    return len(extents)
def verify_filesystem(raw,out):
    with raw.open('rb') as f:
        head=f.read(4096)
        if head[32:36]!=b'NXSB' or struct.unpack_from('<3Q',head,48)!=(0,0,2):raise RuntimeError('Container features differ from the accepted seed')
        f.seek(0);features=set()
        while block:=f.read(4096):
            if block[32:36]==b'APSB':features.add(struct.unpack_from('<3Q',block,40))
    if features!={(2,0,1)}:raise RuntimeError('Volume features differ from the accepted seed')
    info=plistlib.loads(subprocess.check_output(['hdiutil','attach','-readonly','-nomount','-nobrowse','-imagekey','diskimage-class=CRawDiskImage','-plist',str(raw)]));dev=next(v['dev-entry'] for v in info['system-entities'] if 'dev-entry' in v)
    try:
        check=subprocess.run(['/sbin/fsck_apfs','-n',dev],capture_output=True,text=True)
        (out/'fsck-readonly.log').write_text(check.stdout+check.stderr)
    finally:detach(dev)
    if check.returncode:raise RuntimeError('Read-only APFS filesystem verification failed')
    return {'fsck_returncode':0,'apfs_feature_flags_match_baseline':True}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--os-image',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--size-mib',type=int,choices=(512,2048),default=512,help='Explicit seed capacity;2048 requires a new kernel/boot qualification')
    a=p.parse_args();expected_bytes=a.size_mib*1024*1024
    profile=json.loads(PROFILE.read_text());source=a.os_image.resolve(strict=True);out=a.output.resolve()
    if out.exists() or str(source).startswith('/dev/'):raise RuntimeError('Use an original OS image and a new output directory')
    if os.geteuid() not in (0,501):raise RuntimeError('Run as the fixture owner UID501 or as root, only inside owned disk images')
    if digest(source)!=profile['original_os_sha256']:raise RuntimeError('Original OS image identity mismatch')
    out.mkdir(parents=True);om=out/'os-mount';dm=out/'data-mount';vm=out/'verify-mount'
    for d in (om,dm,vm):d.mkdir()
    image=out/'formatted.cdr';osdev=datadev=None
    try:
        osdev=attach(source,om)
        subprocess.run(['hdiutil','create','-size',str(a.size_mib)+'m','-layout','NONE','-fs','APFS','-volname','EldenData','-type','UDTO',str(image)],check=True,stdout=subprocess.DEVNULL)
        datadev=attach(image,dm);info=plistlib.loads(subprocess.check_output(['diskutil','info','-plist',str(dm)]));old_uuid=info['VolumeUUID']
        for name,item in sorted(profile['entries'].items(),key=lambda p:(len(Path(p[0]).parts),p[0])):
            target=dm/name
            if not target.resolve().is_relative_to(dm):raise RuntimeError('Fixture path escapes mount')
            target.parent.mkdir(parents=True,exist_ok=True)
            if item['kind']=='directory':target.mkdir(exist_ok=True)
            elif item['kind']=='symlink':os.symlink(item['target'],target)
            else:
                original=om/'private/var'/name
                if original.is_file() and not original.is_symlink() and original.resolve().is_relative_to(om) and digest(original)==item['sha256']:shutil.copyfile(original,target)
                elif name in profile['preferences']:
                    value=profile['preferences'][name];variants=[plistlib.dumps(value,fmt=plistlib.FMT_BINARY,sort_keys=s) for s in (True,False)]
                    data=next((b for b in variants if hashlib.sha256(b).hexdigest()==item['sha256']),None)
                    if data is None:raise RuntimeError('Preference encoding differs: '+name)
                    target.write_bytes(data)
                else:raise RuntimeError('Required content is not in the original OS: '+name)
            # Match the original owners-off creation semantics: children store
            # anonymous 99:99, not the host's projected stat() UID/GID.
            if item['kind']!='symlink':os.chmod(target,item['mode'])
        os.chmod(dm,profile['root']['mode']);os.chown(dm,profile['root']['uid'],profile['root']['gid'])
        verify_tree(dm,profile)
    finally:
        for dev in (datadev,osdev):
            if dev:detach(dev)
    raw=out/'data.raw';changed=retag_copy(image,raw,old_uuid,profile['volume_uuid'],expected_bytes=expected_bytes);dev=None
    try:
        dev=attach(raw,vm);info=plistlib.loads(subprocess.check_output(['diskutil','info','-plist',str(vm)]))
        if info['VolumeUUID'].upper()!=profile['volume_uuid']:raise RuntimeError('APFS volume identity did not survive retag')
        count=verify_tree(vm,profile)
        live_inodes={name:(vm/name).lstat().st_ino for name in profile['entries']}
        live_inodes['.']=vm.lstat().st_ino
        raw_owners=audit_image(raw,live_inodes,profile)
        space=os.statvfs(vm);host_available_bytes=space.f_bavail*space.f_frsize
    finally:
        if dev:detach(dev)
    packed=out/'data.packed';extents=pack(raw,packed)
    report={'logical_manifest_sha256':digest(PROFILE),'logical_entries_verified':count,'volume_uuid':profile['volume_uuid'],'raw_sha256':digest(raw),'packed_sha256':digest(packed),'packed_bytes':packed.stat().st_size,'expanded_bytes':raw.stat().st_size,'extent_count':extents,'retagged_superblocks':changed,'only_new_image_files_modified':True,'host_journal_contents_not_copied':True,'hardware_tested':False,'tablet_operation':False,
        'requested_size_mib':a.size_mib,'host_available_bytes_after_seed':host_available_bytes,'requires_expanded_native_qualification':a.size_mib!=512}
    report.update(verify_filesystem(raw,out))
    report.update(raw_owners_verified=raw_owners,live_inodes=live_inodes,raw_ownership=profile['raw_ownership'])
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='live_inodes'},indent=2))
if __name__=='__main__':main()
