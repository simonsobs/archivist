import queue

from archivist.core.models import Archive

_archive_queue: "ArchiveQueue | None" = None
_extract_queue: "ExtractQueue | None" = None


class ArchiveQueue:
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


class ExtractQueue:
    """Thread-safe queue for Extract jobs awaiting processing."""

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


def get_archive_queue() -> ArchiveQueue:
    global _archive_queue
    if _archive_queue is None:
        _archive_queue = ArchiveQueue()
    return _archive_queue


def get_extract_queue() -> ExtractQueue:
    global _extract_queue
    if _extract_queue is None:
        _extract_queue = ExtractQueue()
    return _extract_queue
