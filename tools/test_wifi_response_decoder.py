"""Check response success, config mismatch and explicit incomplete evidence."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'analysis'))
from decode_wifi_response_trace import decode

SAMPLE=(b'ELDEN_CE3_FLOW seq=0 ms=100 kind=1 a=1 b=5 c=4d4f4445 d=2 e=1 credit=2 reports=2\n'
        b'ELDEN_CE3_FLOW seq=1 ms=101 kind=1 a=0 b=1 c=5253504d d=0 e=0 credit=2 reports=2\n'
        b'ELDEN_CE3_FLOW seq=2 ms=102 kind=1 a=10008000 b=8000 c=52494e47 d=40 e=4 credit=0 reports=2\n'
        b'ELDEN_CE3_FLOW seq=3 ms=102 kind=1 a=10008000 b=8000 c=45585043 d=4 e=1b86000 credit=0 reports=2\n'
        b'ELDEN_CE3_FLOW seq=4 ms=102 kind=1 a=1000410c b=0 c=50545253 d=1000410c e=40 credit=0 reports=2\n'
        b'ELDEN_CE3_FLOW_END claimed=5 emitted=5 dropped=0\n')
class Decoder(unittest.TestCase):
    def test_success_is_bound_to_requested_mode_and_config(self):
        result=decode(SAMPLE)
        self.assertTrue(result['mode_status_verified'] and result['mode_command_succeeded'])
        self.assertTrue(result['ce3_config_matches'] and result['ce3_enable_observed'])
        self.assertFalse(result['network_accepted'])
    def test_failure_or_wrong_mode_is_not_success(self):
        for replacement in (b'a=1 b=1 c=5253504d',b'a=0 b=0 c=5253504d'):
            result=decode(SAMPLE.replace(b'a=0 b=1 c=5253504d',replacement))
            self.assertFalse(result['mode_command_succeeded'])
    def test_register_mismatch_is_retained(self):
        result=decode(SAMPLE.replace(b'a=10008000 b=8000 c=52494e47',b'a=0 b=0 c=52494e47'))
        self.assertFalse(result['ce3_config_matches'])
    def test_refused_schema_remains_unproven(self):
        result=decode(SAMPLE.replace(b'a=0 b=1 c=5253504d',b'a=18 b=0 c=52454655'))
        self.assertFalse(result['mode_status_verified'])
        self.assertTrue(result['mode_transition_success_unproven'])
if __name__=='__main__':unittest.main()
