"""One unattended, session-bound swipe/tap trial based on CRC-verified frames.

The console owns USB/readiness. This watcher creates only its structured control
file. Image matching is limited to the already observed fixed Settings icon;
application content is retained for visual assessment, not declared successful.
"""
from pathlib import Path
import argparse,datetime,json,re,time
from PIL import Image,ImageChops,ImageStat
from decode_frame_preview import decode

def rgb(raw):
 import struct
 image=Image.new('RGB',(238,380));image.putdata([(((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31) for v, in struct.iter_unpack('<H',raw)]);return image

def lockscreen(image):
 pixels=list(image.crop((60,20,170,75)).getdata())
 bright=sum(1 for r,g,b in pixels if min(r,g,b)>155)
 bar=sum(1 for r,g,b in image.crop((75,375,165,380)).getdata() if min(r,g,b)>190)
 # A blank white app also has many bright pixels and a navigation bar.
 # Require the sparse bright clock/handle of the frozen lock-screen profile.
 return 300<bright<len(pixels)*0.6 and 30<bar<300

def desktop(image,reference,box=(186,138,205,157),search=0):
 # Compare only the observed grey gear, not its wallpaper/background.
 expected=list(reference.crop(box).getdata())
 mask=[i for i,p in enumerate(expected) if max(p)-min(p)<18 and 25<sum(p)/3<230]
 if len(mask)<40:return False
 tap=(27285/32767*238,12934/32767*380)
 for dx in range(-search,search+1):
  for dy in range(-search,search+1):
   shifted=(box[0]+dx,box[1]+dy,box[2]+dx,box[3]+dy)
   if not (0<=shifted[0]<shifted[2]<=238 and 0<=shifted[1]<shifted[3]<=380):continue
   if not (shifted[0]+2<tap[0]<shifted[2]-2 and shifted[1]+2<tap[1]<shifted[3]-2):continue
   current=list(image.crop(shifted).getdata())
   if sum(sum(abs(a-b) for a,b in zip(current[i],expected[i]))/3 for i in mask)/len(mask)<14:return True
 return False

def main():
 p=argparse.ArgumentParser();p.add_argument('--workbench',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--session',required=True);p.add_argument('--desktop-settle-seconds',type=int,default=0);p.add_argument('--lock-settle-seconds',type=int,default=45);p.add_argument('--entry-gesture',choices=('swipe-up','home'),default='swipe-up');p.add_argument('--desktop-reference',type=Path,required=True);p.add_argument('--desktop-box',type=int,nargs=4,default=(186,138,205,157));p.add_argument('--desktop-search',type=int,default=0);p.add_argument('--desktop-only',action='store_true',help='Observe the desktop after entry without requesting a Settings tap');p.add_argument('--wait-pd-ready',action='store_true',help='Defer entry until the latest PD observation is Ready');p.add_argument('--finish-after-tap-seconds',type=int,default=180,help='Observation seconds after tap, or after desktop in desktop-only mode');a=p.parse_args();assert 0<=a.desktop_settle_seconds<=90 and 0<=a.desktop_search<=8 and 0<=a.lock_settle_seconds<=90 and 15<=a.finish_after_tap_seconds<=180
 root=a.workbench.resolve(strict=True);run=a.run.resolve();assert run.is_relative_to(root/'edl_work')
 assert len(a.session)==16 and all(x in '0123456789abcdef' for x in a.session)
 run.mkdir(parents=True,exist_ok=True);out=run/'trial-frames';out.mkdir(exist_ok=True)
 reference_path=a.desktop_reference.resolve(strict=True)
 reference=Image.open(reference_path).convert('RGB');assert reference.size==(238,380)
 assert 0<=a.desktop_box[0]<a.desktop_box[2]<=238 and 0<=a.desktop_box[1]<a.desktop_box[3]<=380
 control=run/'control.json';assert not control.exists()
 report={'session':a.session,'events':[],'device_result':'unproven'};start=time.monotonic();seen=set();lock_at=None;swipe_at=None;tap_at=None;request_frame=0;last_size=-1;tap_frame=0;finished=False
 desktop_at=None;desktop_frame=0;desktop_done_at=None;report['desktop_settle_seconds']=a.desktop_settle_seconds;report['desktop_only']=a.desktop_only
 report['lock_settle_seconds']=a.lock_settle_seconds
 report['wait_pd_ready']=a.wait_pd_ready
 report['entry_gesture']=a.entry_gesture
 report['finish_after_tap_seconds']=a.finish_after_tap_seconds
 import hashlib
 report['desktop_reference']=dict(path=str(reference_path),sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),box=a.desktop_box,search=a.desktop_search)
 def event(kind,**fields):
  item=dict(kind=kind,elapsed=time.monotonic()-start,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**fields);report['events'].append(item)
  (run/'trial.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(item),flush=True)
 def command(ident,kind):
  temp=run/'control.pending.json';temp.write_text(json.dumps(dict(id=ident,session=a.session,command=kind))+'\n');temp.replace(control);event('request',command=kind,id=ident)
 while time.monotonic()-start<1000:
  logs=list((run/'usb').glob('*.bin'))
  if len(logs)>1:event('refused-multiple-captures');break
  if not logs:time.sleep(.5);continue
  meta_path=logs[0].with_suffix('.json')
  try:meta=json.loads(meta_path.read_text())
  except (OSError,ValueError):time.sleep(.2);continue
  if meta.get('candidate_session')!=a.session:event('refused-session');break
  data=logs[0].read_bytes();text=data.decode(errors='replace')
  if 'ELDEN_RECOVERY DEADLINE_FIRED' in text or 'ELDEN_RPC RESET_AFTER_SYNC' in text or 'ELDEN_RECOVERY PANIC_WAIT' in text:
   event('target-returning');break
  if meta.get('raw_sha256'):event('capture-ended');break
  signature=re.search(r'ELDEN_ICON_SIGNATURE pid=([0-9]+) unique=([0-9]+) error=([0-9]+) mac=([0-9]+) ns=([0-9]+) code=([0-9a-f]+) flags=([0-9a-f]+)',text)
  if signature:
   event('signature-failed',pid=int(signature[1]),error=int(signature[3]),mac=int(signature[4]),namespace=int(signature[5]),code=signature[6],flags=signature[7]);command('icon-signature-result','fastboot');break
  exited=re.search(r'ELDEN_ICON_EXIT pid=([0-9]+) rv=([0-9a-f]+) ns=([0-9]+) code=([0-9a-f]+) text=([^\r\n]*)',text)
  if exited and (int(exited[2],16)!=0 or int(exited[3])!=0):
   event('service-exit',pid=int(exited[1]),rv=exited[2],namespace=int(exited[3]),code=exited[4],text=exited[5]);command('icon-exit-reason-captured','fastboot');break
  failed=re.search(r'ELDEN_ICON_CPU exec result=([1-9][0-9]*) stage=([0-9]+)',text)
  if failed:
   event('exec-failed',error=int(failed[1]),stage=int(failed[2]));command('icon-exec-failed','fastboot');break
  if len(data)!=last_size:
   last_size=len(data)
   for marker in ('ELDEN_ICON_CPU stage=ready','ELDEN_ICON_CPU exec result=0','ELDEN_ICON_CPU environment appended','ELDEN_ICON_CPU loaded','ELDEN_ICON_CPU installed','ELDEN_UI_REPLAY swipe-up sent=25 error=0 release=0','ELDEN_UI_REPLAY settings down=0 up=0'):
    if marker in text and not any(x.get('marker')==marker for x in report['events']):event('marker',marker=marker)
   for ident,frame,raw in decode(data,a.session,[x['offset'] for x in meta.get('discontinuities',[])]):
    if ident in seen:continue
    seen.add(ident);image=rgb(raw);image.save(out/f'frame-{ident}.png')
    isdesk=desktop(image,reference,tuple(a.desktop_box),a.desktop_search);islock=lockscreen(image)
    event('verified-frame',id=ident,desktop_match=isdesk,lockscreen_match=islock)
    if lock_at is None and islock and not isdesk:lock_at=time.monotonic()
    entry_released=('ELDEN_HID event=4 result=0' in text and 'ELDEN_HID event=5 result=0' in text) if a.entry_gesture=='home' else 'ELDEN_UI_REPLAY swipe-up sent=25 error=0 release=0' in text
    if swipe_at is not None and tap_at is None and ident>request_frame and isdesk and entry_released:
     image.save(out/'desktop.png');desktop_frame=ident
     if desktop_at is None:desktop_at=time.monotonic();event('desktop-settling',seconds=a.desktop_settle_seconds)
    elif swipe_at is not None and tap_at is None and ident>request_frame and not isdesk:
     desktop_at=None
     # A later template mismatch is recorded above, but does not erase an
     # already observed desktop or extend its bounded observation deadline.
    if tap_at is not None and ident>tap_frame:image.save(out/f'after-tap-{ident}.png')
  if desktop_at is not None and tap_at is None and time.monotonic()-desktop_at>=a.desktop_settle_seconds:
   if a.desktop_only:
    if desktop_done_at is None:desktop_done_at=time.monotonic();event('desktop-only-observed',frame=desktop_frame)
   else:command('icon-settings-once','tap-settings');tap_at=time.monotonic();tap_frame=desktop_frame
  pd_states=re.findall(r'ELDEN_PD_POWER state=(\d+) ',text)
  pd_ready=not a.wait_pd_ready or (pd_states and pd_states[-1]=='2')
  if lock_at is not None and swipe_at is None and time.monotonic()-lock_at>=a.lock_settle_seconds and 'ELDEN_ICON_CPU stage=ready' in text and pd_ready:
   request_frame=max(seen,default=0);command('icon-unlock-once',a.entry_gesture);swipe_at=time.monotonic()
  if tap_at is not None and not finished and time.monotonic()-tap_at>=a.finish_after_tap_seconds:
   command('icon-trial-finish','fastboot');finished=True
  if a.desktop_only and desktop_done_at is not None and not finished and time.monotonic()-desktop_done_at>=a.finish_after_tap_seconds:
   command('desktop-only-finish','fastboot');finished=True
  if a.desktop_only and swipe_at is not None and desktop_done_at is None and not finished and time.monotonic()-swipe_at>=90:
   event('desktop-not-observed-after-entry');command('desktop-only-unproven','fastboot');finished=True;break
  time.sleep(.5)
 else:event('watcher-timeout; console and target deadlines retained')
 report['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();(run/'trial.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
