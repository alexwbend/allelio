"""PUB-4 (clean-install smoke test): the documented ways to invoke Allelio work.

The README's install section names the `allelio` console script, and its
troubleshooting section offers `python3 -m allelio` for the common case where
that script isn't on PATH. Both are documented promises to a first-time user,
so both are tested here.
"""

import subprocess
import sys

import allelio.__main__ as main_module
from allelio import cli


def test_module_entrypoint_reuses_the_console_script_group():
    """`python -m allelio` must dispatch to the same Click group as `allelio`."""
    assert main_module.main is cli.main is cli.allelio


def test_python_dash_m_allelio_runs():
    """The README's PATH fallback actually executes and reports the version."""
    result = subprocess.run(
        [sys.executable, "-m", "allelio", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "version" in result.stdout


def test_console_script_entrypoint_is_declared():
    """pyproject's `allelio = allelio.cli:main` target has to resolve."""
    assert callable(cli.main)
