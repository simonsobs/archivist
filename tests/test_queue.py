# Copyright (c) 2025-2026 Simons Observatory.
# Full license can be found in the top level "LICENSE" file.

"""Tests for archivist.queue.Queue and get_status_queue."""

import queue as stdlib_queue
import unittest

from archivist.queue import Queue, get_status_queue


class TestQueue(unittest.TestCase):
    def test_new_queue_is_empty(self):
        q = Queue()
        self.assertEqual(q.size, 0)

    def test_enqueue_increases_size(self):
        q = Queue()
        q.enqueue("item")
        self.assertEqual(q.size, 1)

    def test_dequeue_returns_enqueued_item_fifo(self):
        q = Queue()
        q.enqueue("first")
        q.enqueue("second")

        self.assertEqual(q.dequeue(), "first")
        self.assertEqual(q.dequeue(), "second")

    def test_dequeue_nonblocking_raises_when_empty(self):
        q = Queue()
        with self.assertRaises(stdlib_queue.Empty):
            q.dequeue(block=False)

    def test_task_done_does_not_raise_after_dequeue(self):
        q = Queue()
        q.enqueue("item")
        q.dequeue()
        q.task_done()


class TestGetStatusQueue(unittest.TestCase):
    def test_returns_singleton(self):
        first = get_status_queue()
        second = get_status_queue()
        self.assertIs(first, second)

    def test_returns_a_queue_instance(self):
        self.assertIsInstance(get_status_queue(), Queue)


if __name__ == "__main__":
    unittest.main()
