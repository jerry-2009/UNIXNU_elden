"""Replay the actual watcher's frame and deadline blocks without device I/O."""
from pathlib import Path
import argparse,json,subprocess,textwrap,types
ROOT=Path(__file__).resolve().parents[1]
PATH='tools/device/watch_icon_trial.py'

def replay(source,frames,settle=0):
    frame=source[source.index('    if swipe_at is not None and tap_at is None and ident>request_frame and isdesk'):source.index('  pd_states=re.findall')]
    # Strip the unrelated post-tap image branch, preserving the actual guards.
    frame=frame.replace("    if tap_at is not None and ident>tap_frame:image.save(out/f'after-tap-{ident}.png')\n",'')
    frame=frame.replace('\n  if desktop_at','\n    if desktop_at').replace('\n   if a.desktop_only:','\n     if a.desktop_only:').replace('\n    if desktop_done_at','\n      if desktop_done_at').replace("\n   else:command('icon-settings-once'","\n     else:command('icon-settings-once'")
    timer=source[source.index('  if tap_at is not None and not finished'):source.index('  time.sleep(.5)')]
    calls=[];events=[];clock=[0.0]
    env={'time':types.SimpleNamespace(monotonic=lambda:clock[0]),'swipe_at':132.937,'tap_at':None,'request_frame':3,'desktop_at':None,'desktop_done_at':None,'finished':False,'entry_released':True,'out':Path('.'),'image':types.SimpleNamespace(save=lambda _:None),'event':lambda name,**kw:events.append(name),'command':lambda *args:calls.append(args),'a':types.SimpleNamespace(desktop_only=True,desktop_settle_seconds=settle,finish_after_tap_seconds=60)}
    for stamp,ident,matched in frames:
        clock[0]=stamp;env.update(ident=ident,isdesk=matched);exec(textwrap.dedent(frame),env)
    for stamp in (200.0,223.0,300.0):
        clock[0]=stamp;exec('for _ in (0,):\n'+textwrap.indent(textwrap.dedent(timer),' '),env)
    return calls,events

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    old=subprocess.check_output(['git','show','7de19eb69f022e9ce9921d72ef5d7c148fa9b278:'+PATH],cwd=ROOT,text=True);new=(ROOT/PATH).read_text()
    frames=[(139.671,4,True),(143.5,5,True),(156.015,6,False),(158.375,7,False)]
    old_calls,_=replay(old,frames);assert old_calls==[('desktop-only-unproven','fastboot')]
    calls,events=replay(new,frames);assert calls==[('desktop-only-finish','fastboot')] and 'desktop-not-observed-after-entry' not in events
    assert replay(new,[(139.0,4,False)])[0]==[('desktop-only-unproven','fastboot')]
    assert replay(new,[(139.0,4,True),(140.0,5,False)],settle=2)[0]==[('desktop-only-unproven','fastboot')]
    assert replay(new,[(139.0,4,True),(143.0,5,True)],settle=2)[0]==[('desktop-only-finish','fastboot')]
    result={'passed':True,'cases':5,'old_misreport_reproduced':True,'v146_frame_timing_replayed':True,'actual_watcher_blocks':True,'device_operations':False}
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))
if __name__=='__main__':main()
