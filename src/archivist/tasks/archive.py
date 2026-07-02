from time import sleep

import loguru
from sqlalchemy import inspect

from archivist.database import get_session
from archivist.orm.archivequeue import ArchiveQueue
from archivist.settings import get_settings


def start_archive(librarian_name: str, store_files: bool = True):
    """
    Start an archive process by sending a request to the archivist server.
    """
    settings = get_settings()

    session = get_session()
    try:
        archive_item = ArchiveQueue.dequeue(session)
        if archive_item is not None:
            archive_dict = {c.key: getattr(archive_item, c.key) for c in inspect(archive_item).mapper.column_attrs}
            loguru.logger.info(f"Archive Item: {archive_dict}")
    finally:
        session.close()
    sleep(1)
