Operations
==========

Command Line
------------

Every command takes the configuration file with ``-c``. Inside the container, run
them with ``podman exec archivist archivist -c /etc/archivist/config.json ...``.

- ``start-server``: Starts the HTTP server and background workers. This is the
  container's default command.
- ``archive --source-path $PATH``: Submits a file or directory under ``local_root``
  to the running server, without a librarian. Needs a ``__cli__`` entry under
  ``clients``. No callback is sent.
- ``requeue-archive --manifest-id $ID``: Stores an archive again. Use it for an
  archive that failed, or completed without all of its files. Files already
  present at the right size are skipped.
- ``resend-callback --manifest-id $ID``: Sends the callback for a completed
  archive again. Without ``--manifest-id``, resends every failed callback.

Archive Jobs
------------

Each manifest becomes one archive job. Jobs are copied in the order they arrive.
When a job finishes, it is marked completed or failed, and a completed job's
callback is sent to its librarian.

If the archivist restarts during a copy, the job is checked on startup: if every
file is present it is marked completed, otherwise it is queued again, up to
``max_archive_retries`` times.

A job fails when any file still cannot be copied after ``copy_attempts``. The error
is logged as ``Archive <manifest_id> failed to store``. No callback is sent for a
failed job; fix the cause and run ``requeue-archive``.

Checking State
--------------

To see the state of recent jobs:

.. code-block:: bash

    podman exec archivist-database psql -U archivist -d archivist -c \
      "SELECT manifest_id, completed, failed, callback_state, callback_last_error
         FROM archive ORDER BY created_time DESC LIMIT 20;"

The archivist also serves a health endpoint at ``/health``.
