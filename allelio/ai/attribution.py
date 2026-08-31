"""Who wrote an explanation.

A failed call still answers with the variant's own data wrapped in the
disclaimer, and that reads exactly like an explanation. The difference used to
be kept as a count on the engine, one number for a whole run, and every reader
of it — the CLI's tally, the report's footer, the upload's payload — had its
own idea of which cards the number covered. On a run that wrote some cards and
not others they all agreed on the wrong thing.

So the credit lives on the card. Nothing here imports anything.
"""

from typing import Dict, NamedTuple, Optional


class Explanation(NamedTuple):
    """One explanation and the name of whoever wrote it.

    `model` is the full name of the model that answered — the same string the
    page prints and the report records — or None when the call failed and
    `text` is the variant's own data.

    `error` is why it did not answer, in the server's own words, or None. It
    rides on the card for the same reason the credit does: the engine has one
    slot for it, and the batch runs three calls at a time into that one slot,
    so a card asking why *it* has no model got whichever answer landed last.
    """

    text: str
    model: Optional[str]
    error: Optional[str] = None


class Attribution(NamedTuple):
    """Who wrote a set of cards, and how many of them.

    `model` is None when no card in the set was written by a model.
    """

    model: Optional[str]
    written: int
    total: int


def attribution(explanations: Dict[str, Explanation]) -> Attribution:
    """Read the credit for a set of cards off the cards themselves.

    The one place the CLI's tally, the report's footer and the upload's payload
    derive it, so that they cannot derive it differently.
    """
    written = [e.model for e in explanations.values() if e.model]
    # Sorted rather than first-wins: one run has one model, and if a set ever
    # carries two, naming both is the honest answer and naming one is not.
    names = sorted(set(written))
    return Attribution(
        model=", ".join(names) or None,
        written=len(written),
        total=len(explanations),
    )
