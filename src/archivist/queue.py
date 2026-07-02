import queue

from archivist.core.models import Archive

_archive_queue: "Queue | None" = None
_extract_queue: "Queue | None" = None


class Queue:
    """Thread-safe queue for Archive jobs awaiting processing."""

    def __init__(self) -> None:
        self._q: queue.Queue[Archive] = queue.Queue()

    def enqueue_archive(self, archive: Archive) -> None:
        self._q.put(archive)

    def dequeue_archive(self, block: bool = True, timeout: float | None = None) -> Archive:
        return self._q.get(block=block, timeout=timeout)

    def task_done(self) -> None:
        self._q.task_done()

    @property
    def size(self) -> int:
        return self._q.qsize()

        return self._q.qsize()


def get_archive_queue() -> Queue:
    global _archive_queue
    if _archive_queue is None:
        _archive_queue = Queue()
    return _archive_queue


def get_extract_queue() -> Queue:
    global _extract_queue
    if _extract_queue is None:
        _extract_queue = Queue()
    return _extract_queue
