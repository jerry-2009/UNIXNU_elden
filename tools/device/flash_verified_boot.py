"""Y700 boot_a-only iteration writer. Default is offline; --write selects the live operation.

The live path requires HA2A1PT2 already in fastboot slot a, a positive native
battery-soc-ok result and a valid battery-voltage reading, the known COM7/1-5
programmer connection, exact stock AVB admission, fresh GPT and full readback.
Start the session-bound USB logger separately before invoking --write.
"""
import argparse,datetime,hashlib,json,os,re,struct,subprocess,sys,time,zlib
from pathlib import Path
import minifh as fh
from avb_guard import check_image,metadata
from firehose_transport import delta_plan

ROOT=None
FASTBOOT=Path('D:/Desktop/Git/SchoolBox/Tools/platform-tools_ADB/fastboot.exe')
SERIAL='HA2A1PT2'
STOCK_CHARGE_RESTORE_SHA='8b8e72dad85a65d3bf6fc2c6b2a88064d0487e4696ae578e9fd4c46a33565890'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fastboot(*args):
    r=subprocess.run([FASTBOOT,'-s',SERIAL,*args],capture_output=True,text=True,timeout=15)
    if r.returncode:raise RuntimeError(r.stdout+r.stderr)
    return r.stdout+r.stderr

def getvar_value(text,name):
    values=re.findall(r'^(?:\(bootloader\)\s*)?'+re.escape(name)+r':\s*(\S+)\s*$',text,re.M)
    if len(values)!=1:raise RuntimeError('missing or ambiguous fastboot '+name)
    return values[0]

def read_fastboot_power(command=fastboot):
    raw=getvar_value(command('getvar','battery-voltage'),'battery-voltage')
    if not re.fullmatch(r'[0-9]+',raw):raise RuntimeError('invalid fastboot battery-voltage')
    mv=int(raw)
    if not 1000<=mv<=20000:raise RuntimeError('implausible fastboot battery-voltage')
    ok=getvar_value(command('getvar','battery-soc-ok'),'battery-soc-ok')
    if ok not in ('yes','no'):raise RuntimeError('invalid fastboot battery-soc-ok')
    return dict(battery_mv=mv,battery_soc_ok=ok)

def require_fastboot_power(power):
    if power['battery_mv']<3500:
        raise RuntimeError('User voltage floor3500mV: switch to offline work; no experimental write')
    if power['battery_soc_ok']!='yes':
        raise RuntimeError('Y700 battery-soc-ok='+power['battery_soc_ok']+' at '+str(power['battery_mv'])+
                           ' mV; charge the device before a write')

def open_verified_edl_port(timeout=20,enumerate_ports=None,open_fn=None,now=None,pause=None):
    """Wait through COM creation only; never retry after Sahara/programming starts."""
    from serial.tools import list_ports
    import serial
    enumerate_ports=enumerate_ports or list_ports.comports;open_fn=open_fn or fh.open_port
    now=now or time.monotonic;pause=pause or time.sleep;deadline=now()+timeout;attempts=0
    def matches():
        # pyserial adds :x.<interface> when Windows exposes USBMI. The observed
        # QDLoader has interface3 on the same physical1-5 path; admit only that
        # proven spelling alongside the legacy spelling, never arbitrary suffixes.
        return len([q for q in enumerate_ports() if q.device=='COM7' and (q.vid,q.pid)==(0x05c6,0x9008) and q.location in ('1-5','1-5:x.3')])==1
    while now()<deadline:
        if matches():
            attempts+=1
            try:port=open_fn('COM7')
            except (serial.SerialException,OSError) as error:
                # PnP may publish COM7 before its device handle is openable.
                # Access denied or other errors can indicate another owner;
                # do not hide those failures or touch any other port.
                if not (getattr(error,'errno',None)==2 or 'FileNotFoundError(2,' in str(error)):raise
            else:
                if matches():return port,attempts
                port.close() # identity disappeared before any protocol bytes
        pause(.25)
    raise RuntimeError('expected Y700 COM7/05c6:9008/location1-5 not openable; attempts='+str(attempts))

def check_gpt(b):
    h=bytearray(b[4096:8192]);assert h[:8]==b'EFI PART'
    rev,size,expected=struct.unpack_from('<III',h,8)
    assert rev==0x10000 and 92<=size<=4096
    struct.pack_into('<I',h,16,0);assert zlib.crc32(h[:size])==expected
    assert struct.unpack_from('<QQ',h,24)==(1,1048575)
    table,n,esize,crc=struct.unpack_from('<QIII',h,72)
    assert table==2 and 0<n<=128 and esize==128
    entries=b[table*4096:table*4096+n*esize]
    assert len(entries)==n*esize and zlib.crc32(entries)==crc
    found=[]
    for i in range(n):
        e=entries[i*esize:(i+1)*esize]
        if e[:16]!=bytes(16) and e[56:128].decode('utf-16-le').split('\0')[0]=='boot_a':
            found.append(struct.unpack_from('<QQ',e,32))
    assert found==[(113318,137893)]

def main():
    global ROOT
    if sys.flags.optimize:raise SystemExit('Run without -O; validation assertions must remain enabled')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workbench',type=Path,required=True,help='Owner workbench containing signing/ and edl_work/')
    p.add_argument('image',type=Path);p.add_argument('reference',type=Path)
    p.add_argument('--write',action='store_true');p.add_argument('--expect-sha')
    p.add_argument('--restore-stock-for-charge',action='store_true',help='explicit owner-authorized low-battery exception for the fixed verified stock Android boot only; minimum3300mV')
    p.add_argument('--output',type=Path)
    a=p.parse_args();ROOT=a.workbench.resolve(strict=True);image=a.image.resolve();reference=a.reference.resolve()
    if a.write and (ROOT/'maintenance/IN_PROGRESS.json').exists():
        p.error('workbench maintenance is active; live device writes are disabled')
    checked=check_image(image,'boot_a')
    for directory in image.parents:
        if not directory.is_relative_to(ROOT):break
        withdrawn=directory/'withdrawn.json'
        if withdrawn.is_file():
            record=json.loads(withdrawn.read_text())
            if record.get('withdrawn') and record.get('image_sha256')==checked.sha256:
                raise RuntimeError('Candidate withdrawn: '+record.get('reason','see '+str(withdrawn)))
    if a.restore_stock_for_charge and (not a.write or checked.sha256!=STOCK_CHARGE_RESTORE_SHA):
        p.error('charge restoration is restricted to --write of the fixed verified stock boot image')
    assert checked.bytes==100663296 and reference.stat().st_size==100663296
    assert metadata(image)['props']==metadata(ROOT/'signing/phase5_resign/boot_signed.img')['props']
    reference_sha=sha(reference)
    plan=delta_plan(image.read_bytes(),reference.read_bytes())
    summary=dict(image=str(image),image_sha256=checked.sha256,reference_sha256=reference_sha,
        index=checked.index,footer_location=checked.location,serial=SERIAL,
        changed_sectors=plan['changed_sectors'],planned_write_sectors=plan['write_sectors'],
        only_disk_target='boot_a LUN4:113318+24576')
    print(json.dumps(summary,indent=2),flush=True)
    if not a.write:return
    if a.expect_sha!=checked.sha256:p.error('--write requires the independently reviewed image SHA256')
    if checked.sha256==reference_sha:p.error('unchanged candidate; use reboot without another flash')
    if not a.output:p.error('--write requires a fresh --output directory')
    out=a.output.resolve()
    if not out.is_relative_to(ROOT/'edl_work') or out.exists():p.error('output must be a new directory under this project edl_work')
    out.mkdir(parents=True)
    report=dict(summary,started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),success=False,
                edl_opened=False,programmer_uploaded=False,nand_write_started=False)
    port=None
    try:
        assert sha(image)==checked.sha256 and sha(reference)==reference_sha
        assert 'current-slot: a' in fastboot('getvar','current-slot')
        report['power']=read_fastboot_power()
        if a.restore_stock_for_charge:
            samples=[report['power']]
            for _ in range(2):
                time.sleep(1);samples.append(read_fastboot_power())
            if min(q['battery_mv'] for q in samples)<3300:raise RuntimeError('stock charge restoration requires voltage at least3300mV')
            if max(q['battery_mv'] for q in samples)-min(q['battery_mv'] for q in samples)>50:raise RuntimeError('unstable battery voltage; restoration stopped')
            report['power_samples']=samples
            report['stock_charge_restore_low_soc_authorized']=True
        else:
            require_fastboot_power(report['power'])
        fastboot('oem','edl')
        report['programmer_sha256']=sha(Path(fh.MELF))
        report['edl_opened']=False
        port,report['edl_open_attempts']=open_verified_edl_port()
        report['edl_opened']=True
        if not fh.sahara_upload(port,fh.MELF):raise RuntimeError('programmer upload failed')
        report['programmer_uploaded']=True
        time.sleep(1);fh.configure(port)
        fh.read_part(port,4,0,6,out/'lun4-main-before.bin')
        check_gpt((out/'lun4-main-before.bin').read_bytes())
        assert sha(image)==checked.sha256 and sha(reference)==reference_sha
        report['nand_write_started']=True # conservative from the first possible write
        if not fh.program_delta(port,4,113318,24576,image,reference,'verified-boot_a'):
            raise RuntimeError('write did not complete')
        digest=fh.target_sha256(port,4,113318,24576)
        if digest is None:
            fh.read_part(port,4,113318,24576,out/'boot-readback.img');digest=sha(out/'boot-readback.img')
        if digest!=checked.sha256:raise RuntimeError('full device readback hash differs')
        report.update(success=True,full_readback_sha256=digest,gpt_identity_checked=True)
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        fh.reset(port);report['reset_sent']=True
        print('Verified boot_a and reset '+SERIAL,flush=True)
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        if port:port.close()
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
