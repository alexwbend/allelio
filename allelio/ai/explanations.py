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
        model: Ollama model name (e.g. 'llama3.1:8b')

    Returns:
        Explanation string with disclaimers applied, or raises if Ollama unavailable.
    """
    engine = AIEngine(model=model)

    connected = await engine.check_connection()
    if not connected:
        raise RuntimeError("Cannot connect to Ollama. Is it running? (ollama serve)")

    model_ok = await engine.check_model_available()
    if not model_ok:
        raise RuntimeError(
            f"Model '{engine.model}' not found in Ollama. "
            f"Pull it with: ollama pull {engine.model}"
        )

    return await engine.explain_variant(variant_result)
