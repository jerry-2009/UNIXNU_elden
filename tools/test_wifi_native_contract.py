"""Check artifact-bound identity declarations and rejection of external paths."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from charge_verification_boot import load_native_contract


class NativeContract(unittest.TestCase):
    def fixture(self):
        folder=Path(tempfile.mkdtemp(prefix='y700-native-contract-'))
        (folder/'native.macho').write_bytes(b'modeled native artifact')
        identity=dict(sections={},commands=[],symbols={})
        (folder/'native-contract.json').write_text(json.dumps(identity))
        sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
        report=dict(native_sha256=sha(folder/'native.macho'))
        report['native_identity_contract']=dict(path='native-contract.json',
            sha256=sha(folder/'native-contract.json'),native_sha256=report['native_sha256'])
        return folder,identity,report

    def test_declared_identity_matches_saved_files(self):
        folder,identity,report=self.fixture()
        self.assertEqual(load_native_contract(folder,report,'wifi-ce3-flow-trace',wifi_service=True),identity)

    def test_path_and_variant_rejected(self):
        for path in ('../native-contract.json','other.json','C:/outside.json'):
            folder,_,report=self.fixture();report['native_identity_contract']['path']=path
            with self.assertRaises(ValueError):load_native_contract(folder,report,'wifi-ce3-flow-trace',wifi_service=True)
        folder,_,report=self.fixture()
        with self.assertRaises(ValueError):load_native_contract(folder,report,'wifi-ce3-flow-trace',wifi_service=False)

    def test_hash_and_native_binding_changes_rejected(self):
        for changed in ('native','contract','native-binding','declaration-hash'):
            folder,_,report=self.fixture()
            if changed=='native':(folder/'native.macho').write_bytes(b'changed native')
            if changed=='contract':(folder/'native-contract.json').write_text('{}')
            if changed=='native-binding':report['native_identity_contract']['native_sha256']='f'*64
            if changed=='declaration-hash':report['native_identity_contract']['sha256']='f'*64
            with self.assertRaises(ValueError):load_native_contract(folder,report,'wifi-ce3-flow-trace',wifi_service=True)

    def test_extra_identity_fields_rejected(self):
        folder,identity,report=self.fixture();identity['allow_extra']=True
        (folder/'native-contract.json').write_text(json.dumps(identity))
        report['native_identity_contract']['sha256']=hashlib.sha256((folder/'native-contract.json').read_bytes()).hexdigest()
        with self.assertRaises(ValueError):load_native_contract(folder,report,'wifi-ce3-flow-trace',wifi_service=True)


if __name__=='__main__':unittest.main()
