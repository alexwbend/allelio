"""Entry point for `python -m allelio`.

The README's troubleshooting section offers this as the fallback when the
`allelio` console script isn't on PATH (a common first-install wall on macOS
and on distros that put user scripts somewhere PATH doesn't reach), so it has
to actually work.
"""

from allelio.cli import main

if __name__ == "__main__":
    main()
