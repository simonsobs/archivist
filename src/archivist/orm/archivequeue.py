"""
The ORM definition for the queue of archive jobs awaiting processing.

When the API receives a manifest to archive, it does not perform the
archive operation synchronously. Instead, it places an item in this
queue (backed by the database, so it survives restarts) and a separate
worker thread picks items up and performs the actual archive operation.
"""

import datetime

from sqlalchemy.orm import Session

from .. import database as db


class ArchiveQueue(db.Base):
    """
    The queue of archive jobs awaiting processing.
    """

    __tablename__ = "archive_queue"

    id = db.Column(db.Integer, primary_key=True)
    "The unique identifier for this item in the queue."
    created_time = db.Column(db.DateTime, nullable=False)
    "The time that this item was added to the queue."
    retries = db.Column(db.Integer, nullable=False, default=0)
    "The number of times this item has been tried to be archived."

    manifest_id = db.Column(db.String(256), nullable=False, unique=True)
    "The ID of the manifest associated with this archive."
    manifest = db.Column(db.PickleType, nullable=False)
    "The raw manifest (JSON) that was submitted for archiving."
    paths = db.Column(db.PickleType, nullable=False)
    "The list of file / directory paths contained in the archive."
    root = db.Column(db.String(512), nullable=False)
    "The common root filesystem location for building relative paths."

    consumed = db.Column(db.Boolean, default=False)
    "Whether this queue item has been picked up by a worker."
    consumed_time = db.Column(db.DateTime)
    "The time at which the item was picked up. Useful for pruning."

    completed = db.Column(db.Boolean, default=False)
    "Whether this queue item has been entirely completed."
    completed_time = db.Column(db.DateTime)
    "The time at which the queue item was marked as completed."

    failed = db.Column(db.Boolean, default=False)
    "Whether this queue item failed, and that is the reason for completed status."

    @classmethod
    def new_item(cls, manifest_id: str, manifest: str, paths: list[str], root: str) -> "ArchiveQueue":
        """
        Create a new item in the queue from an incoming archive request.

        Parameters
        ----------
        manifest_id : str
            The ID of the manifest associated with this archive.
        manifest : str
            The raw manifest (JSON) that was submitted for archiving.
        paths : list[str]
            The list of file / directory paths contained in the archive.
        root : str
            The common root filesystem location for building relative paths.
        """

        return cls(
            manifest_id=manifest_id,
            manifest=manifest,
            paths=paths,
            root=root,
            created_time=datetime.datetime.now(datetime.timezone.utc),
            retries=0,
        )

    @classmethod
    def dequeue(cls, session: Session) -> "ArchiveQueue | None":
        """
        Pop the oldest unconsumed item off the queue and mark it as consumed.

        Parameters
        ----------
        session : Session
            The database session to use.
        """

        item = session.query(cls).filter_by(consumed=False).order_by(cls.created_time.asc()).first()

        if item is not None:
            item.consumed = True
            item.consumed_time = datetime.datetime.now(datetime.timezone.utc)
            session.commit()

        return item

    def complete(self, session: Session):
        """
        Mark this queue item as successfully completed.

        Parameters
        ----------
        session : Session
            The database session to use.
        """

        self.completed = True
        self.completed_time = datetime.datetime.now(datetime.timezone.utc)

        session.commit()

    def fail(self, session: Session):
        """
        Mark this queue item as failed.

        Parameters
        ----------
        session : Session
            The database session to use.
        """

        self.failed = True
        self.completed = True
        self.completed_time = datetime.datetime.now(datetime.timezone.utc)

        session.commit()
