from .. import database as db


class ManifestEntry(db.Base):
    """
    One file's authoritative record within a manifest. One shared table keyed
    by the manifest FK -- not a table per manifest. Column set mirrors the
    Pydantic `ManifestEntry` in `core/models.py` 1:1.
    """

    __tablename__ = "manifest_entry"

    id = db.Column(db.Integer, primary_key=True)
    "Surrogate PK; a single file row has no external identity."
    manifest_id = db.Column(
        db.String(36),
        db.ForeignKey("manifest.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    "FK back to the owning manifest."
    name = db.Column(db.String(1024), nullable=False)
    "The name of the file."
    create_time = db.Column(db.DateTime, nullable=False)
    "The time the file was created."
    size = db.Column(db.BigInteger, nullable=False)
    "The size of the file in bytes."
    checksum = db.Column(db.String(256), nullable=False)
    "The sha256 checksum of the file."
    uploader = db.Column(db.String(256), nullable=False)
    "The uploader of the file."
    source = db.Column(db.String(256), nullable=False)
    "The source of the file."
    instance_path = db.Column(db.String(2048), nullable=False)
    "The path to the instance on the store."
    instance_create_time = db.Column(db.DateTime, nullable=False)
    "The time the instance was created."
    instance_available = db.Column(db.Boolean, nullable=False)
    "Whether the instance is available."
    outgoing_transfer_id = db.Column(db.Integer, nullable=False)
    "The ID of the outgoing transfer, if it exists."

    manifest = db.relationship("Manifest", back_populates="entries")
    "The owning manifest."
