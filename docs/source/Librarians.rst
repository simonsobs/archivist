Registering a Librarian
=======================

A librarian and an archivist talk in both directions: the librarian submits
manifests, and the archivist calls back when an archive is stored. Both directions
use HTTP Basic with the **same** ``user:password`` pair, so there is one credential
to provision.

Registering a librarian takes three steps: generate the credential, configure the
archivist, and register the archivist on the librarian.

Generate the Credential
-----------------------

Write a random password to a file readable by both services:

.. code-block:: bash

    python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")' > authenticator_password

Avoid ``:`` in the password; the librarian splits the authenticator on it.

Configure the Archivist
-----------------------

Add the librarian under both ``clients`` and ``librarians`` in the
:doc:`configuration <Configuration>`, keyed by the librarian's own ``name``
(from its ``server_settings.json``):

.. code-block:: json

    {
      "clients": {
        "princeton_librarian": {
          "username": "archuser",
          "password_file": "/run/secrets/archivist_authenticator"
        }
      },
      "librarians": {
        "princeton_librarian": {
          "url": "http://librarian:21109",
          "username": "archuser",
          "password_file": "/run/secrets/archivist_authenticator"
        }
      }
    }

- ``clients`` lets the librarian submit manifests. The archivist rejects a manifest
  whose ``librarian_name`` does not match the entry the credentials belong to.
- ``librarians`` tells the archivist where to send callbacks. ``url`` is the
  librarian's base URL; the callback path is added to it.
- ``username`` is a free choice and is not the librarian's name.

Restart the archivist to load the change.

Register on the Librarian
-------------------------

On the librarian, register the archivist with the same credential:

.. code-block:: bash

    librarian add-archivist $LIBRARIAN_NAME --name=archivist-princeton
                                            --url=http://archivist
                                            --port=8080
                                            --authenticator=archuser:$password

Then add a ``create_archive`` background task that sends manifests to it. See the
librarian documentation on
`connecting an archivist <https://librarian.readthedocs.io/en/latest/Connections.html>`_
and `background tasks <https://librarian.readthedocs.io/en/latest/Background.html>`_.

Names That Must Match
---------------------

Most registration problems are a mismatch in one of these:

- The librarian's ``name`` is the key under ``clients`` and ``librarians``.
- The archivist's ``name`` is the ``--name`` given to ``add-archivist``, and the
  ``archivist_name`` of the ``create_archive`` task.
- The ``username`` and password are the two halves of ``--authenticator``.
- The task's ``filesize_per_run`` is at most the archivist's ``maximal_size_bytes``.
  A larger manifest is rejected, and the same files are selected again on every run.
