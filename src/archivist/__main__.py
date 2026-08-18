import os
import sys
from datetime import datetime
from pathlib import Path

import click
import loguru
import requests

from archivist.core.models import ManifestEntry, ManifestFailedResponse, ManifestRequest, ManifestResponse
from archivist.settings import get_settings
from archivist.utils import _checksum


@click.group()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    required=False,
    help="Path to the Archivist configuration file",
)
@click.pass_context
def main(ctx, config):
    if config is None:
        click.echo("Archivist requires a configuration file", err=True)
        click.echo("See readme for more information", err=True)
        sys.exit(1)

    os.environ["ARCHIVIST_CONFIG_PATH"] = config
    ctx.ensure_object(dict)


@main.command()
@click.option(
    "--source-path", type=click.Path(exists=True), required=True, help="The source path of the file to archive"
)
@click.option(
    "--librarian-name",
    type=str,
    required=False,
    help="The name of the librarian archiving the file (defaults to the reserved CLI name, which never triggers a callback)",
    default=None,
)
@click.option("--manifest-id", type=str, required=False, help="The ID of the manifest to use for archiving")
@click.pass_context
def archive(ctx, source_path, librarian_name, manifest_id):
    """Command to archive a file.
    For example: `archivist -c config archive "--source-path /path/to/source --dest-path /path/to/dest"`

    Submissions authenticate with the token filed under the submitting name in
    `clients`. `--librarian-name` therefore submits as that Librarian, using
    its token: not a privilege escalation, since running the CLI already means
    reading the config file that holds every token in it.
    """
    # Here you would implement the logic to handle the archiving process
    # For now, we will just print the source and destination paths
    click.echo(f"Archiving file from {source_path}")

    settings = get_settings()

    # Unnamed CLI jobs archive under the reserved sentinel name, so the
    # completed job is never reported back to a real Librarian.
    if librarian_name is None:
        librarian_name = settings.cli_librarian_name

    # The CLI submits over the same authenticated endpoint as a Librarian, so
    # it needs the token filed under the name it is submitting as. Resolved
    # before any checksumming: a misconfiguration should not cost a full walk
    # of the source tree first.
    client = settings.clients.get(librarian_name)
    if settings.require_client_auth and (client is None or not client.auth_token):
        click.secho("[ERROR]", fg="red", nl=False, err=True)
        click.echo(
            f" No token configured for '{librarian_name}'; add it under `clients` in the config file.",
            err=True,
        )
        sys.exit(1)

    source_root = Path(source_path).absolute()

    if source_root.is_file():
        files = [source_root]
        walk_root = source_root.parent
    else:
        files = [Path(dirpath) / filename for dirpath, _, filenames in os.walk(source_root) for filename in filenames]
        walk_root = source_root

    uploader = librarian_name
    archive_files = []

    for file_path in files:
        stat = file_path.stat()
        relative_path = file_path.relative_to(settings.local_root)
        loguru.logger.info(f"Archiving file: {file_path}, relative path: {relative_path}")
        archive_files.append(
            ManifestEntry(
                name=str(relative_path),
                create_time=datetime.fromtimestamp(stat.st_ctime),
                size=stat.st_size,
                checksum=_checksum(file_path),
                uploader=uploader,
                source=str(source_root),
                instance_path=str(file_path.absolute()),
                instance_create_time=datetime.now(),
                instance_available=True,
                outgoing_transfer_id=0,
            )
        )
    if not manifest_id:
        manifest_id = str(datetime.now().timestamp()).replace(".", "")

    manifest_request = ManifestRequest(
        manifest_id=manifest_id,
        librarian_name=librarian_name,
        archive_name=settings.name,
        archive_files=archive_files,
    )
    headers = {}
    if client is not None and client.auth_token:
        headers["Authorization"] = f"Bearer {client.auth_token}"

    req = requests.post(
        f"http://{settings.host}:{settings.port}/api/v1/archive",
        json=manifest_request.model_dump(mode="json"),
        headers=headers,
        timeout=30,
    )

    click.echo(f"Status code: {req.status_code}")

    if req.status_code == 200:
        response = ManifestResponse.model_validate(req.json())
        click.echo(f"Archive succeeded, manifest_id={response.manifest_id}")
    else:
        response = ManifestFailedResponse.model_validate(req.json())
        click.secho("[ERROR]", fg="red", nl=False, err=True)
        click.echo(f" Archive failed: {response.error}", err=True)


@main.command()
@click.argument("cmd", nargs=1)
@click.option("--archive", type=str, help="Name of the job")
@click.option(
    "--dest-path",
    type=str,
    help="The destination path where the file should be restored",
)
@click.pass_context
def extract(ctx, archive, dest_path):
    """Command to record a job.
    For example: `slurmise record "-o 2 -i 3 -m fast"`
    """


@main.command()
@click.option("--manifest-id", type=str, required=False, help="The manifest whose callback should be reset to pending")
@click.pass_context
def resend_callback(ctx, manifest_id):
    """Reset the Librarian callback to pending for a manifest whose callback failed or was exhausted.

    Resets the callback bookkeeping on the archive row; the server's callback
    worker picks it up from there. Useful after correcting a Librarian's
    configuration. Runs against the database directly, so the server does not
    need to be reachable.
    """

    from archivist.database import get_session
    from archivist.orm.archive import Archive

    session = get_session()
    try:
        click.echo(f"Resending callback for manifest {manifest_id}...")
        if manifest_id is not None:
            items = session.query(Archive).filter_by(id=manifest_id).all()
        else:
            items = session.query(Archive).filter_by(callback_state="failed").all()
        if manifest_id is not None and not items:
            # A named manifest that matches nothing is an operator mistake, not
            # a no-op worth reporting as success.
            click.secho("[ERROR]", fg="red", nl=False, err=True)
            click.echo(f" No completed archive for manifest {manifest_id}", err=True)
            return
        click.echo(f"Resetting {len(items)} callback(s) to pending.")
        for item in items:
            if not item.completed:
                click.secho("[ERROR]", fg="red", nl=False, err=True)
                click.echo(f" No completed archive for manifest {manifest_id}", err=True)
                return
            item.callback_pending()
            click.echo(f"Callback for {item.id} reset to pending.")
            session.commit()
    finally:
        session.close()


@main.command()
@click.pass_context
def start_server(ctx):
    """Command to check the status of the archivist."""

    import uvicorn

    from .settings import server_settings

    uvicorn.run(
        "archivist.server:main",
        host=server_settings.host,
        port=server_settings.port,
        log_level=server_settings.log_level.lower(),
        factory=True,
    )
