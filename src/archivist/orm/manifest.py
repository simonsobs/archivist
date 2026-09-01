import datetime

from .. import database as db


class Manifest(db.Base):
    """
    A manifest submitted by a Librarian: the authoritative record of one
    archive request, plus its per-file entries.
    """

    __tablename__ = "manifest"

    id = db.Column(db.String(36), primary_key=True)
    "ID identifying this manifest."
    librarian_name = db.Column(db.String(256), nullable=False)
    "The name of the Librarian that generated this manifest."
    created_time = db.Column(db.DateTime, nullable=False)
    "The time this manifest was received."
    total_size_bytes = db.Column(db.BigInteger, nullable=False, default=0)
    "Denormalized cache of the summed size of all entries."
    file_count = db.Column(db.Integer, nullable=False, default=0)
    "Denormalized cache of the number of entries."

    entries = db.relationship(
        "ManifestEntry",
        back_populates="manifest",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    "The per-file entries belonging to this manifest."
    archive = db.relationship(
        "Archive",
        back_populates="manifest",
        uselist=False,  # 1:1, decision 5
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    "The single archive job for this manifest."

    @classmethod
    def get_or_create(cls, session, manifest_id, librarian_name) -> "Manifest":
        existing = session.get(cls, manifest_id)
        if existing is not None:
            return existing
        manifest = cls(
            id=manifest_id,
            librarian_name=librarian_name,
            created_time=datetime.datetime.now(datetime.UTC),
        )
        session.add(manifest)
        return manifest
