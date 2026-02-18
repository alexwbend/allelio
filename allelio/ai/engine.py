"""
Ollama LLM integration for Allelio AI explanation engine.

This module provides async interfaces to an Ollama instance running locally
for generating plain-language explanations of genetic variants.
"""

import asyncio
from typing import Dict, List, Optional, Callable

try:
    from ollama import AsyncClient
except ImportError:
    AsyncClient = None

from .prompts import build_variant_prompt, SYSTEM_PROMPT
from .safety import check_safety, get_variant_warnings, wrap_with_disclaimer


DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_HOST = "http://localhost:11434"


class AIEngine:
    """
    AI explanation engine using Ollama for local LLM inference.
    """
    
    def __init__(self, model: Optional[str] = None, host: Optional[str] = None):
        """
        Initialize the AI engine.
        
        Args:
            model: Model identifier (defaults to DEFAULT_MODEL)
            host: Ollama host URL (defaults to http://localhost:11434)
        """
        self.model = model or DEFAULT_MODEL
        self.host = host or DEFAULT_HOST
        
        if AsyncClient is None:
            self.client = None
        else:
            self.client = AsyncClient(host=self.host)
        
        self.available = False
    
    async def check_connection(self) -> bool:
        """
        Check if connection to Ollama is available.
        
        Returns:
            True if Ollama is reachable, False otherwise
        """
        if self.client is None:
            return False
        
        try:
            # Try a simple tags request to verify connection
            await asyncio.wait_for(self.client.list(), timeout=5)
            self.available = True
            return True
        except Exception:
            self.available = False
            return False
    
    async def check_model_available(self) -> bool:
        """
        Check if the configured model is available/pulled in Ollama.

        Returns:
            True if model is available, False otherwise
        """
        if self.client is None or not self.available:
            return False

        try:
            response = await asyncio.wait_for(self.client.list(), timeout=5)
            # Handle both old dict format and new object format from ollama package
            models = []
            if isinstance(response, dict):
                models = response.get('models', [])
            elif hasattr(response, 'models'):
                models = response.models or []
            else:
                models = list(response) if response else []

            model_base = self.model.split(':')[0]
            for m in models:
                name = m.get('name', '') if isinstance(m, dict) else getattr(m, 'model', getattr(m, 'name', ''))
                if model_base in str(name):
                    return True
            return False
        except Exception:
            return False
    
    async def explain_variant(self, result) -> str:
        """
        Generate an AI explanation for a single variant.
        
        Args:
            result: A VariantResult object from allelio.analysis.lookup
            
        Returns:
            Explanation string with safety checks and disclaimers applied
        """
        # Check if AI is available
        if self.client is None or not self.available:
            return self._fallback_explanation(result)
        
        # Build the prompt
        user_prompt = build_variant_prompt(result)
        
        try:
            # Call Ollama chat API
            response = await asyncio.wait_for(
                self.client.chat(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT
                        },
                        {
                            "role": "user",
                            "content": user_prompt
                        }
                    ],
                    stream=False
                ),
                timeout=60
            )
            
            explanation = response['message']['content']
            
            # Run safety checks
            explanation, safety_warnings = check_safety(explanation)
            
            # Get variant-specific warnings
            variant_warnings = get_variant_warnings(result)
            
            # Wrap with disclaimers
            final_explanation = wrap_with_disclaimer(explanation, variant_warnings)
            
            return final_explanation
            
        except asyncio.TimeoutError:
            return self._fallback_explanation(result, reason="Request timed out")
        except Exception as e:
            return self._fallback_explanation(result, reason=str(e))
    
    async def explain_variants_batch(
        self,
        results: List,
        max_concurrent: int = 3,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, str]:
        """
        Generate AI explanations for multiple variants with concurrency control.
        
        Args:
            results: List of VariantResult objects
            max_concurrent: Maximum concurrent requests to Ollama
            progress_callback: Optional callback function(completed, total) for progress tracking
            
        Returns:
            Dictionary mapping rsID to explanation string
        """
        if not results:
            return {}
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def explain_with_semaphore(result):
            async with semaphore:
                explanation = await self.explain_variant(result)
                if progress_callback:
                    progress_callback(len(explanations), len(results))
                return result.rsid, explanation
        
        # Track completions for callback
        explanations = {}
        
        # Create all tasks
        tasks = [explain_with_semaphore(result) for result in results]
        
        # Execute with progress tracking
        for coro in asyncio.as_completed(tasks):
            rsid, explanation = await coro
            explanations[rsid] = explanation
            if progress_callback:
                progress_callback(len(explanations), len(results))
        
        return explanations
    
    async def generate_summary(self, results: List) -> str:
        """
        Generate an executive summary of variant findings.
        
        Args:
            results: List of VariantResult objects
            
        Returns:
            Summary string grouped by category and highlighting significant findings
        """
        if self.client is None or not self.available:
            return "AI summary generation is unavailable. Please review individual variant explanations."
        
        if not results:
            return "No variants to summarize."
        
        # Organize results by significance
        high_impact = []
        moderate = []
        low = []
        
        for result in results:
            clinvar = result.clinvar_entries or []
            gwas = result.gwas_entries or []
            
            # Classify based on available data
            if clinvar or (gwas and len(gwas) > 0):
                has_clinvar_pathogenic = any(
                    'pathogenic' in str(e.get('clinical_significance', '')).lower()
                    for e in clinvar
                )
                
                if has_clinvar_pathogenic or (gwas and any(
                    float(e.get('p_value', '1.0').split('e-')[1]) > 5 
                    for e in gwas 
                    if 'e-' in str(e.get('p_value', ''))
                )):
                    high_impact.append(result)
                elif clinvar or gwas:
                    moderate.append(result)
                else:
                    low.append(result)
            else:
                low.append(result)
        
        # Build summary prompt
        summary_parts = [
            f"Summary of {len(results)} genetic variants analyzed:\n"
        ]
        
        if high_impact:
            summary_parts.append(f"- {len(high_impact)} variant(s) with potentially significant findings")
        if moderate:
            summary_parts.append(f"- {len(moderate)} variant(s) with moderate research associations")
        if low:
            summary_parts.append(f"- {len(low)} variant(s) with limited available data")
        
        summary_parts.append(
            "\nPlease provide a brief 2-3 paragraph executive summary of these findings, "
            "organized by significance and grouped by trait/condition when applicable. "
            "Emphasize the most important findings and remind the user to consult a genetic counselor."
        )
        
        summary_prompt = "\n".join(summary_parts)
        
        try:
            response = await asyncio.wait_for(
                self.client.chat(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT
                        },
                        {
                            "role": "user",
                            "content": summary_prompt
                        }
                    ],
                    stream=False
                ),
                timeout=60
            )
            
            summary = response['message']['content']
            
            # Apply safety checks to summary
            summary, _ = check_safety(summary)
            
            # Wrap with standard disclaimer
            final_summary = wrap_with_disclaimer(summary, [])
            
            return final_summary
            
        except Exception:
            return "Summary generation failed. Please review individual variant explanations."
    
    def _fallback_explanation(self, result, reason: str = "AI explanations unavailable") -> str:
        """
        Provide a fallback explanation when Ollama is not available.
        
        Args:
            result: A VariantResult object
            reason: Reason why AI is unavailable
            
        Returns:
            Plain text summary of available data
        """
        # Extract gene from sub-entries
        gene = "Unknown"
        if result.clinvar_entries:
            gene = getattr(result.clinvar_entries[0], 'gene', None) or "Unknown"
        elif result.gwas_entries:
            gene = getattr(result.gwas_entries[0], 'mapped_gene', None) or "Unknown"

        lines = [
            f"Explanation: {reason}",
            "",
            "Raw variant data:",
            f"- rsID: {result.rsid or 'Unknown'}",
            f"- Gene: {gene}",
            f"- Chromosome: {result.chromosome or 'Unknown'}, Position: {result.position or 'Unknown'}",
            f"- Genotype: {result.genotype or 'Unknown'}",
        ]

        if result.clinvar_entries:
            lines.append("\nClinVar Information:")
            for entry in result.clinvar_entries:
                sig = getattr(entry, 'clinical_significance', 'Unknown')
                cond = getattr(entry, 'conditions', 'Unknown')
                lines.append(f"  - {cond}: {sig}")

        if result.gwas_entries:
            lines.append("\nGWAS Associations:")
            for entry in result.gwas_entries:
                trait = getattr(entry, 'trait', 'Unknown')
                p_val = getattr(entry, 'p_value', 'Unknown')
                lines.append(f"  - {trait}: p-value = {p_val}")
        
        lines.extend([
            "",
            "Please consult a genetic counselor or healthcare provider for interpretation of these findings.",
        ])
        
        return "\n".join(lines)
