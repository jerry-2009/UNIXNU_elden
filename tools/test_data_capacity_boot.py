"""Exercise actual capacity qualification and its explicit KeyStore variant."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import data_capacity_boot as capacity


class CapacityQualification(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="y700-capacity-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.old_object = self.folder / "inherited.o"
        self.old_object.write_bytes(b"unchanged inherited object")
        self.old_hash = hashlib.sha256(self.old_object.read_bytes()).hexdigest()

    def report(self, with_key):
        contract = capacity.read(capacity.ROOT / "profiles/data-capacity-2g/seed-layout-contract.json")
        seed = dict(contract, requires_expanded_native_qualification=True,
                    raw_owners_verified=233, packed_sha256="a" * 64, raw_sha256="d" * 64)
        names = {"kern_exec": 3, "ShengUfs": 5}
        if with_key:
            names["EldenKeyEventsGlue"] = 2
        sources = capacity.source_inputs()
        reports = {role: {"path": str(self.old_object), "sha256": self.old_hash}
                   for role in ["parent", "core", "clean", "seed"] + (["keystore"] if with_key else [])}
        seed_path = self.folder / "seed.json"
        seed_path.write_text(json.dumps(seed))
        reports["seed"] = {"path": str(seed_path), "sha256": hashlib.sha256(seed_path.read_bytes()).hexdigest()}
        return {
            "profile": "data-capacity-2g-key" if with_key else "data-capacity-2g",
            "base_report": {"profile": "ufs-idle-trial"},
            "expected_data_bytes": 2147483648,
            "actual_keystore_adapter_rebuilt": with_key,
            "changed_core_objects": 1,
            "changed_native_objects": 2 if with_key else 1,
            "scalar": True,
            "objects": {
                name: {"unique_predicates": count,
                       "bindings": [{"old_sha256": self.old_hash}]}
                for name, count in names.items()
            },
            "key_archive_members": {"EldenKeyEventsGlue.o": "b" * 64} if with_key else {},
            "seed_report": seed,
            "seed": {"packed_sha256": seed["packed_sha256"], "raw_sha256": seed["raw_sha256"], "packed_reconstruction_verified": True},
            "inherited_objects": {str(self.old_object): self.old_hash},
            "inherited_sources": {"old-source": self.old_hash},
            "source_inputs": sources,
            "capacity_source_manifest_sha256": sources[capacity.SOURCE_MANIFEST],
            "inherited_build_reports": reports,
        }

    def qualify(self, report):
        path = self.folder / "result.json"
        path.write_text(json.dumps(report))
        # Shared firmware/radio qualification is independently audited. Only
        # that boundary is modeled; capacity's real guards and report run here.
        with patch.object(capacity, "qualify_shared_assets",
                          return_value={"profile": report["profile"]}):
            return capacity.qualify(path, self.folder / "entry.json", self.folder / "runtime")

    def test_core_ufs_only_reports_literal_false(self):
        result = self.qualify(self.report(False))
        self.assertIs(result["keystore_capacity_updated"], False)

    def test_actual_key_adapter_reports_literal_true(self):
        result = self.qualify(self.report(True))
        self.assertIs(result["keystore_capacity_updated"], True)

    def test_key_variant_requires_actual_archive_member(self):
        report = self.report(True)
        report["key_archive_members"] = {}
        with self.assertRaisesRegex(ValueError, "archive was not replaced"):
            self.qualify(report)

    def test_core_ufs_variant_rejects_key_delta(self):
        report = self.report(False)
        report["changed_native_objects"] = 2
        with self.assertRaisesRegex(ValueError, "guard object delta"):
            self.qualify(report)

    def test_adapter_proof_requires_literal_boolean(self):
        for value in ["false", 1, None]:
            with self.subTest(value=value):
                report = self.report(True)
                report["actual_keystore_adapter_rebuilt"] = value
                with self.assertRaisesRegex(ValueError, "KeyStore adapter variant"):
                    self.qualify(report)

    def test_seed_contract_change_is_rejected(self):
        report = self.report(True)
        report["seed_report"]["requested_size_mib"] = 512
        with self.assertRaisesRegex(ValueError, "Seed report differs"):
            self.qualify(report)

    def test_modified_parent_object_is_rejected(self):
        report = self.report(True)
        other = self.folder / "object.o"
        other.write_bytes(b"changed inherited object")
        report["inherited_objects"] = {str(other): self.old_hash}
        with self.assertRaisesRegex(ValueError, "Parent object changed"):
            self.qualify(report)

    def test_unbound_capacity_predicate_is_rejected(self):
        report = self.report(True)
        report["objects"]["EldenKeyEventsGlue"]["bindings"][0]["old_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "Unbound old capacity predicate"):
            self.qualify(report)


    def test_incomplete_source_closure_is_rejected(self):
        report = self.report(True)
        del report["source_inputs"]["tools/build_clean.py"]
        with self.assertRaisesRegex(ValueError, "source closure changed"):
            self.qualify(report)

    def test_changed_inherited_build_report_is_rejected(self):
        report = self.report(True)
        self.old_object.write_bytes(b"modified build proof")
        with self.assertRaisesRegex(ValueError, "Inherited build report changed"):
            self.qualify(report)

    def test_reconstructed_raw_digest_must_match(self):
        report = self.report(True)
        report["seed"]["raw_sha256"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "Seed verification differs"):
            self.qualify(report)


if __name__ == "__main__":
    unittest.main()
