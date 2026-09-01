"""
The ORM definition for the queue of archive jobs awaiting processing.

When the API receives a manifest to archive, it does not perform the
archive operation synchronously. Instead, it places an item in this
queue (backed by the database, so it survives restarts) and a separate
worker thread picks items up and performs the actual archive operation.
"""

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .. import database as db
from .manifest import Manifest


class Archive(db.Base):
    """
    The queue of archive jobs awaiting processing.
    """

    __tablename__ = "archive"

    id = db.Column(db.String(36), primary_key=True)
    "Archivist's own ID for the archive, minted here. The Librarian stores it and keys the callback on it."
    manifest_id = db.Column(
        db.String(36), db.ForeignKey("manifest.id", ondelete="CASCADE"), nullable=False, unique=True
    )  # Unique, since there is a 1:1 relationship with the manifest.
    "The ID of the manifest being archived."
    created_time = db.Column(db.DateTime, nullable=False)
    "The time this job was added to the queue."
    retries = db.Column(db.Integer, nullable=False, default=0)
    "The number of times this job has been attempted."

    manifest = db.relationship("Manifest", back_populates="archive")
    "The manifest being archived."

    archive_root = db.Column(db.String(512), nullable=False)
    "The archive root at submit time; snapshotted since settings can change."
    archive_path = db.Column(db.String(2048), nullable=True)
    "The destination path, set on completion."

    consumed = db.Column(db.Boolean, default=False)
    "Whether a worker has picked this job up."
    consumed_time = db.Column(db.DateTime)
    "The time the job was picked up. Useful for pruning."
    completed = db.Column(db.Boolean, default=False)
    "Whether the job has finished (success or failure)."
    completed_time = db.Column(db.DateTime)
    "The time the job was marked completed."
    failed = db.Column(db.Boolean, default=False)
    "Whether the job failed, and that is why it is completed."
    callback_state = db.Column(db.String(16), nullable=False, default="pending")
    "pending | sent | errored | failed | skipped"
    callback_attempts = db.Column(db.Integer, nullable=False, default=0)
    "Number of callback POST attempts made so far."
    callback_last_attempt = db.Column(db.DateTime, nullable=True)
    "When the most recent callback attempt was made."
    callback_next_retry = db.Column(db.DateTime, nullable=True)
    "Earliest time the next callback attempt may run (backoff)."
    callback_last_error = db.Column(db.String(1024), nullable=True)
    "Message from the most recent failed attempt (missing config or POST error)."

    @classmethod
    def new_item(cls, manifest: "Manifest", archive_root: str) -> "Archive":
        return cls(
            # Archivist mints its own archive id: the Librarian stores it in
            # its own column and no longer requires it to equal the manifest
            # id.
            id=str(uuid.uuid4()),
            manifest=manifest,
            archive_root=archive_root,
            created_time=datetime.datetime.now(datetime.UTC),
            retries=0,
        )

    @classmethod
    def dequeue(cls, session: Session) -> "Archive | None":
        stmt = (
            select(cls)
            .options(joinedload(cls.manifest).selectinload(Manifest.entries))
            .with_for_update(skip_locked=True, of=cls)
            .filter_by(consumed=False, completed=False)
            .order_by(cls.created_time.asc())
        )
        item = session.execute(stmt).unique().scalar()
        if item is not None:
            item.consumed = True
            item.consumed_time = datetime.datetime.now(datetime.UTC)
            session.commit()
        return item

    def requeue(self, session: Session):
        """
        Mark this queue item as unconsumed so it can be picked up again.

        Parameters
        ----------
        session : Session
            The database session to use.
        """

        self.consumed = False
        self.consumed_time = None
        self.retries += 1
        session.commit()

    def complete(self, session: Session):
        """
        Mark this queue item as successfully completed.

        Parameters
        ----------
        session : Session
            The database session to use.
        """

        self.completed = True
        self.completed_time = datetime.datetime.now(datetime.UTC)

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
        self.completed_time = datetime.datetime.now(datetime.UTC)

        session.commit()

    def callback_pending(self):
        """Mark this archive as owing a Librarian callback, due immediately.

        Resets the delivery bookkeeping so a fresh (or manually reset) row is
        picked up by the callback worker on its next poll. Does not commit;
        the caller owns the transaction.
        """

        self.callback_state = "pending"
        self.callback_attempts = 0
        self.callback_next_retry = datetime.datetime.now(datetime.UTC)
        self.callback_last_error = None

    def skip_callback(self):
        """Mark this archive as owing no callback (e.g. CLI-submitted jobs)."""

        self.callback_state = "skipped"

    def callback_sent(self):
        """Record a successful callback delivery."""

        self.callback_state = "sent"
        self.callback_last_error = None

    def callback_error(self, error: str, next_retry: datetime.datetime):
        """Record a failed callback attempt to be retried after ``next_retry``."""

        self.callback_state = "errored"
        self.callback_last_error = error
        self.callback_next_retry = next_retry

    def callback_failed(self, error: str):
        """Record a callback attempt that exhausted the retry budget."""

        self.callback_state = "failed"
        self.callback_last_error = error
