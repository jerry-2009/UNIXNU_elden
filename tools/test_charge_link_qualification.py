"""Test actual charge-pair qualification and build-option refusal paths.

Compiler/object services are modeled here; real native build evidence is separate.
No tablet, firmware or external application is accessed.
"""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_charge_verification
import build_clean
import bt_runtime_boot
from charge_verification_boot import qualify_charge_link_pair, load_native_contract

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenPmicGlink'))
from LinkSource import header,policy,client


def sha(data):return hashlib.sha256(data).hexdigest()


class ChargeLinkQualification(unittest.TestCase):
    def fixture(self, combined=False):
        temporary=tempfile.TemporaryDirectory(prefix='y700-charge-qualify-')
        self.addCleanup(temporary.cleanup)
        folder=Path(temporary.name);(folder/'source').mkdir()
        generated_header=header();header_path=folder/'source/ChargePolicy.h'
        header_path.write_bytes(generated_header)
        report=dict(profile='charge-link-pd' if combined else 'charge-link-recovery',manual_inhibit_survives_transport_loss=True,
                    generated_policy_header_sha256=sha(generated_header),native_objects={})
        from PdStartupSource import recovery_client
        pmic_source=recovery_client() if combined else client()
        for unit,name,data in [('ChargePolicy','ChargePolicy.c',policy()),('PmicClient','PmicClient.cpp',pmic_source)]:
            (folder/'source'/name).write_bytes(data)
            obj=(unit+' modeled object').encode();(folder/(unit+'.o')).write_bytes(obj)
            aliases=['/frozen/ChargePolicy.h','/build/project/ChargePolicy.h']
            overlay=dict(fallthrough=False,roots=[dict(type='file',name=n,**{'external-contents':str(header_path)}) for n in aliases])
            (folder/(unit+'.overlay.json')).write_text(json.dumps(overlay),encoding='utf-8')
            report['native_objects'][unit]=dict(source_sha256=sha(data),object_sha256=sha(obj),
                generated_policy_header_sha256=sha(generated_header),policy_header_bindings=aliases)
        return folder,report

    def test_compiled_pair_accepts_derived_aliases(self):
        folder,report=self.fixture();qualify_charge_link_pair(folder,report)

    def test_combined_requires_matching_pmic_source_and_gui_packaging(self):
        folder,report=self.fixture(combined=True);qualify_charge_link_pair(folder,report)
        report['profile']='charge-link-recovery'
        with self.assertRaisesRegex(ValueError,'source/header pairing'):qualify_charge_link_pair(folder,report)
        qualification=dict(profile='charge-link-pd',table_count=59,key_state=2)
        with self.assertRaisesRegex(ValueError,'requires --pd-gui'):bt_runtime_boot.menu(qualification)
        gui=bt_runtime_boot.pd_gui(qualification)
        self.assertEqual(gui['native_profile'],'charge-link-pd')
        self.assertIn('ebl=6',bt_runtime_boot.menu(gui))

    def test_missing_or_mismatched_consumer_rejected(self):
        for unit in ('ChargePolicy','PmicClient'):
            for changed in ('missing','source','header','object'):
                with self.subTest(unit=unit,changed=changed):
                    folder,report=self.fixture()
                    if changed=='missing':report['native_objects'].pop(unit)
                    elif changed=='source':report['native_objects'][unit]['source_sha256']='0'*64
                    elif changed=='header':report['native_objects'][unit]['generated_policy_header_sha256']='0'*64
                    else:(folder/(unit+'.o')).write_bytes(b'old object')
                    with self.assertRaises(ValueError):qualify_charge_link_pair(folder,report)

    def test_old_missing_or_duplicate_header_alias_rejected(self):
        for unit in ('ChargePolicy','PmicClient'):
            for changed in ('old','missing','duplicate','declaration','fallthrough'):
                with self.subTest(unit=unit,changed=changed):
                    folder,report=self.fixture();path=folder/(unit+'.overlay.json')
                    overlay=json.loads(path.read_text(encoding='utf-8'))
                    if changed=='old':overlay['roots'][1]['external-contents']=str(folder/'old/ChargePolicy.h')
                    elif changed=='missing':overlay['roots'].pop()
                    elif changed=='duplicate':overlay['roots'][1]=copy.deepcopy(overlay['roots'][0])
                    elif changed=='declaration':report['native_objects'][unit]['policy_header_bindings'].pop()
                    else:overlay['fallthrough']=True
                    path.write_text(json.dumps(overlay),encoding='utf-8')
                    with self.assertRaises(ValueError):qualify_charge_link_pair(folder,report)

    def test_generated_source_and_header_tampering_rejected(self):
        for name in ('ChargePolicy.h','ChargePolicy.c','PmicClient.cpp'):
            folder,report=self.fixture();(folder/'source'/name).write_bytes(b'old source')
            with self.assertRaises(ValueError):qualify_charge_link_pair(folder,report)

    def test_artifact_bound_charge_identity(self):
        folder,report=self.fixture();artifact=b'modeled loaded native';identity=dict(sections={},commands=[],symbols={})
        (folder/'native.macho').write_bytes(artifact)
        contract=json.dumps(identity).encode();(folder/'native-contract.json').write_bytes(contract)
        report['native_sha256']=sha(artifact)
        report['native_identity_contract']=dict(path='native-contract.json',sha256=sha(contract),native_sha256=sha(artifact))
        self.assertEqual(load_native_contract(folder,report,'charge-link-recovery'),identity)
        for changed in ('external-path','artifact','contract','binding'):
            selected=copy.deepcopy(report)
            if changed=='external-path':selected['native_identity_contract']['path']='../native-contract.json'
            elif changed=='artifact':(folder/'native.macho').write_bytes(b'changed artifact')
            elif changed=='contract':selected['native_identity_contract']['sha256']='0'*64
            else:selected['native_identity_contract']['native_sha256']='0'*64
            with self.assertRaises(ValueError):load_native_contract(folder,selected,'charge-link-recovery')
            (folder/'native.macho').write_bytes(artifact)

    def clean_arguments(self):
        return ['build_clean.py','--inputs','unused-inputs.json','--output','unused-output',
                '--variant','bluetooth','--bt-exit-stack','--software-keystore',
                '--bluetool-launch','--bt-transport-trace','--bluetool-lifecycle',
                '--bt-registry','--bt-helper-trace','--bt-process-lifetime',
                '--bt-address17','--charge-link-recovery']

    def test_clean_chain_reaches_native_platform_guard(self):
        for options in ([],['--pd-gui']):
            with mock.patch.object(sys,'argv',self.clean_arguments()+options),mock.patch.object(sys,'platform','win32'):
                with self.assertRaisesRegex(SystemExit,'Native build requires macOS'):build_clean.main()

    def test_clean_chain_rejects_missing_prerequisite_and_mixed_options(self):
        base=self.clean_arguments()
        for option in ('--spmi-translation-survey','--backlight-service','--backlight-power-trial',
                       '--pd-power-trial','--cpu-power-observation','--cpu-governor',
                       '--storage-medium','--early-storage-guard','--ufs-wait-trial',
                       '--ufs-queue-trial','--ufs-idle-trial','--data-capacity-2g'):
            with self.subTest(option=option),mock.patch.object(sys,'argv',base+[option]):
                with self.assertRaises(ValueError):build_clean.main()
        for omitted in ('--bt-address17','--bt-process-lifetime'):
            with mock.patch.object(sys,'argv',[a for a in base if a!=omitted]):
                with self.assertRaises(ValueError):build_clean.main()
        with mock.patch.object(sys,'argv',['build_clean.py','--inputs','unused.json','--output','unused',
                                         '--variant','gui','--charge-link-recovery']):
            with self.assertRaisesRegex(ValueError,'Bluetooth/address17'):build_clean.main()

    def test_component_rejects_mixed_options_before_input_access(self):
        base=['build_charge_verification.py','--clean-build','unused-clean','--parent-build','unused-parent',
              '--original-kernelcache','unused-kernel','--llvm','unused-llvm','--output','unused-out','--link-recovery']
        for option in ('--translation-survey','--backlight-service','--backlight-power-trial',
                       '--pd-power-trial','--cpu-power-observation','--cpu-governor',
                       '--storage-medium','--early-storage-guard','--ufs-wait-trial',
                       '--ufs-queue-trial','--ufs-idle-trial'):
            with self.subTest(option=option),mock.patch.object(sys,'argv',base+[option]):
                with self.assertRaisesRegex(ValueError,'separate charging pair'):build_charge_verification.main()


if __name__=='__main__':unittest.main()
