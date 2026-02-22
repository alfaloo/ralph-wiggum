"""Unit tests for ralph/locks.py — atomic, cross-process-safe JSON file I/O."""

import json
import threading
from unittest.mock import patch

import pytest

from ralph.locks import locked_json_rw, read_json, write_json


# ===========================================================================
# locked_json_rw — basic read/modify/write behaviour
# ===========================================================================


class TestLockedJsonRw:
    def test_reads_existing_json(self, tmp_path):
        """locked_json_rw yields the parsed JSON object."""
        p = tmp_path / "data.json"
        p.write_text(json.dumps({"key": "value", "num": 42}))

        with locked_json_rw(str(p)) as data:
            assert data["key"] == "value"
            assert data["num"] == 42

    def test_modification_is_persisted(self, tmp_path):
        """Modifying the yielded dict writes the updated content back to disk."""
        p = tmp_path / "data.json"
        p.write_text(json.dumps({"counter": 0}))

        with locked_json_rw(str(p)) as data:
            data["counter"] = 99

        result = json.loads(p.read_text())
        assert result["counter"] == 99

    def test_adding_key_is_persisted(self, tmp_path):
        """New keys added inside the block are written back."""
        p = tmp_path / "data.json"
        p.write_text(json.dumps({"existing": True}))

        with locked_json_rw(str(p)) as data:
            data["new_key"] = "hello"

        result = json.loads(p.read_text())
        assert result["existing"] is True
        assert result["new_key"] == "hello"

    def test_no_modification_still_writes_back(self, tmp_path):
        """Even without modification the file is rewritten (same content)."""
        original = {"a": 1, "b": [1, 2, 3]}
        p = tmp_path / "data.json"
        p.write_text(json.dumps(original))

        with locked_json_rw(str(p)) as data:
            pass  # no modification

        result = json.loads(p.read_text())
        assert result == original

    def test_works_with_list_root(self, tmp_path):
        """locked_json_rw handles JSON arrays at the root level."""
        p = tmp_path / "state.json"
        p.write_text(json.dumps([{"iteration": 1}]))

        with locked_json_rw(str(p)) as data:
            data.append({"iteration": 2})

        result = json.loads(p.read_text())
        assert len(result) == 2
        assert result[1]["iteration"] == 2

    def test_exception_inside_block_does_not_write_file(self, tmp_path):
        """If an exception is raised inside the block, changes are NOT written back."""
        original = {"v": 1}
        p = tmp_path / "data.json"
        p.write_text(json.dumps(original))

        with pytest.raises(ValueError, match="simulated error"):
            with locked_json_rw(str(p)) as data:
                data["v"] = 999
                raise ValueError("simulated error")

        result = json.loads(p.read_text())
        assert result == original, "File must not be modified when exception is raised"

    def test_multiple_sequential_rw_accumulate_correctly(self, tmp_path):
        """Sequential locked_json_rw calls each see the previous write."""
        p = tmp_path / "data.json"
        p.write_text(json.dumps({"n": 0}))

        for _ in range(5):
            with locked_json_rw(str(p)) as data:
                data["n"] += 1

        result = json.loads(p.read_text())
        assert result["n"] == 5


# ===========================================================================
# Atomic write integrity
# ===========================================================================


class TestAtomicWriteIntegrity:
    def test_original_untouched_when_os_replace_fails_in_write_json(self, tmp_path):
        """If os.replace raises, the original file is not corrupted."""
        original = {"safe": True, "value": 42}
        p = tmp_path / "data.json"
        p.write_text(json.dumps(original))

        with patch("ralph.locks.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                write_json(str(p), {"corrupted": True})

        # Original must be untouched
        result = json.loads(p.read_text())
        assert result == original

    def test_tmp_file_cleaned_up_on_os_replace_failure_in_write_json(self, tmp_path):
        """If os.replace raises inside write_json, the .tmp file is removed."""
        p = tmp_path / "data.json"
        p.write_text(json.dumps({"v": 1}))

        with patch("ralph.locks.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                write_json(str(p), {"v": 2})

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"Stale .tmp files found: {tmp_files}"

    def test_original_untouched_when_os_replace_fails_in_locked_json_rw(self, tmp_path):
        """locked_json_rw: original file untouched if os.replace raises during write."""
        original = {"counter": 7}
        p = tmp_path / "data.json"
        p.write_text(json.dumps(original))

        with patch("ralph.locks.os.replace", side_effect=OSError("boom")):
            with pytest.raises(OSError, match="boom"):
                with locked_json_rw(str(p)) as data:
                    data["counter"] = 999

        result = json.loads(p.read_text())
        assert result == original

    def test_tmp_file_cleaned_up_on_os_replace_failure_in_locked_json_rw(self, tmp_path):
        """locked_json_rw: .tmp file removed if os.replace raises."""
        p = tmp_path / "data.json"
        p.write_text(json.dumps({"v": 1}))

        with patch("ralph.locks.os.replace", side_effect=OSError("boom")):
            with pytest.raises(OSError):
                with locked_json_rw(str(p)) as data:
                    data["v"] = 2

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"Stale .tmp files found: {tmp_files}"


# ===========================================================================
# Concurrent writes — thread safety and mutual exclusion
# ===========================================================================


class TestConcurrentWrites:
    def test_concurrent_locked_json_rw_no_lost_updates(self, tmp_path):
        """20 threads each increment a counter via locked_json_rw; final value must be 20."""
        N = 20
        p = tmp_path / "counter.json"
        p.write_text(json.dumps({"counter": 0}))

        errors = []

        def increment():
            try:
                with locked_json_rw(str(p)) as data:
                    data["counter"] += 1
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=increment) for _ in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        result = json.loads(p.read_text())
        assert result["counter"] == N, (
            f"Expected counter={N}, got {result['counter']} — lost updates detected"
        )

    def test_concurrent_locked_json_rw_list_append(self, tmp_path):
        """N threads each append to a JSON list; final list length must equal N."""
        N = 15
        p = tmp_path / "list.json"
        p.write_text(json.dumps([]))

        errors = []

        def append_item(i):
            try:
                with locked_json_rw(str(p)) as data:
                    data.append(i)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=append_item, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        result = json.loads(p.read_text())
        assert len(result) == N, (
            f"Expected {N} items, got {len(result)} — lost appends detected"
        )
        assert sorted(result) == list(range(N))

    def test_locked_json_rw_mutual_exclusion(self, tmp_path):
        """Only one thread can be inside locked_json_rw at a time."""
        p = tmp_path / "data.json"
        p.write_text(json.dumps({"v": 0}))

        inside_count = [0]
        max_inside = [0]
        meta_lock = threading.Lock()
        errors = []

        def worker():
            try:
                with locked_json_rw(str(p)) as data:
                    with meta_lock:
                        inside_count[0] += 1
                        max_inside[0] = max(max_inside[0], inside_count[0])

                    data["v"] += 1

                    with meta_lock:
                        inside_count[0] -= 1
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        assert max_inside[0] == 1, (
            f"Multiple threads were inside locked_json_rw simultaneously "
            f"(max concurrent: {max_inside[0]})"
        )
        result = json.loads(p.read_text())
        assert result["v"] == 10

    def test_concurrent_write_json_produces_valid_json(self, tmp_path):
        """Concurrent write_json calls all succeed and the file is valid JSON after."""
        N = 10
        p = tmp_path / "data.json"
        p.write_text(json.dumps({"items": []}))

        errors = []

        def write_item(i):
            try:
                write_json(str(p), {"item": i})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=write_item, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        # File must contain valid JSON (one of the N writes won the last slot)
        content = p.read_text()
        parsed = json.loads(content)
        assert "item" in parsed
        assert parsed["item"] in range(N)


# ===========================================================================
# read_json
# ===========================================================================


class TestReadJson:
    def test_read_json_parses_dict(self, tmp_path):
        """read_json parses a JSON object from disk."""
        p = tmp_path / "data.json"
        data = {"key": "value", "num": 3.14, "flag": True}
        p.write_text(json.dumps(data))

        result = read_json(str(p))
        assert result == data

    def test_read_json_parses_list(self, tmp_path):
        """read_json handles JSON arrays."""
        p = tmp_path / "state.json"
        data = [{"a": 1}, {"b": 2}]
        p.write_text(json.dumps(data))

        result = read_json(str(p))
        assert result == data

    def test_read_json_does_not_modify_file(self, tmp_path):
        """read_json leaves the file byte-for-byte unchanged."""
        p = tmp_path / "data.json"
        original_text = json.dumps({"unchanged": True})
        p.write_text(original_text)

        read_json(str(p))

        assert p.read_text() == original_text

    def test_read_json_nested_structure(self, tmp_path):
        """read_json handles deeply nested structures."""
        p = tmp_path / "nested.json"
        data = {"level1": {"level2": {"level3": [1, 2, 3]}}}
        p.write_text(json.dumps(data))

        result = read_json(str(p))
        assert result["level1"]["level2"]["level3"] == [1, 2, 3]

    def test_read_json_empty_object(self, tmp_path):
        """read_json handles an empty JSON object."""
        p = tmp_path / "empty.json"
        p.write_text("{}")

        result = read_json(str(p))
        assert result == {}

    def test_read_json_empty_array(self, tmp_path):
        """read_json handles an empty JSON array."""
        p = tmp_path / "empty.json"
        p.write_text("[]")

        result = read_json(str(p))
        assert result == []


# ===========================================================================
# write_json
# ===========================================================================


class TestWriteJson:
    def test_write_json_creates_new_file(self, tmp_path):
        """write_json creates a file that does not yet exist."""
        p = tmp_path / "new.json"
        assert not p.exists()

        write_json(str(p), {"created": True})

        assert p.exists()
        result = json.loads(p.read_text())
        assert result == {"created": True}

    def test_write_json_writes_correct_content(self, tmp_path):
        """write_json persists the given data as valid JSON."""
        p = tmp_path / "out.json"
        data = {"tasks": [1, 2, 3], "done": False}
        write_json(str(p), data)

        result = json.loads(p.read_text())
        assert result == data

    def test_write_json_overwrites_existing_file(self, tmp_path):
        """write_json replaces the content of an existing file."""
        p = tmp_path / "out.json"
        p.write_text(json.dumps({"old": True}))

        write_json(str(p), {"new": True})

        result = json.loads(p.read_text())
        assert result == {"new": True}
        assert "old" not in result

    def test_write_json_complex_data(self, tmp_path):
        """write_json handles complex nested data structures."""
        p = tmp_path / "complex.json"
        data = {
            "tasks": [
                {"id": "T1", "status": "completed", "deps": []},
                {"id": "T2", "status": "pending", "deps": ["T1"]},
            ],
            "version": 1,
        }
        write_json(str(p), data)

        result = json.loads(p.read_text())
        assert result == data

    def test_write_json_produces_valid_json(self, tmp_path):
        """Content written by write_json is valid JSON parseable by json.loads."""
        p = tmp_path / "data.json"
        write_json(str(p), [1, "two", 3.0, None, True, False])

        content = p.read_text()
        parsed = json.loads(content)
        assert parsed == [1, "two", 3.0, None, True, False]

    def test_write_json_output_is_indented(self, tmp_path):
        """write_json produces indented (human-readable) JSON."""
        p = tmp_path / "data.json"
        write_json(str(p), {"key": "value"})

        content = p.read_text()
        assert "\n" in content
