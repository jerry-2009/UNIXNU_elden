"""Host charge confirmation, loss and one bounded stock-recovery path."""
import unittest
from elden_usb_console import ChargeSequence

def status(generation=10,mode=2,available=True):
    return {'charge_control':'1' if available else '0','charge_generation':str(generation),'charge_mode':str(mode)}

class ChargeSequenceTests(unittest.TestCase):
    def start(self,modes=None):
        s=ChargeSequence(modes or ['stock'],0,5,max_status_gap=5)
        self.assertEqual(s.update(status(),0),s.modes[0])
        return s

    def test_unavailable_historical_state_never_confirms(self):
        s=self.start();self.assertIsNone(s.update(status(11,1,False),1))
        self.assertIsNone(s.update(status(11,1,False),6))
        self.assertFalse(s.done);self.assertFalse(s.restored);self.assertIsNone(s.applied_at)

    def test_invalid_or_old_generation_never_confirms(self):
        for value in ('9','10','4294967296','9999999999','-1','1x','',None,11):
            with self.subTest(value=value):
                s=self.start();v=status(11,1);v['charge_generation']=value
                self.assertIsNone(s.update(v,1));self.assertIsNone(s.update(v,6))
                self.assertFalse(s.restored);self.assertIsNone(s.applied_at)

    def test_fresh_new_generation_requires_hold(self):
        s=self.start();self.assertIsNone(s.update(status(11,1),1))
        s.update(status(11,1),5.99);self.assertFalse(s.done)
        s.update(status(11,1),6);self.assertTrue(s.done);self.assertTrue(s.restored)

    def test_first_confirmation_at_or_after_deadline_is_not_success(self):
        for elapsed in (45,90,360):
            with self.subTest(elapsed=elapsed):
                s=self.start()
                self.assertEqual(s.update(status(11,1),elapsed),'stock')
                self.assertTrue(s.recovering);self.assertTrue(s.errors)
                self.assertFalse(s.restored);self.assertIsNone(s.applied_at)

    def test_in_time_confirmation_can_finish_hold_after_deadline(self):
        s=self.start();s.update(status(11,1),44.9)
        s.update(status(11,1),49.9);self.assertTrue(s.done);self.assertTrue(s.restored)

    def test_loss_during_hold_requires_new_qualified_interval(self):
        for bad in (status(11,1,False),status(11,2),status(9,1)):
            with self.subTest(bad=bad):
                s=self.start();s.update(status(11,1),1);s.update(bad,4)
                self.assertIsNone(s.applied_at);self.assertFalse(s.restored)
                self.assertEqual(s.events[-1]['event'],'confirmation-lost')
                s.update(status(11,1),6);self.assertFalse(s.done)
                s.update(status(11,1),11);self.assertTrue(s.done);self.assertTrue(s.restored)

    def test_silent_gap_restarts_hold(self):
        s=self.start()
        s.update(status(11,1),1)
        s.update(status(11,1),7)
        self.assertFalse(s.restored)
        self.assertEqual([e['event'] for e in s.events],['sent','applied','confirmation-lost','applied'])
        s.update(status(11,1),12)
        self.assertTrue(s.restored)

    def test_same_mode_new_generation_restarts_hold(self):
        s=self.start()
        s.update(status(11,1),1)
        s.update(status(12,1),6)
        self.assertFalse(s.restored)
        self.assertEqual(s.applied_at,6)
        s.update(status(12,1),11)
        self.assertTrue(s.restored)

    def test_silent_gap_after_confirmation_deadline_reverts_to_stock(self):
        s=self.start(['bypass','stock'])
        s.update(status(11,2),44)
        self.assertEqual(s.update(status(11,2),50),'stock')
        self.assertTrue(s.errors)
        self.assertFalse(s.restored)

    def test_unconfirmed_command_has_one_stock_recovery(self):
        s=self.start(['bypass','stock'])
        self.assertEqual(s.update(status(10,2),45),'stock')
        self.assertTrue(s.recovering);self.assertFalse(s.restored)
        self.assertIsNone(s.update(status(10,2),90));self.assertTrue(s.done)
        self.assertFalse(s.restored);self.assertEqual(len(s.errors),2)
        self.assertEqual([e['mode'] for e in s.events if e['event']=='sent'],['bypass','stock'])

    def test_no_recovery_write_while_unavailable(self):
        s=self.start(['bypass','stock'])
        self.assertIsNone(s.update(status(11,2,False),45));self.assertTrue(s.recovering)
        self.assertIsNone(s.update(status(11,2,False),90));self.assertTrue(s.done)
        self.assertFalse(s.restored);self.assertEqual(sum(e['event']=='sent' for e in s.events),1)

    def test_recovered_stock_still_preserves_trial_error(self):
        s=self.start(['bypass','stock']);s.update(status(10,2),45)
        s.update(status(11,1),46);s.update(status(11,1),51)
        self.assertTrue(s.restored);self.assertTrue(s.done);self.assertTrue(s.errors)

    def test_pending_loss_timeout_does_not_replay_experiment(self):
        s=self.start(['80','stock']);s.update(status(11,3),1)
        s.update(status(11,3,False),4);s.update(status(11,3,False),45)
        self.assertEqual(s.update(status(11,3),46),'stock')
        self.assertEqual([e['mode'] for e in s.events if e['event']=='sent'],['80','stock'])

    def test_transport_loss_discards_hold_and_allows_only_stock(self):
        s=self.start(['bypass','80','stock'])
        s.update(status(11,2),1)
        s.transport_lost(3)
        self.assertIsNone(s.update(status(11,2,False),16))
        self.assertEqual(s.update(status(11,2),17),'stock')
        s.update(status(12,1),18)
        s.update(status(12,1),23)
        self.assertTrue(s.done and s.restored and s.errors)
        self.assertEqual([e['mode'] for e in s.events if e['event']=='sent'],['bypass','stock'])

    def test_interruption_of_intermediate_stock_does_not_resume_trial(self):
        s=self.start(['stock','80','stock'])
        s.update(status(11,1),1)
        s.transport_lost(2)
        self.assertIsNone(s.update(status(11,1),15))
        self.assertFalse(s.done)
        self.assertIsNone(s.update(status(11,1),20))
        self.assertTrue(s.done and s.restored and s.errors)
        self.assertEqual([e['mode'] for e in s.events if e['event']=='sent'],['stock'])

    def test_repeated_disconnect_cannot_extend_recovery(self):
        s=self.start(['bypass','stock'])
        s.transport_lost(1)
        s.transport_lost(30)
        self.assertIsNone(s.update(status(11,2),46))
        self.assertTrue(s.done)
        self.assertFalse(s.restored)
        self.assertEqual([e['mode'] for e in s.events if e['event']=='sent'],['bypass'])

    def test_disconnect_before_first_write_aborts_without_controls(self):
        s=ChargeSequence(['bypass','stock'],60,5,max_status_gap=5)
        s.transport_lost(20)
        self.assertIsNone(s.update(status(),70))
        self.assertTrue(s.done and s.errors)
        self.assertFalse(s.events)

    def test_u32_limit_and_no_wrap_request(self):
        s=ChargeSequence(['stock'],0,5,max_status_gap=5)
        self.assertIsNone(s.update(status(0xffffffff),0));self.assertTrue(s.done)
        self.assertTrue(s.errors);self.assertFalse(s.restored);self.assertFalse(s.events)
        s=ChargeSequence(['stock'],0,5,max_status_gap=5)
        self.assertEqual(s.update(status(0xfffffffe),0),'stock')
        s.update(status(0xffffffff,1),1);s.update(status(0xffffffff,1),6)
        self.assertTrue(s.restored)

    def test_valid_five_mode_sequence(self):
        s=ChargeSequence(['bypass','80','bypass','40-60','stock'],0,5,max_status_gap=5)
        self.assertEqual(s.update(status(0,0),0),'bypass')
        for generation,mode in enumerate((2,3,2,4,1),1):
            start=(generation-1)*6+1;s.update(status(generation,mode),start)
            request=s.update(status(generation,mode),start+5)
            self.assertEqual(request,('80','bypass','40-60','stock',None)[generation-1])
        self.assertTrue(s.done);self.assertTrue(s.restored);self.assertFalse(s.errors)

if __name__=='__main__':unittest.main()
