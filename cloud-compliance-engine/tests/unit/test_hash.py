"""Unit tests for canonical hashing."""
import pytest
from app.services.hash_utils import canonical_hash, record_hash, snapshot_hash_from_record_hashes, rule_definition_hash


def test_canonical_hash_stable():
    obj = {"a": 1, "b": 2, "c": 3}
    h1 = canonical_hash(obj)
    h2 = canonical_hash({"c": 3, "a": 1, "b": 2})
    assert h1 == h2


def test_canonical_hash_different():
    assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})
    assert canonical_hash({"a": 1}) != canonical_hash({"b": 1})


def test_record_hash():
    row = {"name": "b1", "region": "us-east-1"}
    h = record_hash(row)
    assert len(h) == 64
    assert h == record_hash({"region": "us-east-1", "name": "b1"})


def test_snapshot_hash_from_record_hashes():
    hashes = ["a", "b", "c"]
    h = snapshot_hash_from_record_hashes(hashes)
    assert h != snapshot_hash_from_record_hashes(["a", "c", "b"])
    assert h == snapshot_hash_from_record_hashes(hashes)


def test_rule_definition_hash():
    rule = {"control_id": "2.3", "control_ref": "iam-root-access-keys", "pass_rule": "zero_rows", "required_columns": ["account_id"]}
    h = rule_definition_hash(rule)
    assert len(h) == 64
