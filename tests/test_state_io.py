"""Tests for state_io.py — atomic, lock-coordinated JSON state I/O (Issue N3)."""
import json
import os
import sys
import threading
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import state_io as sio


class TestReadJson:
    def test_missing_file_returns_default(self, tmp_path):
        p = str(tmp_path / "nope.json")
        assert sio.read_json(p, {"a": 1}) == {"a": 1}

    def test_corrupt_file_returns_default(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        assert sio.read_json(str(p), {"fallback": True}) == {"fallback": True}

    def test_valid_file_round_trips(self, tmp_path):
        p = str(tmp_path / "ok.json")
        payload = {"positions": {"CID": {"x": 1}}, "cluster": {}}
        sio.atomic_write_json(p, payload)
        assert sio.read_json(p, {}) == payload

    def test_unicode_preserved(self, tmp_path):
        p = str(tmp_path / "he.json")
        payload = {"note": "חדר מצב"}
        sio.atomic_write_json(p, payload)
        assert sio.read_json(p, {})["note"] == "חדר מצב"


class TestAtomicWriteJson:
    def test_no_temp_files_left_on_success(self, tmp_path):
        p = str(tmp_path / "s.json")
        sio.atomic_write_json(p, {"k": "v"})
        leftovers = [f for f in os.listdir(tmp_path) if f.startswith(".tmp_state_")]
        assert leftovers == []

    def test_temp_file_cleaned_on_serialize_failure(self, tmp_path):
        p = str(tmp_path / "s.json")
        # object() is not JSON-serializable → json.dump raises mid-write
        with pytest.raises(TypeError):
            sio.atomic_write_json(p, {"bad": object()})
        leftovers = [f for f in os.listdir(tmp_path) if f.startswith(".tmp_state_")]
        assert leftovers == []
        assert not os.path.exists(p)

    def test_existing_file_replaced_not_corrupted_on_failure(self, tmp_path):
        p = str(tmp_path / "s.json")
        sio.atomic_write_json(p, {"good": 1})
        with pytest.raises(TypeError):
            sio.atomic_write_json(p, {"bad": object()})
        # original file must survive intact (os.replace never ran)
        assert sio.read_json(p, None) == {"good": 1}

    def test_overwrite_replaces_content(self, tmp_path):
        p = str(tmp_path / "s.json")
        sio.atomic_write_json(p, {"v": 1})
        sio.atomic_write_json(p, {"v": 2})
        assert sio.read_json(p, {}) == {"v": 2}


class TestFileLock:
    def test_lock_file_created(self, tmp_path):
        target = str(tmp_path / "state.json")
        with sio.file_lock(target):
            assert os.path.exists(sio.lock_path_for(target))

    def test_lock_reacquirable_after_release(self, tmp_path):
        target = str(tmp_path / "state.json")
        with sio.file_lock(target):
            pass
        with sio.file_lock(target):  # must not deadlock
            pass

    def test_noop_when_fcntl_unavailable(self, tmp_path):
        target = str(tmp_path / "state.json")
        with patch.object(sio, "_HAVE_FCNTL", False):
            with sio.file_lock(target):
                pass  # yields without touching a lock file
        assert not os.path.exists(sio.lock_path_for(target))

    def test_concurrent_rmw_no_lost_updates(self, tmp_path):
        """20 threads each do 5 locked read-modify-write increments.
        With the lock, the final counter must equal 100 and the file must
        always be valid JSON (no torn state)."""
        target = str(tmp_path / "counter.json")
        sio.atomic_write_json(target, {"n": 0})

        def worker():
            for _ in range(5):
                with sio.file_lock(target):
                    st = sio.read_json(target, {"n": 0})
                    st["n"] += 1
                    sio.atomic_write_json(target, st)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        final = sio.read_json(target, None)
        assert final == {"n": 100}
