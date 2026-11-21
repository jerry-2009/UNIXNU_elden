"""Exercise the real logger loop with a failing COM link; no device I/O."""
import contextlib,hashlib,io,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
import serial
from serial.tools import list_ports
import elden_usb_console as logger

SESSION='1234567890abcdef'
NONCE='1111111111111111'
def port(name='COM9',location='1-5',vid=logger.VID):
    return types.SimpleNamespace(device=name,location=location,vid=vid,pid=logger.PID,serial_number=logger.SERIAL)

class Clock:
    now=0.0
    def monotonic(self):return self.now
    def sleep(self,seconds):self.now+=seconds

class ReconnectTests(unittest.TestCase):
    def test_nonce_required_and_stable(self):
        guard=logger.BootContinuity(SESSION,True)
        with self.assertRaises(RuntimeError):guard.observe({'session':SESSION})
        guard.observe({'session':SESSION,'boot':NONCE})
        guard.observe({'session':SESSION,'boot':NONCE})
        with self.assertRaises(RuntimeError):guard.observe({'session':SESSION,'boot':'2222222222222222'})
        with self.assertRaises(RuntimeError):guard.observe({'session':'0'*16,'boot':NONCE})
        legacy=logger.BootContinuity(SESSION)
        legacy.observe({'session':SESSION});self.assertIsNone(legacy.nonce)

    def test_physical_identity_and_explicit_port(self):
        before=port();after=port('COM11')
        self.assertIs(logger.reconnect_port(before,[port('COM8','1-6'),after,port('COM1','1-5',vid=0x05c6)]),after)
        self.assertIsNone(logger.reconnect_port(before,[after],'COM9'))
        with self.assertRaises(RuntimeError):logger.reconnect_port(before,[after,port('COM12')])

    def run_loop(self,changed_boot=False):
        clock=Clock();created=[];control_writes=[]
        class Link:
            def __init__(self,**kwargs):self.number=len(created);created.append(self)
            def open(self):pass
            def close(self):pass
            def write(self,data):
                if data.startswith(b'home '):
                    control_writes.append(data)
                    if self.number==0:raise serial.SerialException('uncertain control write; cable disappeared')
                return len(data)
            def read(self,size):
                clock.sleep(2)
                nonce='2222222222222222' if changed_boot and self.number else NONCE
                return ('\nELDEN STATUS v1 session='+SESSION+' boot='+nonce+
                    ' configured=1 dtr=1 cache=0 data=0 init_exec=1 user_trap=1 fastboot=ready\n').encode()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);control=root/'control.json';output=root/'logs'
            control.write_text(json.dumps(dict(id='only-home',session=SESSION,command='home')))
            args=['logger','--listen','--expect-session',SESSION,'--status-interval','1','--seconds','48',
                  '--reconnect-seconds','10','--control-file',str(control),'--output',str(output)]
            with patch.object(sys,'argv',args),patch.object(serial,'Serial',Link),patch.object(list_ports,'comports',lambda:[port()]),\
                 patch.object(logger.time,'monotonic',clock.monotonic),patch.object(logger.time,'sleep',clock.sleep),\
                 contextlib.redirect_stdout(io.StringIO()):
                if changed_boot:
                    with self.assertRaisesRegex(RuntimeError,'rebooted or changed'):logger.main()
                else:logger.main()
            meta=json.loads(next(output.glob('*.json')).read_text());raw=next(output.glob('*.bin')).read_bytes()
            self.assertEqual(len(control_writes),1)
            self.assertEqual(len(meta['reconnections']),1)
            self.assertEqual(len(meta['discontinuities']),1)
            self.assertEqual(meta['raw_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(meta['boot_nonce'],NONCE)
            self.assertEqual(len([e for e in meta['control_events'] if e.get('state')=='send-attempt']),1)
            if changed_boot:self.assertIn('rebooted or changed',meta['ended_by'])
            else:
                self.assertTrue(meta['bound_startup_milestone_observed'])
                self.assertGreaterEqual(meta['elapsed_seconds'],48)

    def test_uncertain_control_not_repeated_on_same_boot(self):self.run_loop()
    def test_new_boot_stops_controls_and_retains_evidence(self):self.run_loop(True)

    def test_charge_reconnect_runs_only_stock_recovery(self):
        clock=Clock();created=[];writes=[]

        class Link:
            def __init__(self,**kwargs):
                self.number=len(created);created.append(self)
            def open(self):pass
            def close(self):pass
            def write(self,data):
                if data!=b'status\n':writes.append((clock.now,data))
                if data.startswith(b'charge ') and self.number==0:
                    raise serial.SerialException('cable removed during charge write')
                return len(data)
            def read(self,size):
                clock.sleep(2)
                generation=1+sum(command.endswith(b' stock\n') for _,command in writes)
                mode=1 if generation==2 else 2
                return (f'\nELDEN STATUS v1 session={SESSION} boot={NONCE} configured=1 '
                        f'dtr=1 cache=0 data=0 init_exec=1 user_trap=1 fastboot=ready '
                        f'charge_control=1 charge_generation={generation} charge_mode={mode}\n').encode()

        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'logs'
            args=['logger','--listen','--expect-session',SESSION,'--status-interval','1',
                  '--seconds','65','--reconnect-seconds','35','--reboot-after-ready',
                  '--reboot-delay','42','--charge-delay','0','--charge-hold','5',
                  '--charge-sequence','bypass,80,stock','--output',str(output)]
            with patch.object(sys,'argv',args),patch.object(serial,'Serial',Link),patch.object(list_ports,'comports',lambda:[port()]),\
                 patch.object(logger.time,'monotonic',clock.monotonic),patch.object(logger.time,'sleep',clock.sleep),\
                 contextlib.redirect_stdout(io.StringIO()):
                logger.main()
            meta=json.loads(next(output.glob('*.json')).read_text())
            self.assertEqual([line.decode().strip() for _,line in writes],
                             [f'charge {SESSION} bypass', f'charge {SESSION} stock', f'fastboot {SESSION}'])
            self.assertGreaterEqual(writes[1][0]-writes[0][0],10)
            self.assertEqual(len(meta['reconnections']),1)
            self.assertFalse(meta['charge_sequence_complete'])
            self.assertTrue(meta['charge_restore_confirmed'])

if __name__=='__main__':unittest.main()
