"""
Bridge module providing a simple async interface for generating variant explanations.

This is the entry point imported by the CLI:
    from allelio.ai.explanations import generate_explanation
"""

import asyncio
from typing import Optional

from .engine import AIEngine


async def generate_explanation(variant_result, model: Optional[str] = None) -> str:
    """Generate an AI explanation for a single variant result.

    Args:
        variant_result: A VariantResult object from allelio.analysis.lookup
        model: Model name (e.g. 'llama3.1:8b'); defaults to $ALLELIO_MODEL

    Returns:
        Explanation string with disclaimers applied, or raises if no model answers.
    """
    engine = AIEngine(model=model)

    await engine.check_connection()
    # One gate, the same one the CLI and the upload use, and the engine's own
    # sentence for why. A server that will not enumerate its models is not a
    # server that is missing this one, and this used to say it was.
    if not engine.will_explain():
        raise RuntimeError(engine.reason())

    written = await engine.explain(variant_result)
    # "or raises if no model answers" is the documented contract, and until now
    # a failed call returned the variant's own data instead — text that reads
    # like an explanation to a caller that was promised an exception. The
    # record answers it for this call, not for the run: a caller asking about
    # one variant is told about that variant.
    if written.model is None:
        raise RuntimeError(
            written.error
            or f"{engine.provider} at {engine.host} did not answer for '{engine.model}'."
        )
    return written.text
