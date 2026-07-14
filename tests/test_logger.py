# Test suite for the environment-aware logging facade (issue #72).
import importlib
import logging

import pytest
from sphinx.util.logging import VERBOSE

from sphinx_codelinks import logger as logmod


@pytest.fixture(autouse=True)
def _reset_backend():
    """Each test starts and ends with the default (library) backend."""
    logmod.reset()
    logmod.logger.configure(verbose=False, quiet=False)
    yield
    logmod.reset()
    logmod.logger.configure(verbose=False, quiet=False)


def test_default_backend_drops_info_and_emits_warning(caplog):
    """As a plain library (no frontend configured), routine INFO is silently
    dropped while genuine warnings still propagate."""
    log = logmod.get_logger("sphinx_codelinks.analyse.sample")

    log.info("routine progress")
    log.warning("real problem", subtype="git.root")

    messages = [record.getMessage() for record in caplog.records]
    assert "routine progress" not in messages
    assert "real problem" in messages


def test_cli_backend_routes_info_to_stdout_and_warning_to_stderr(capsys):
    """CLI frontend: routine progress goes to stdout, warnings to stderr."""
    logmod.configure_cli(verbose=False, quiet=False)
    log = logmod.get_logger("sphinx_codelinks.analyse.sample")

    log.info("files loaded: 3")
    log.warning("git root not found", subtype="git.root")

    captured = capsys.readouterr()
    assert "files loaded: 3" in captured.out
    assert "files loaded: 3" not in captured.err
    assert "git root not found" in captured.err
    assert "git root not found" not in captured.out


def test_cli_backend_quiet_suppresses_info_but_keeps_warning(capsys):
    """--quiet hides routine progress but never hides warnings."""
    logmod.configure_cli(verbose=False, quiet=True)
    log = logmod.get_logger("sphinx_codelinks.analyse.sample")

    log.info("files loaded: 3")
    log.warning("git root not found", subtype="git.root")

    captured = capsys.readouterr()
    assert "files loaded: 3" not in captured.out
    assert "git root not found" in captured.err


def test_cli_backend_debug_is_gated_by_verbose(capsys):
    """CLI frontend: detailed debug output is hidden by default, shown with -v."""
    logmod.configure_cli(verbose=False, quiet=False)
    logmod.get_logger("sphinx_codelinks.analyse.sample").debug("breakdown detail")
    assert "breakdown detail" not in capsys.readouterr().out

    logmod.configure_cli(verbose=True, quiet=False)
    logmod.get_logger("sphinx_codelinks.analyse.sample").debug("breakdown detail")
    assert "breakdown detail" in capsys.readouterr().out


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_sphinx_backend_routes_through_sphinx_logging():
    """Sphinx frontend: info is default-visible (INFO), debug is -v only
    (VERBOSE), warnings carry the codelinks type/subtype; all under sphinx.*"""
    logmod.configure_sphinx()

    handler = _ListHandler()
    sphinx_logger = logging.getLogger("sphinx")
    sphinx_logger.addHandler(handler)
    old_level = sphinx_logger.level
    sphinx_logger.setLevel(VERBOSE)
    try:
        log = logmod.get_logger("sphinx_codelinks.analyse.sample")
        log.info("project summary")
        log.debug("breakdown detail")
        log.warning("git root not found", subtype="git.root", location="x.cpp")
    finally:
        sphinx_logger.removeHandler(handler)
        sphinx_logger.setLevel(old_level)

    # routed under the sphinx-prefixed namespace Sphinx actually captures
    assert all(
        rec.name == "sphinx.sphinx_codelinks.analyse.sample" for rec in handler.records
    )

    info_records = [r for r in handler.records if "project summary" in r.getMessage()]
    assert info_records and info_records[0].levelno == logging.INFO

    debug_records = [r for r in handler.records if "breakdown detail" in r.getMessage()]
    assert debug_records and debug_records[0].levelno == VERBOSE

    warn_records = [
        r for r in handler.records if "git root not found" in r.getMessage()
    ]
    assert warn_records
    assert warn_records[0].levelno == logging.WARNING
    assert getattr(warn_records[0], "type", None) == "codelinks"
    assert getattr(warn_records[0], "subtype", None) == "git.root"


ANALYSE_MODULE_LOGGERS = (
    "sphinx_codelinks.analyse.analyse",
    "sphinx_codelinks.analyse.oneline_parser",
    "sphinx_codelinks.analyse.projects",
    "sphinx_codelinks.analyse.utils",
)


def test_analyse_modules_install_no_handlers_at_import():
    """Regression guard for #72: importing the analyse layer must not install
    handlers or pin levels on its own loggers."""
    for name in ANALYSE_MODULE_LOGGERS:
        importlib.import_module(name)
        module_logger = logging.getLogger(name)
        assert module_logger.handlers == [], (
            f"{name} installed handlers at import: {module_logger.handlers}"
        )
        assert module_logger.level == logging.NOTSET, (
            f"{name} pinned its level at import to {module_logger.level}"
        )


def test_registry_lists_all_warning_slugs():
    """The canonical registry names every warning slug analyse can emit."""
    assert logmod.CODELINKS_WARNING_SLUGS == (
        "codelinks.git.root",
        "codelinks.git.config",
        "codelinks.git.remote",
        "codelinks.git.head",
        "codelinks.git.ref",
        "codelinks.git.host",
        "codelinks.marker.too_many_fields",
        "codelinks.marker.too_few_fields",
        "codelinks.marker.missing_square_brackets",
        "codelinks.marker.not_start_or_end_with_square_brackets",
        "codelinks.marker.newline_in_field",
    )


def test_cli_backend_counts_non_suppressed_warnings(capsys):
    """The CLI backend is the single choke point that counts warnings and
    surfaces each slug so users know what to suppress."""
    logmod.configure_cli()
    log = logmod.get_logger("sphinx_codelinks.analyse.sample")

    log.warning("git root not found", subtype="git.root")
    log.warning("too many fields", subtype="marker.too_many_fields")

    err = capsys.readouterr().err
    assert logmod.cli_warning_count() == 2
    assert "git root not found" in err
    assert "codelinks.git.root" in err
    assert "codelinks.marker.too_many_fields" in err


def test_cli_backend_drops_suppressed_warnings(capsys):
    """A suppressed warning is neither printed nor counted."""
    logmod.configure_cli(suppress_warnings=["codelinks.git"])
    log = logmod.get_logger("sphinx_codelinks.analyse.sample")

    log.warning("git root not found", subtype="git.root")
    log.warning("too many fields", subtype="marker.too_many_fields")

    err = capsys.readouterr().err
    assert logmod.cli_warning_count() == 1
    assert "git root not found" not in err
    assert "too many fields" in err


def test_cli_backend_without_subtype_uses_bare_codelinks_slug(capsys):
    """A warning without a subtype still counts and is suppressible via the
    bare ``codelinks`` slug."""
    logmod.configure_cli(suppress_warnings=["codelinks"])
    logmod.get_logger("x").warning("no subtype")
    assert logmod.cli_warning_count() == 0
    assert capsys.readouterr().err == ""


def test_set_cli_suppress_warnings_updates_active_backend(capsys):
    """The suppression list can be set after the backend is configured (the
    CLI learns it only once the TOML config is loaded)."""
    logmod.configure_cli()
    logmod.set_cli_suppress_warnings(["codelinks"])
    logmod.get_logger("x").warning("anything", subtype="git.root")

    assert logmod.cli_warning_count() == 0
    assert capsys.readouterr().err == ""


def test_cli_warning_count_is_zero_without_a_cli_backend():
    """Querying the count under the default/library backend is safe."""
    logmod.reset()
    assert logmod.cli_warning_count() == 0


@pytest.mark.parametrize(
    ("slug", "patterns", "expected"),
    [
        # a bare parent silences the whole hierarchy below it
        ("codelinks.git.root", ["codelinks"], True),
        ("codelinks.marker.too_many_fields", ["codelinks"], True),
        # family level silences only that family
        ("codelinks.git.root", ["codelinks.git"], True),
        ("codelinks.git.host", ["codelinks.git"], True),
        ("codelinks.marker.too_many_fields", ["codelinks.git"], False),
        # matching is on dot boundaries, never a raw string prefix
        ("codelinks.github", ["codelinks.git"], False),
        # exact leaf silences only that leaf
        ("codelinks.git.root", ["codelinks.git.root"], True),
        ("codelinks.git.host", ["codelinks.git.root"], False),
        # a trailing ".*" is accepted as a Sphinx-style alias for the parent
        ("codelinks.git.root", ["codelinks.git.*"], True),
        ("codelinks.marker.newline_in_field", ["codelinks.*"], True),
        # no patterns suppress nothing
        ("codelinks.git.root", [], False),
        # any matching pattern wins
        (
            "codelinks.marker.newline_in_field",
            ["codelinks.git", "codelinks.marker"],
            True,
        ),
    ],
)
def test_is_suppressed(slug, patterns, expected):
    assert logmod.is_suppressed(slug, patterns) is expected


def test_git_metadata_warnings_use_dotted_codelinks_slugs(tmp_path, capsys):
    """Every git-metadata warning surfaces under ``codelinks.git.<name>`` so it
    is suppressible with the same hierarchical slugs as marker warnings."""
    from sphinx_codelinks.analyse import utils

    logmod.configure_cli()

    # git.root: no .git anywhere above the directory
    utils.locate_git_root(tmp_path / "no_repo")

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    # git.config: .git exists but no config file
    utils.get_remote_url(repo)
    # git.remote: config present but no remote url
    (repo / ".git" / "config").write_text("[core]\n")
    utils.get_remote_url(repo)
    # git.head: no .git/HEAD
    utils.get_current_rev(repo)
    # git.ref: HEAD points at a ref file that does not exist
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    utils.get_current_rev(repo)
    # git.host: unsupported git hosting platform
    utils.form_https_url("git@bitbucket.org:o/r.git", "rev", repo, repo / "f.c", 1)

    err = capsys.readouterr().err
    for slug in (
        "codelinks.git.root",
        "codelinks.git.config",
        "codelinks.git.remote",
        "codelinks.git.head",
        "codelinks.git.ref",
        "codelinks.git.host",
    ):
        assert slug in err, f"missing {slug} in:\n{err}"
    assert logmod.cli_warning_count() == 6
