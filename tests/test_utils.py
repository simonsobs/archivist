# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.utils._checksum."""

import hashlib
import os
import tempfile
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from archivist.utils import _checksum


def _write_tmp_file(data: bytes) -> str:
    fd, path = tempfile.mkstemp()
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    return path


class TestChecksum(unittest.TestCase):
    def setUp(self):
        self._paths = []

    def tearDown(self):
        for path in self._paths:
            os.remove(path)

    def _tmp_file(self, data: bytes) -> str:
        path = _write_tmp_file(data)
        self._paths.append(path)
        return path

    def test_empty_file(self):
        path = self._tmp_file(b"")
        self.assertEqual(_checksum(path), hashlib.sha256(b"").hexdigest())

    def test_known_value(self):
        path = self._tmp_file(b"hello world")
        self.assertEqual(_checksum(path), hashlib.sha256(b"hello world").hexdigest())

    def test_larger_than_chunk_size(self):
        data = b"x" * (1024 * 1024 + 17)
        path = self._tmp_file(data)
        self.assertEqual(_checksum(path), hashlib.sha256(data).hexdigest())


class TestChecksumProperty(unittest.TestCase):
    @given(st.binary(max_size=1 << 16))
    @settings(deadline=None)
    def test_matches_hashlib_for_arbitrary_bytes(self, data: bytes):
        path = _write_tmp_file(data)
        try:
            self.assertEqual(_checksum(path), hashlib.sha256(data).hexdigest())
        finally:
            os.remove(path)

    @given(st.binary(min_size=1, max_size=4096))
    @settings(deadline=None)
    def test_is_deterministic(self, data: bytes):
        path = _write_tmp_file(data)
        try:
            self.assertEqual(_checksum(path), _checksum(path))
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
