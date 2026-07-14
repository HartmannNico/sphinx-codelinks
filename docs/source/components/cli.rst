.. _cli:

Command Line Interface (CLI)
============================

``Sphinx-CodeLinks`` provides a CLI for users to integrate documentation builds into CI/CD pipelines
and for local development.

It features help pages. Add ``-h`` or ``--help`` to any command to see the available options.

.. typer:: sphinx_codelinks.cmd.app
   :prog: codelinks
   :width: 85
   :preferred: svg
   :theme: monokai
   :show-nested:
   :make-sections:

Treating warnings as errors
===========================

By default, ``codelinks analyse`` exits ``0`` even when it prints warnings. Pass
``-W`` / ``--strict`` to make it exit ``1`` if any non-suppressed warning was
emitted, mirroring ``sphinx-build -W``. This turns broken markers or missing git
metadata into a hard failure — useful as a CI/CD quality gate.

.. code-block:: bash

   codelinks analyse codelinks.toml --strict

The exit-code contract is:

.. list-table::
   :header-rows: 1
   :widths: 60 20 20

   * - Situation
     - without ``-W``
     - with ``-W``
   * - Completed, no warnings
     - ``0``
     - ``0``
   * - Completed, ≥1 non-suppressed warning
     - ``0``
     - ``1``
   * - Uncaught exception / crash
     - ``1``
     - ``1``
   * - Usage / configuration error
     - ``2``
     - ``2``

Because ``-W`` covers *all* warnings, expected ones (for example running outside
a git checkout) can be silenced by listing their slugs in
:ref:`suppress_warnings`. Suppressed warnings never count towards the exit code.
