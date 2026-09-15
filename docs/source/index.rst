Welcome to Archivist's documentation!
=====================================

The archivist is a service for long-term storage of data tracked by a
`librarian <https://librarian.readthedocs.io>`_. A librarian sends the archivist
a manifest describing a batch of files; the archivist copies those files from the
librarian's stores into archive storage, and calls the librarian back when they
are stored. File data is never sent over HTTP: the archivist reads it in place.

The archivist is made up of four parts:

- The HTTP server, a FastAPI server that accepts manifests from librarians.
- The database, a PostgreSQL database that records manifests and the state of
  each archive job.
- The background workers, which copy files into archive storage and send
  callbacks to librarians.
- The command-line client, used to start the server and manage archive jobs.

Indices and tables
==================

.. toctree::
    :maxdepth: 2

    Deployment
    Configuration
    Librarians
    Operations
