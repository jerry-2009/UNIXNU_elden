"""Y700 experimental USB CDC logger. Default is offline; --listen is explicit.

Only the experimental 1209:7004 / ELDEN-XNU device is admitted. No flash, partition operation, or shell command is sent. The default only
reads logs and optionally queries ping/status. --reboot-after-ready explicitly
requests one session-bound fastboot RPC after observed startup readiness.
--charge-sequence explicitly tests the board's charge modes and ends with a
verified stock-policy restore before the ready reboot.
"""
import argparse
import datetime
import json
from pathlib import Path
import time
import re
import os
import subprocess
import hashlib

VID,PID,SERIAL=0x1209,0x7004,'ELDEN-XNU'

def control_ready(kind,last_status,home_sent,home_release_ok,swipe_release_ok):
    if not last_status or last_status.get('fastboot')!='ready':return False
    return ((home_sent and home_release_ok) or swipe_release_ok) if kind=='tap-settings' else True

def control_request(value,session):
    if not isinstance(value,dict) or set(value)!={'id','session','command'}:
        raise ValueError('control request must contain id, session, command only')
    if not isinstance(value['id'],str) or not re.fullmatch('[a-z0-9-]{1,64}',value['id']):
        raise ValueError('invalid control request id')
    if value['session']!=session or value['command'] not in ('home','tap-settings','swipe-up','fastboot'):
        raise ValueError('wrong session or unsupported control command')
    return value['id'],value['command'],(value['command']+' '+session+'\n').encode('ascii')

class ConsoleLines:
    """Keep every complete line in large USB reads; bound only fragments."""
    def __init__(self,limit=16384):
        self.limit=limit;self.pending='';self.discarding=False;self.discarded=0
    def feed(self,text):
        if self.discarding:
            if '\n' not in text:return []
            text=text.split('\n',1)[1];self.discarding=False
        parts=(self.pending+text).split('\n');self.pending=parts.pop();complete=[]
        for line in parts:
            if len(line)<=self.limit:complete.append(line)
            else:self.discarded+=1
        if len(self.pending)>self.limit:
            self.pending='';self.discarding=True;self.discarded+=1
        return complete

class ChargeSequence:
    MODES={'stock':1,'bypass':2,'80':3,'40-60':4}
    MAX_GENERATION=0xffffffff
    def __init__(self,modes,delay,hold,*,max_status_gap):
        self.modes=modes;self.delay=delay;self.hold=hold;self.index=0;self.pending=None
        self.sent_at=None;self.applied_at=None;self.before=None;self.done=not modes
        self.max_status_gap=max_status_gap
        self.confirmed_sample=None
        self.recovering=False;self.recovery_deadline=None;self.restored=False;self.errors=[];self.events=[]
    def update(self,status,elapsed):
        if self.done:return None
        raw=status.get('charge_generation','')
        generation=int(raw) if isinstance(raw,str) and re.fullmatch(r'\d{1,10}',raw) else None
        if generation is not None and generation>self.MAX_GENERATION:generation=None
        mode=status.get('charge_mode')
        available=status.get('charge_control')=='1'
        if self.pending:
            # The kernel retains the last applied mode/generation after its
            # telemetry becomes unavailable. Those historical values cannot
            # confirm a new command or finish the observed hold interval.
            matches=available and generation is not None and generation>self.before and mode==str(self.MODES[self.pending])
            if self.confirmed_sample is not None:
                last_generation,last_seen=self.confirmed_sample
                if not matches or generation!=last_generation or elapsed-last_seen>self.max_status_gap:
                    self.events.append(dict(event='confirmation-lost',mode=self.pending,elapsed=elapsed))
                    self.applied_at=None
                    self.confirmed_sample=None
            confirmed=matches and (self.applied_at is not None or elapsed-self.sent_at<45)
            if confirmed:
                self.confirmed_sample=(generation,elapsed)
            if confirmed and self.applied_at is None:
                self.applied_at=elapsed;self.events.append(dict(event='applied',mode=self.pending,generation=generation,elapsed=elapsed))
            if self.applied_at is not None and elapsed-self.applied_at>=self.hold:
                self.index+=1;self.pending=None;self.applied_at=None
                self.confirmed_sample=None
                if self.index==len(self.modes):self.done=True;self.restored=True;return None
            elif self.applied_at is None and elapsed-self.sent_at>=45:
                self.errors.append('Unconfirmed charge command: '+self.pending)
                if self.recovering:self.done=True;return None
                self.modes=['stock'];self.index=0;self.pending=None;self.recovering=True;self.recovery_deadline=elapsed+45
        if self.pending:return None
        if self.recovering and elapsed>=self.recovery_deadline:self.done=True;return None
        if elapsed<self.delay or not available or generation is None:return None
        if generation==self.MAX_GENERATION:
            self.errors.append('Charge generation exhausted; no further command sent');self.done=True;return None
        self.pending=self.modes[self.index];self.before=generation;self.sent_at=elapsed
        self.events.append(dict(event='sent',mode=self.pending,before_generation=generation,elapsed=elapsed))
        return self.pending

class Milestone:
    def __init__(self,session):self.session=session;self.first=None;self.failed=False;self.confirmed=False
    def line(self,text,now):
        if re.search(r'\bpanic\s*\(|kernel data abort',text,re.I):self.failed=True;self.first=None;self.confirmed=False
        if not text.startswith('ELDEN STATUS v1 '):return None
        values=dict(item.split('=',1) for item in text.split()[3:] if '=' in item)
        expected={'configured':'1','dtr':'1','cache':'0','data':'0','init_exec':'1','user_trap':'1'}
        good=self.session and values.get('session')==self.session and all(values.get(k)==v for k,v in expected.items())
        if not good:self.first=None;self.confirmed=False
        elif not self.failed:
            if self.first is None:self.first=now
            if now-self.first>=10:self.confirmed=True
        return values

class BootContinuity:
    """Image session IDs are static; reconnect also requires a per-boot token."""
    def __init__(self,session,required=False):self.session=session;self.required=required;self.nonce=None
    def observe(self,status):
        if status.get('session')!=self.session:
            if self.required:raise RuntimeError('Reconnect session differs from the selected image')
            return
        nonce=status.get('boot','')
        if not re.fullmatch('[0-9a-f]{16}',nonce):
            if self.required:raise RuntimeError('Reconnect requires a target per-boot nonce')
            return
        if self.nonce is not None and nonce!=self.nonce:raise RuntimeError('Target rebooted or changed during capture; controls stopped')
        self.nonce=nonce

def reconnect_port(previous,ports,explicit=None):
    matches=[p for p in ports if (not explicit or p.device==explicit) and
             p.location==previous.location and admitted(p)]
    if len(matches)>1:raise RuntimeError('Ambiguous experimental USB identity on reconnect')
    return matches[0] if matches else None

def windows_instance_matches(port, records):
    """PySerial's Windows USB serial regex drops non-alphanumeric IDs such as ELDEN-XNU."""
    if not re.fullmatch(r'COM[0-9]+',port.device,re.I):return None
    if isinstance(records,dict):records=[records]
    matches=[r for r in (records or []) if r.get('FriendlyName','').endswith('('+port.device+')')]
    expected='USB\\VID_1209&PID_7004\\'+SERIAL
    if len(matches)==1 and matches[0].get('InstanceId','').upper()==expected:
        return matches[0]['InstanceId']
    return None

def admitted(port):
    if port.vid!=VID or port.pid!=PID:return False
    if port.serial_number==SERIAL:return True
    if port.serial_number or os.name!='nt':return False
    # A COM number or VID/PID alone is insufficient; require the exact live PnP identity.
    script='Get-PnpDevice -PresentOnly -Class Ports | Select-Object FriendlyName,InstanceId | ConvertTo-Json -Compress'
    try:
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
                              capture_output=True,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:return False
        instance=windows_instance_matches(port,json.loads(result.stdout.decode('utf-8-sig',errors='replace')))
    except (OSError,ValueError,subprocess.TimeoutExpired):return False
    if not instance:return False
    port.elden_verified_instance=instance
    return True

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--listen',action='store_true')
    p.add_argument('--port')
    p.add_argument('--seconds',type=int,default=300)
    p.add_argument('--wait-seconds',type=int,default=90)
    p.add_argument('--query',choices=['ping','status'])
    p.add_argument('--status-interval',type=float,default=0,help='optional read-only status query interval')
    p.add_argument('--expect-session',help='bind milestone observations to the candidate session ID')
    p.add_argument('--reboot-after-ready',action='store_true',help='send one session-bound fastboot command after 10s of healthy startup and an explicit ready capability')
    p.add_argument('--reboot-delay',type=int,default=0,help='minimum capture seconds before an explicitly requested ready reboot')
    p.add_argument('--home-after-ready',action='store_true',help='send one session-bound virtual HID Home after healthy startup, HID driver and a non-boot GUI frame')
    p.add_argument('--home-count',type=int,choices=(1,2),default=1,help='optional wake then unlock Home sequence, with confirmed release and spacing')
    p.add_argument('--control-file',type=Path,help='optional explicit session-bound JSON home/tap-settings/swipe-up/fastboot requests; never raw serial commands')
    p.add_argument('--charge-sequence',help='explicit comma-separated stock,bypass,80,40-60 sequence, ending with stock')
    p.add_argument('--charge-delay',type=int,default=60)
    p.add_argument('--charge-hold',type=int,default=15)
    p.add_argument('--output',type=Path,required=True,help='Explicit log directory outside the source repository')
    p.add_argument('--reconnect-seconds',type=int,default=0,help='optional bounded reconnect to the same physical device and boot; never repeats a control request')
    a=p.parse_args()
    if a.seconds<1 or a.wait_seconds<1 or a.status_interval<0 or not 0<=a.reboot_delay<a.seconds:p.error('invalid duration')
    if a.reboot_delay and not a.reboot_after_ready:p.error('reboot-delay requires reboot-after-ready')
    if a.expect_session and not re.fullmatch('[0-9a-f]{16}',a.expect_session):p.error('session must be 16 lowercase hex characters')
    if a.reboot_after_ready and (not a.listen or not a.expect_session or not a.status_interval):p.error('reboot needs --listen, --expect-session and --status-interval')
    if a.home_after_ready and (not a.listen or not a.expect_session or not a.status_interval):p.error('home needs --listen, --expect-session and --status-interval')
    if a.home_after_ready and a.reboot_after_ready:p.error('choose only one action')
    if a.home_count!=1 and not a.home_after_ready:p.error('home-count requires home-after-ready')
    if a.control_file and (not a.listen or not a.expect_session or not a.status_interval):p.error('control file requires a bound active status listener')
    if not 0<=a.reconnect_seconds<=60:p.error('reconnect-seconds must be0..60')
    if a.reconnect_seconds and (not a.listen or not a.expect_session or not a.status_interval or a.charge_sequence):p.error('reconnect requires bound status capture without a host charge sequence')
    charge_modes=a.charge_sequence.split(',') if a.charge_sequence else []
    if charge_modes:
        if not a.reboot_after_ready or not 1<=len(charge_modes)<=8 or charge_modes[-1]!='stock':p.error('charge tests require ready reboot and a final stock restore')
        if any(m not in ChargeSequence.MODES for m in charge_modes) or any(x==y for x,y in zip(charge_modes,charge_modes[1:])):p.error('invalid charge sequence')
        if not 0<=a.charge_delay<a.reboot_delay or not 5<=a.charge_hold<=60:p.error('invalid charge timing')
    if not a.listen:
        print('Offline ready: run --listen before booting the USB candidate. Expected 1209:7004, serial ELDEN-XNU.');return
    import serial
    from serial.tools import list_ports
    deadline=time.monotonic()+a.wait_seconds;selected=None
    while time.monotonic()<deadline:
        ports=[x for x in list_ports.comports() if admitted(x) and (not a.port or x.device==a.port)]
        if len(ports)>1:raise RuntimeError('multiple matching devices; specify --port')
        if ports:selected=ports[0];break
        time.sleep(.5)
    if selected is None:raise RuntimeError('CDC not detected; retain the device screen; do not infer no panic')
    a.output.mkdir(parents=True,exist_ok=True)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
    raw=a.output/(stamp+'.bin');meta=a.output/(stamp+'.json')
    report=dict(port=selected.device,vid=VID,pid=PID,serial=SERIAL,location=selected.location,
                raw_log=str(raw),bytes=0,query=a.query,device_operations='CDC read; optional ping/status only')
    report['verified_pnp_instance']=getattr(selected,'elden_verified_instance',None)
    if a.reboot_after_ready:report['device_operations']='CDC read/status; one explicitly requested session-bound fastboot RPC after readiness'
    if charge_modes:report['device_operations']='CDC read/status; explicit bounded charge-mode RPC sequence with stock restore and fastboot return'
    if a.home_after_ready:report['device_operations']='CDC read/status; explicit session-bound Home sequence'
    if a.control_file:report['device_operations']+='; explicit control-file home/tap-settings/swipe-up/fastboot commands'
    report['recovery_events']=[]
    s=serial.Serial(port=None,baudrate=115200,timeout=.15,write_timeout=2)
    s.port=selected.device;s.dtr=True;s.rts=False
    report['open_attempt_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    report['candidate_session']=a.expect_session
    meta.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Opening verified '+selected.device+'; configuring CDC and DTR...',flush=True)
    from cdc_open import open_verified
    def open_error(error):
        report.setdefault('open_errors',[]).append(str(error))
        report['bound_startup_milestone_observed']=False
        meta.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    selected,attempts=open_verified(s,selected,list_ports.comports,admitted,(serial.SerialException,OSError),open_error)
    report['open_attempts']=attempts
    report['verified_pnp_instance']=getattr(selected,'elden_verified_instance',None)
    started=time.monotonic();report['opened_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    tracker=Milestone(a.expect_session);lines=ConsoleLines();next_status=started+.5;report['statuses']=[]
    reboot_sent=False;home_sent=False;home_release_ok=False;swipe_release_ok=False;homes_sent=0;last_home_sent=0;hid_ready=False;gui_at=None;received_hash=hashlib.sha256()
    controls_seen=set();last_status=None;report['control_events']=[];report['milestones']=[];milestones_seen=set()
    charge=ChargeSequence(charge_modes,a.charge_delay,a.charge_hold,
                          max_status_gap=2*max(a.status_interval,.5))
    continuity=BootContinuity(a.expect_session,required=bool(a.reconnect_seconds))
    returning=False;report['discontinuities']=[];report['reconnections']=[]
    print('Connected '+selected.device+'; DTR asserted. Saving raw bytes to '+str(raw),flush=True)
    try:
        with raw.open('xb') as output:
            if a.query:s.write((a.query+'\n').encode('ascii'))
            while time.monotonic()-started<a.seconds:
                try:
                    if a.status_interval and not (reboot_sent or returning) and time.monotonic()>=next_status:
                        s.write(b'status\n');next_status=time.monotonic()+max(a.status_interval,.5)
                    if a.control_file and not (reboot_sent or returning) and tracker.confirmed and not tracker.failed and last_status:
                        try:
                            if a.control_file.stat().st_size>2048:raise ValueError('control file too large')
                            ident,kind,command=control_request(json.loads(a.control_file.read_text(encoding='utf-8')),a.expect_session)
                        except (OSError,ValueError):ident=None
                        if ident and ident not in controls_seen:
                            ready=control_ready(kind,last_status,home_sent,home_release_ok,swipe_release_ok)
                            if ready:
                                controls_seen.add(ident);output.flush();os.fsync(output.fileno())
                                report['control_events'].append(dict(id=ident,command=kind,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),state='send-attempt'))
                                meta.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
                                if kind=='fastboot':reboot_sent=True
                                if kind=='home':home_sent=True;homes_sent=a.home_count;home_release_ok=False;last_home_sent=time.monotonic()
                                if s.write(command)!=len(command):raise serial.SerialException('short control command write; no retry')
                                print('\nSent bound control '+kind+' id='+ident,flush=True)
                    data=s.read(32768)
                    if not data:continue
                    output.write(data);output.flush();report['bytes']+=len(data);received_hash.update(data)
                    decoded=data.decode('utf-8',errors='replace').replace('\r','');print(decoded,end='',flush=True)
                    for line in lines.feed(decoded):
                        status=tracker.line(line,time.monotonic())
                        if line.startswith(('ELDEN_RECOVERY DEADLINE_FIRED','ELDEN_RPC ACK_COMMITTED','ELDEN_RPC RESET_AFTER_SYNC','ELDEN_RECOVERY PSCI_RESET')):returning=True
                        if line.startswith('ELDEN_HID event=5 result=0 '):home_release_ok=True
                        for prefix in ('EldenRoot: verify OS ','EldenRoot: OS complete SHA256','EldenRoot: verify SystemOS ',
                                       'EldenRoot: SystemOS complete SHA256','BSD root:','ELDEN_BOOT init exec accepted',
                                       'ELDEN_DISPLAY frame=','ELDEN_TOUCH chip='):
                            if line.startswith(prefix) and prefix not in milestones_seen:
                                milestones_seen.add(prefix);report['milestones'].append(dict(prefix=prefix,line=line,elapsed=time.monotonic()-started,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
                        if line.startswith(('ELDEN_CPU ','ELDEN_UI_REPLAY ','ELDEN ACK TAP_SETTINGS','ELDEN ERR tap-settings','ELDEN ACK SWIPE_UP','ELDEN ERR swipe-up')):
                            report['control_events'].append(dict(line=line,elapsed=time.monotonic()-started,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
                            meta.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
                        if line=='ELDEN_UI_REPLAY swipe-up sent=25 error=0 release=0 source=software':
                            swipe_release_ok=any(e.get('command')=='swipe-up' and e.get('state')=='send-attempt' for e in report['control_events'])
                        if line.startswith('ELDEN_HID event-driver=1'):hid_ready=True
                        frame=re.fullmatch(r'ELDEN_DISPLAY frame=\d+ kind=0 pixels=(\d+) bounds=(\d+),(\d+)-(\d+),(\d+)',line)
                        if frame:
                            lit,minx,miny,maxx,maxy=map(int,frame.groups())
                            if lit and (lit>1904*3040//2 or minx<300 or miny<600 or maxy>2400):
                                if gui_at is None:gui_at=time.monotonic()
                        if status:
                            continuity.observe(status);report['boot_nonce']=continuity.nonce
                            report['statuses'].append(status);last_status=status
                        if charge_modes and status and tracker.confirmed and not tracker.failed and not (reboot_sent or returning):
                            elapsed=time.monotonic()-started
                            requested_mode=charge.update(status,elapsed)
                            if requested_mode:
                                output.flush();os.fsync(output.fileno())
                                report['charge_events']=charge.events;report['charge_errors']=charge.errors
                                meta.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
                                command=('charge '+a.expect_session+' '+requested_mode+'\n').encode('ascii')
                                if s.write(command)!=len(command):raise serial.SerialException('short charge command write; no retry')
                                print('\nSent session-bound charge mode '+requested_mode,flush=True)
                            if not charge.events and elapsed>=a.reboot_delay:
                                charge.errors.append('Charge controller never became ready; no charge command sent');charge.done=True
                        if a.home_after_ready and homes_sent<a.home_count and not (reboot_sent or returning) and hid_ready and gui_at is not None and time.monotonic()-gui_at>=2 and (homes_sent==0 or (home_release_ok and time.monotonic()-last_home_sent>=2)) and tracker.confirmed and not tracker.failed and status:
                            output.flush();os.fsync(output.fileno());home_sent=True
                            homes_sent+=1;home_sent=homes_sent==a.home_count;home_release_ok=False;last_home_sent=time.monotonic()
                            when=datetime.datetime.now(datetime.timezone.utc).isoformat();report.setdefault('home_requested_utc',when)
                            report.setdefault('home_requests',[]).append(dict(ordinal=homes_sent,utc=when,pre_log_sha256=received_hash.hexdigest()))
                            report.setdefault('pre_home_log_sha256',received_hash.hexdigest())
                            command=('home '+a.expect_session+'\n').encode('ascii')
                            if s.write(command)!=len(command):raise serial.SerialException('short Home command write; no retry')
                            print('\nSent session-bound virtual HID Home command '+str(homes_sent)+'/'+str(a.home_count)+'.',flush=True)
                        if a.reboot_after_ready and charge.done and not (reboot_sent or returning) and time.monotonic()-started>=a.reboot_delay and tracker.confirmed and not tracker.failed and status and status.get('fastboot')=='ready':
                            output.flush();os.fsync(output.fileno());reboot_sent=True
                            report['reboot_requested_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
                            report['pre_reboot_log_bytes']=report['bytes'];report['pre_reboot_log_sha256']=received_hash.hexdigest()
                            meta.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
                            command=('fastboot '+a.expect_session+'\n').encode('ascii')
                            if s.write(command)!=len(command):raise serial.SerialException('short fastboot command write; action uncertain, no retry')
                            print('\nSent one session-bound fastboot RPC after startup readiness.',flush=True)
                        if line.startswith(('ELDEN_RECOVERY ','ELDEN_RPC ','ELDEN_VDOG ','ELDEN_SMP ','ELDEN_SGI_MODE ','ELDEN_GIC_READ ','ELDEN ACK FASTBOOT ','panic(cpu')):
                            if len(report['recovery_events'])<128:
                                report['recovery_events'].append(dict(line=line,elapsed=time.monotonic()-started,
                                    utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
                                meta.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
                        if line.startswith(('ELDEN_POWER_PATH ','ELDEN_PD_BOOT phase=')):
                            events=report.setdefault('power_events',[])
                            if len(events)<256:
                                events.append(dict(line=line,elapsed=time.monotonic()-started,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
                except (serial.SerialException,OSError) as error:
                    if not a.reconnect_seconds or reboot_sent or returning or not continuity.nonce or len(report['reconnections'])>=3:raise
                    output.flush();os.fsync(output.fileno())
                    report['discontinuities'].append(dict(offset=report['bytes'],utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),error=str(error),partial_line_chars=len(lines.pending)))
                    tracker.first=None;tracker.confirmed=False;last_status=None
                    lines.pending='';lines.discarding=True
                    s.close();meta.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
                    until=min(started+a.seconds,time.monotonic()+a.reconnect_seconds)
                    fresh=None
                    while time.monotonic()<until:
                        fresh=reconnect_port(selected,list_ports.comports(),a.port)
                        if fresh is None:time.sleep(.5);continue
                        candidate=serial.Serial(port=None,baudrate=115200,timeout=.15,write_timeout=2)
                        candidate.port=fresh.device;candidate.dtr=True;candidate.rts=False
                        try:candidate.open()
                        except (serial.SerialException,OSError):
                            candidate.close();time.sleep(.5);continue
                        s=candidate;break
                    else:raise serial.SerialException('Bounded USB reconnect expired; no controls repeated') from error
                    selected=fresh;next_status=time.monotonic()
                    report['reconnections'].append(dict(port=selected.device,location=selected.location,expected_boot=continuity.nonce,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
                    meta.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
                    print('\nReopened verified USB port; waiting for fresh matching-boot status.',flush=True)
    except (serial.SerialException,OSError,KeyboardInterrupt,RuntimeError) as error:
        report['ended_by']=str(error)
        if isinstance(error,RuntimeError):raise
    finally:
        s.close();report['elapsed_seconds']=time.monotonic()-started
        report['candidate_session']=a.expect_session
        report['bound_startup_milestone_observed']=tracker.confirmed and not tracker.failed
        report['raw_sha256']=received_hash.hexdigest()
        report['oversized_console_lines_discarded']=lines.discarded
        if charge_modes:
            report['charge_events']=charge.events;report['charge_errors']=charge.errors
            report['charge_sequence_complete']=charge.done and not charge.errors;report['charge_restore_confirmed']=charge.restored
        meta.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('\nSaved '+str(report['bytes'])+' bytes. This is transport evidence, not proof of an iPadOS boot.')

if __name__=='__main__':main()
