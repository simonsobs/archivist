import queue

from archivist.storage.base import Storage

_status_queue: "Queue | None" = None


class Queue:
    """Thread-safe queue for Archive jobs awaiting processing."""

    def __init__(self) -> None:
        self._q: queue.Queue[Storage] = queue.Queue()

    def enqueue(self, item: Storage) -> None:
        self._q.put(item)

    def dequeue(self, block: bool = True, timeout: float | None = None) -> Storage:
        item = self._q.get(block=block, timeout=timeout)
        return item

    def task_done(self) -> None:
        self._q.task_done()

    @property
    def size(self) -> int:
        return self._q.qsize()


def get_status_queue() -> Queue:
    global _status_queue
    if _status_queue is None:
        _status_queue = Queue()
    return _status_queue
