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
from sqlalchemy.orm import Session, joinedload, selectinload

from .. import database as db
from .manifest import Manifest


class Archive(db.Base):
    """
    The queue of archive jobs awaiting processing.
    """

    __tablename__ = "archive"

    id = db.Column(db.String(36), primary_key=True)  # archivist-minted uuid4
    "Archivist-minted uuid4 identifying this archive job."
    created_time = db.Column(db.DateTime, nullable=False)
    "The time this job was added to the queue."
    retries = db.Column(db.Integer, nullable=False, default=0)
    "The number of times this job has been attempted."

    manifest_id = db.Column(
        db.String(36),
        db.ForeignKey("manifest.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # 1:1
    )
    "FK to the manifest being archived (unique -> 1:1)."
    manifest = db.relationship("Manifest", back_populates="archive")
    "The manifest being archived."

    archive_root = db.Column(db.String(512), nullable=False)
    "The archive root at submit time; snapshotted since settings can change."
    archive_path = db.Column(db.String(2048), nullable=True)
    "The destination path, set on completion."

    librarian_archive_id = db.Column(db.String(2048), nullable=True, unique=True)
    "Site-specific identifier supplied by the Librarian callback contract."

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

    @classmethod
    def new_item(cls, manifest: "Manifest", archive_root: str) -> "Archive":
        return cls(
            id=str(uuid.uuid4()),
            manifest=manifest,
            archive_root=archive_root,
            created_time=datetime.datetime.now(datetime.timezone.utc),
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
            item.consumed_time = datetime.datetime.now(datetime.timezone.utc)
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
