import os
import sys

import click


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
@click.option("--source-path", type=str, help="The source path of the file to archive")
@click.option(
    "--dest-path",
    type=str,
    help="The destination path where the file should be archived",
)
@click.pass_context
def archive(ctx, source_path, dest_path):
    """Command to archive a file.
    For example: `archivist archive "--source-path /path/to/source --dest-path /path/to/dest"`
    """
    pass


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
    pass


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
