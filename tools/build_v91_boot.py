#!/usr/bin/env python3
"""Assemble a v91 candidate from explicit inputs; no old boot carrier or device I/O.

The FD, loader and packed Data fixture are checked against source-rebuilt
contracts. Producing this image is an offline check, not hardware acceptance.
"""
from pathlib import Path
import argparse,gzip,hashlib,json,os,shutil,struct,subprocess,sys,tomllib
ROOT=Path(__file__).resolve().parents[1];PROFILE=ROOT/'profiles/v91/boot-build'
sys.path[:0]=[str(ROOT/'tools/device'),str(ROOT/'tools/legacy-workbench'),str(ROOT/'scripts')]
from avb_guard import check_image,metadata
from icon_cpu_trust import append as append_trust
from boot_formats import Fat
from build_boot_shim import extract_alloc_sections
from darwinboot_preflight import adt_walk,parse_kernel
from verify_v91_assets import verify_loader,verify_packed_seed
from firmware_contract import verify_firmware
from fbwc_boot import template as boot_template,qualify as qualify_fbwc
from battery_boot import template as battery_template,verify as verify_battery_menu
import bt_runtime_boot
import hid_delivery_boot
HASHES={'fd':'e50e1d6e2be51367225d76d4e97b90d51ba7812193d99fd4d4d7dd9fdc2ee534','loader':'ae8e5938b22766b921f43f68e2ea63db028fb57ec1f3791edaf7db10f5825299','data':'483125a27280f17d91de594f951cee4216f4888b764525b74db0f61ed62d34b3'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def encode_adt(node):
    b=struct.pack('<II',len(node['properties']),len(node['children']))
    for p in node['properties']:
        name=p['name'].encode();value=bytes.fromhex(p['hex'])
        if len(name)>31:raise ValueError('ADT property name too long')
        b+=name.ljust(32,b'\0')+struct.pack('<I',len(value))+value+bytes(-len(value)%4)
    return b+b''.join(encode_adt(c) for c in node['children'])
def main():
    if sys.flags.optimize:raise SystemExit('Run without -O; validation assertions must remain enabled')
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('kernel','entry-report','fd','loader','data','library','agent','stock-boot','avbtool','key','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--clang',default='clang');p.add_argument('--wsl-distro',help='Use Linux filesystem/signing tools in this Windows WSL distribution')
    p.add_argument('--portable-fat',action='store_true',help='Use the repository FAT16 writer; no mtools, dosfstools or WSL')
    p.add_argument('--data-report',type=Path,help='Source-built Data seed filesystem/manifest verification')
    p.add_argument('--fbwc-report',type=Path,help='Explicit qualified v93 framebuffer build; adds only the bare fbwc option')
    p.add_argument('--battery-ui',action='store_true',help='Restore qualified battery UI; compact existing numeric-one flags without dropping options')
    p.add_argument('--wcn-report',type=Path)
    p.add_argument('--bt-runtime',type=Path)
    p.add_argument('--hid-report',type=Path,help='Explicit v100 result-bearing touch delivery build; retains the v94 menu')
    p.add_argument('--wait-sample',action='store_true',help='v106 only: enable existing bounded process-wait sampler')
    a=p.parse_args();out=a.output.resolve()
    def path(v):
        s=str(Path(v).resolve())
        if not a.wsl_distro:return s
        if len(s)<3 or s[1]!=':':raise ValueError('WSL paths require a Windows drive path')
        return '/mnt/'+s[0].lower()+s[2:].replace('\\','/')
    def run(cmd):subprocess.run((['wsl','-d',a.wsl_distro,'-u','root','--'] if a.wsl_distro else [])+cmd,check=True)
    if out.exists():raise RuntimeError('Output must be new')
    firmware_contract=verify_firmware(a.fd)
    loader_contract=verify_loader(a.loader)
    data_contract={'legacy_frozen_seed':True}
    if sha(a.data)!=HASHES['data']:
        if not a.data_report:raise RuntimeError('Rebuilt Data seed requires --data-report')
        data_contract=verify_packed_seed(a.data,a.data_report)
    if a.fd.stat().st_size!=4194304:raise RuntimeError('Firmware must be 4MiB')
    stock=check_image(a.stock_boot,'boot_a')
    if stock.sha256!='8b8e72dad85a65d3bf6fc2c6b2a88064d0487e4696ae578e9fd4c46a33565890':raise RuntimeError('Wrong stock contract')
    entry=json.loads(a.entry_report.read_text())
    if bool(a.wcn_report)!=bool(a.bt_runtime) or (a.wcn_report and (a.fbwc_report or a.battery_ui or a.hid_report)) or (a.hid_report and (a.fbwc_report or a.battery_ui)):raise ValueError('Select one qualified kernel profile')
    bt=bt_runtime_boot.qualify(a.wcn_report,a.entry_report,a.bt_runtime) if a.wcn_report else None
    hid=hid_delivery_boot.qualify(a.hid_report,a.entry_report) if a.hid_report else None
    fbwc=qualify_fbwc(a.fbwc_report,a.entry_report) if a.fbwc_report else None
    if sha(a.kernel)!=entry['derivative_sha256'] or entry['stub_bytes']!=104:raise RuntimeError('Kernel entry-transform identity mismatch')
    parse_kernel(a.kernel.read_bytes());out.mkdir(parents=True);assets=out/'files/EFI/UniXNU';payloads=assets/'Payloads';payloads.mkdir(parents=True)
    adt_config=json.loads((PROFILE/'adt.json').read_text());adt=encode_adt(adt_config['tree'])
    if hashlib.sha256(adt).hexdigest()!=adt_config['sha256']:raise RuntimeError('ADT encoding differs from v91')
    if bt:adt=encode_adt(bt_runtime_boot.adt(adt_config,bt)['tree'])
    if hid and hid['profile']=='v109-memory8':
        from memory_window_boot import adt as memory_adt
        adt=encode_adt(memory_adt(adt_config)['tree'])
    tree=adt_walk(adt)
    expected_window=hid.get('memory_window_bytes',0x180000000) if hid else 0x180000000
    if tree['window']!=expected_window or tree['gpuaddon'] is not None:raise RuntimeError('Unexpected memory/GPU configuration')
    (payloads/'kernel.macho.adt').write_bytes(adt)
    tc=json.loads((PROFILE/'trust-metadata.json').read_text());parts=[]
    for part in tc['parts']:parts.append(struct.pack('<I16sI',part['version'],bytes.fromhex(part['uuid_hex']),len(part['entries_hex']))+b''.join(bytes.fromhex(x) for x in part['entries_hex']))
    offset=4*(len(parts)+1);offsets=[]
    for part in parts:offsets.append(offset);offset+=len(part)
    trust=struct.pack('<I',len(parts))+struct.pack('<'+'I'*len(parts),*offsets)+b''.join(parts)
    if hashlib.sha256(trust).hexdigest()!=tc['base_sha256']:raise RuntimeError('Original trust metadata mismatch')
    trust,_=append_trust(trust,a.library.read_bytes());trust,_=append_trust(trust,a.agent.read_bytes())
    if hashlib.sha256(trust).hexdigest()!=tc['expected_v91_sha256']:raise RuntimeError('Trustcache is not the v91 contract')
    if bt:
        trust,_=append_trust(trust,(a.bt_runtime/'BlueTool').read_bytes())
        trust=bt_runtime_boot.augment_trust(trust,bt)
        if hashlib.sha256(trust).hexdigest()!=bt['trust_sha256']:raise ValueError('Runtime trust cache differs')
    (payloads/'kernel.macho.trustcache').write_bytes(trust)
    for source,dest in [(a.kernel,payloads/'kernel.macho'),(a.data,payloads/'data.packed'),(a.loader,assets/'EldenPayloadLoader.efi')]:shutil.copyfile(source,dest)
    template=boot_template(bool(fbwc or hid))
    if hid:template=hid_delivery_boot.menu(hid)
    if bt:template=bt_runtime_boot.menu(bt)
    wait_sample=None
    if a.wait_sample:
        if not hid or hid['profile']!='v106-rt-memory':raise ValueError('Wait capture requires v106')
        from wait_sample_boot import template as wait_template,verify as wait_verify
        before=template;template=wait_template(before);wait_sample=wait_verify(before,template)
    battery_ui=None
    if a.battery_ui:
        before=template;template=battery_template(before);battery_ui=verify_battery_menu(before,template)
    identity=a.kernel.read_bytes()+template.encode()+adt+hashlib.sha256(trust).digest()
    for input_file in (a.fd,a.loader,a.data):identity+=bytes.fromhex(sha(input_file))
    session=hashlib.sha256(identity).hexdigest()[:16];menu=template.replace('@SESSION@',session)
    config=tomllib.loads(menu)
    if config['boot']['default']!='xnu' or config['boot']['timeout']!=8 or any(len(e.get('args','').encode())>1023 for e in config['entry']):raise RuntimeError('Unexpected boot menu policy')
    (assets/'unixnu.toml').write_text(menu,encoding='utf-8',newline='\n')
    shim_source=ROOT/'patches/overlays/mu_wide_platforms/BootShim/BootShim.S';obj=out/'BootShim.o'
    run([a.clang,'--target=aarch64-none-elf','-c',path(shim_source),'-o',path(obj),'-DUEFI_BASE=0xFF300000','-DUEFI_SIZE=0x00400000','-DEMBEDDED_PAYLOAD_SIZE=58720256'])
    shim=extract_alloc_sections(obj.read_bytes())
    if len(shim)!=128 or hashlib.sha256(shim).hexdigest()!='ac27ecc2bcec5440606d77e69b7726921b0bf3803dd2234f23b10d1619149e1d':raise RuntimeError('BootShim differs from qualified v91')
    (out/'BootShim.bin').write_bytes(shim)
    image=out/'payload.img'
    expected={}
    if a.portable_fat:
        from fat16_payload import build
        files={f.relative_to(out/'files').as_posix():f.read_bytes() for f in (out/'files').rglob('*') if f.is_file()}
        image.write_bytes(build(files));expected={n:hashlib.sha256(v).hexdigest() for n,v in files.items()}
    else:
        with image.open('xb') as f:f.truncate(58720256)
        run(['mkfs.fat','--invariant','-F','16','-S','512','-s','4','-n','ELDENRAM',path(image)])
        for directory in ('EFI','EFI/UniXNU','EFI/UniXNU/Payloads'):run(['mmd','-i',path(image),'::/'+directory])
        for file in sorted((out/'files').rglob('*')):
            if not file.is_file():continue
            os.utime(file,(1738713600,1738713600));relative=file.relative_to(out/'files').as_posix();run(['mcopy','-m','-i',path(image),path(file),'::/'+relative]);expected[relative]=sha(file)
    fat=Fat(image.read_bytes())
    for name,h in expected.items():
        if hashlib.sha256(fat.read(name)).hexdigest()!=h:raise RuntimeError('FAT content differs: '+name)
    raw=shim+a.fd.read_bytes()+image.read_bytes();compressed=gzip.compress(raw,mtime=0)
    spec=json.loads((PROFILE/'android-header.json').read_text());header=bytearray(4096);header[:8]=b'ANDROID!'
    for offset,key in [(12,'ramdisk_size'),(16,'os_version'),(20,'header_size'),(40,'header_version'),(1580,'signature_size')]:struct.pack_into('<I',header,offset,spec[key])
    struct.pack_into('<I',header,8,len(compressed));header[44:44+len(spec['cmdline'].encode())]=spec['cmdline'].encode();boot=bytes(header)+compressed;boot+=bytes(-len(boot)%4096)
    unsigned=out/'boot.img';unsigned.write_bytes(boot);signed=out/'boot-signed.img';shutil.copyfile(unsigned,signed)
    meta=metadata(a.stock_boot);cmd=['python3' if a.wsl_distro else sys.executable,path(a.avbtool),'add_hash_footer','--image',path(signed),'--partition_name','boot','--partition_size','100663296','--algorithm','SHA256_RSA4096','--key',path(a.key),'--rollback_index','1738713600','--salt',meta['hashes']['boot'][1].hex()]
    for key,value in meta['props'].items():cmd+=['--prop',key+':'+value]
    run(cmd);checked=check_image(signed,'boot_a')
    if metadata(signed)['props']!=meta['props'] or checked.bytes!=100663296:raise RuntimeError('Stock signing properties changed')
    result={'kernel_sha256':sha(a.kernel),'image_sha256':checked.sha256,'rollback_index':checked.index,'footer_location':checked.location,'session':session,'fat_files':expected,'bootshim_sha256':hashlib.sha256(shim).hexdigest(),'external_assets':{name:sha(getattr(a,name)) for name in HASHES},'firmware_contract':firmware_contract,'loader_contract':loader_contract,'data_contract':data_contract,'assembled_without_old_boot_carrier':True,'hardware_tested':False,'device_operation':False,'full_asset_source_closure':not data_contract.get('legacy_frozen_seed',False)}
    if fbwc:result['framebuffer_experiment']=fbwc
    if battery_ui:result['battery_ui']=battery_ui
    if bt:result['bluetooth_runtime']=bt
    if hid:result['touch_delivery']=hid
    if wait_sample:result['wait_sample']=wait_sample
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('image_sha256','rollback_index','footer_location','session','full_asset_source_closure')},indent=2))
if __name__=='__main__':main()
