"""
Local LLM integration for the Allelio AI explanation engine.

Explanations come from a model running on this machine: Ollama by default, or
any OpenAI-compatible server — llama.cpp, LM Studio, vLLM, llama-swap — named
by ALLELIO_OPENAI_BASE. Every prompt carries the variant it is explaining, so
both paths are held to the same rule: the address has to resolve to this
machine, and nothing else is accepted.
"""

import asyncio
import ipaddress
import os
import re
import socket
from typing import Any, Dict, List, Optional, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx

try:
    from ollama import AsyncClient, ResponseError as _OllamaResponseError
except ImportError:
    AsyncClient = None
    _OllamaResponseError = None

# Bound now, not looked up on the module's `httpx` when it is needed: the test
# suite patches `engine.httpx` with a double that has AsyncClient and nothing
# else, and a late attribute lookup would raise AttributeError from inside the
# handler that is meant to classify errors -- reporting every stubbed server as
# down.
_HTTPStatusError = httpx.HTTPStatusError

# The exception classes that mean *something is there*. An error status is the
# server talking: it is up, it just will not enumerate -- a bare llama.cpp
# serves /v1/chat/completions and has no /v1/models at all. A listing that ran
# past its five seconds is the same kind of thing: something accepted the
# connection and is thinking about it, which is what a warming Ollama daemon
# does. Connection refused, or a name that resolves to nothing, is nothing
# answering, and a dead port says so in milliseconds.
_ANSWERED = tuple(
    e
    for e in (_HTTPStatusError, _OllamaResponseError, asyncio.TimeoutError)
    if e is not None
)

# Re-exported: an explanation and its credit are one value everywhere, and
# every caller of this module already imports from it.
from .attribution import Attribution, Explanation, attribution
from .prompts import build_variant_prompt, SYSTEM_PROMPT
from .safety import check_safety, get_variant_warnings, wrap_with_disclaimer


DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_HOST = "http://localhost:11434"

# Names a model for either provider, and wins over the built-in default.
MODEL_ENV = "ALLELIO_MODEL"
# Points at an OpenAI-compatible server on this machine, used instead of
# Ollama — "http://127.0.0.1:1234/v1" for LM Studio, ":8080/v1" for llama.cpp.
OPENAI_BASE_ENV = "ALLELIO_OPENAI_BASE"

OLLAMA = "Ollama"
OPENAI_COMPATIBLE = "OpenAI-compatible"

# What the server said about itself when asked what it serves. One value rather
# than the three booleans this used to be: every caller that recombined them by
# hand -- the CLI, `allelio info`, the web upload, the library bridge -- got a
# different answer for the same server, and the differences were the bugs.
# `status` is computed in one place, in one order, and is the only thing any of
# them branches on.
UNREACHABLE = "unreachable"  # nothing answered at that address
REFUSED = "refused"          # it answered, and what it serves is refused (-cloud)
REFUTED = "refuted"          # it listed what it serves, and this model is not in it
UNLISTED = "unlisted"        # it answered, but would not enumerate its models
SERVING = "serving"          # it listed what it serves, and this model is in it

# A model server names its own models, and that name is printed on the page and
# written into the exported report. Wide enough for what the servers really use
# — "llama3.1:8b", "hf.co/user/repo:Q4_K_M", "publisher/Model-7B-GGUF" — and
# narrow enough that nothing with a bracket in it can be adopted.
_PLAUSIBLE_MODEL_NAME = re.compile(r"[A-Za-z0-9][\w.:/+@-]{0,127}\Z")


def pin_to_loopback(url: str, setting: str) -> str:
    """Return the URL with its host pinned to a loopback address, or raise.

    A prompt carries the variant it explains — rsID, genotype, gene, the ClinVar
    call — so whatever is on the other end of this URL reads a piece of someone's
    genome. The only host allowed to is this one, and resolving to a loopback
    address is the whole test. A name that answers with one public address out
    of four is a name that ships a genome three times out of four, so any
    address that is not provably loopback fails the whole URL.

    The returned URL carries the address rather than the name it was written
    with, because checking a name and then connecting by it checks nothing: the
    request resolves it again, and /api/analyze runs for half an hour after the
    one time this function looked.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(
            f"{setting}={url!r} is not a URL. It needs the scheme and the port, "
            "like http://127.0.0.1:1234/v1"
        )

    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"{setting}={url!r}: {exc}.") from None

    if port == 0:
        # Nonsense in, and the rewrite below would drop it and send the prompt
        # to port 80 instead — wrong destination rather than an error.
        raise ValueError(f"{setting}={url!r}: port 0 is not a port.")

    try:
        # An IP literal never leaves the machine here; getaddrinfo passes it
        # straight back. A name is looked up, which is the point: "localhost"
        # is only trustworthy if it still answers 127.0.0.1.
        infos = socket.getaddrinfo(parts.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(
            f"{setting}={url!r}: {parts.hostname!r} does not resolve ({exc})."
        ) from None

    remote = []
    loopback = []
    for info in infos:
        # A link-local IPv6 address arrives with a %scope suffix that
        # ip_address will not parse.
        address = info[4][0].split("%")[0]
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            # Not provably this machine is not this machine.
            remote.append(address)
            continue
        # ::ffff:127.0.0.1 is the same address written the other way, but
        # IPv6Address.is_loopback only learned to say so in 3.13 and this
        # package claims 3.9. Unwrap it and the answer stops depending on
        # which Python the user happens to have.
        parsed = getattr(parsed, "ipv4_mapped", None) or parsed
        (loopback if parsed.is_loopback else remote).append(parsed)

    if remote or not loopback:
        named = ", ".join(sorted(str(a) for a in set(remote))) or "nothing"
        raise ValueError(
            f"{setting}={url!r} points at {named}, "
            "which is not this machine. Every prompt carries the variant it "
            "explains, so that server would be reading your genome. Allelio only "
            "talks to a model on 127.0.0.1 or ::1."
        )

    # IPv4 first. getaddrinfo promises no order and answers "localhost" with ::1
    # ahead of 127.0.0.1 on macOS, while Ollama and LM Studio both bind 127.0.0.1
    # and nothing else — pinning to the first answer would refuse the connection.
    address = next((a for a in loopback if a.version == 4), loopback[0])
    host = f"[{address}]" if address.version == 6 else str(address)
    # Any userinfo in the original goes with the name it was attached to.
    netloc = f"{host}:{port}" if port else host
    # Query and fragment go too. This is a base to hang "/models" off, and
    # keeping them turns "…/v1?a=b" into a request for "a=b/models" — a config
    # that fails later as "the server is not answering".
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _model_names(response: Any) -> List[str]:
    """Model identifiers out of a list() reply, whichever shape it arrives in."""
    if isinstance(response, dict):
        models = response.get("models", [])
    elif hasattr(response, "models"):
        models = response.models or []
    else:
        models = list(response) if response else []

    names = []
    for entry in models:
        if isinstance(entry, dict):
            name = entry.get("model") or entry.get("name") or ""
        else:
            name = getattr(entry, "model", None) or getattr(entry, "name", "") or ""
        if name:
            names.append(str(name))
    return names


def _aliases_of(entry: Any) -> List[str]:
    """Other names one served model answers to.

    llama-swap advertises them under meta.llamaswap.aliases and routes on them,
    so `ALLELIO_MODEL=qwen36` is a working configuration whose name is nowhere
    in the list of ids.
    """
    if not isinstance(entry, dict):
        return []
    meta = entry.get("meta")
    if not isinstance(meta, dict):
        return []
    found = []
    for section in meta.values():
        if isinstance(section, dict):
            aliases = section.get("aliases")
            # Another process's JSON. A string iterates to single characters
            # and an int raises, and the raise lands in check_connection's
            # blanket except, where a server that answered is reported as down.
            if not isinstance(aliases, (list, tuple)):
                continue
            found += [str(a) for a in aliases if a]
    return found


def _refuse_cloud(name: str) -> None:
    """Raise if this names an Ollama Cloud model.

    The one case where a request to 127.0.0.1:11434 is not a request to this
    machine: the daemon forwards a `-cloud` tag to ollama.com, prompt and all.
    Every address check in this file passes it, because the address really is
    local — the name is the only place it shows.

    Case-folded because Ollama resolves model names case-insensitively, so
    `gpt-oss:120b-CLOUD` reaches the same relay as the lower-case spelling.

    This is a name check and can only ever be one: `ollama cp gpt-oss:120b-cloud
    mine` renames a cloud model past it, and so does a proxy on a loopback port.
    Neither is visible from here.
    """
    if name.lower().endswith("-cloud"):
        raise ValueError(
            f"{name!r} is an Ollama Cloud model. It runs on Ollama's servers, "
            "not yours, and the prompt carries the variant it explains. "
            "Name a model you have pulled locally."
        )


def _raise_for_status(response: Any) -> None:
    """raise_for_status, carrying the server's own sentence.

    httpx's message is the status line and a link to MDN. The reason a person
    needs is in the body, and on the OpenAI-compatible path that sentence is
    the whole diagnostic: a server answers a name it does not have with
    {"error": {"message": "model 'x' not found"}}, and httpx reports "Client
    error '404 Not Found'".
    """
    if response.status_code < 400:
        return
    try:
        body = response.json()
        err = body.get("error") if isinstance(body, dict) else None
        detail = (err.get("message") if isinstance(err, dict) else err) or ""
    except Exception:
        detail = ""
    # Server-controlled text: capped here, escaped at every sink.
    detail = str(detail or response.text)[:200]
    raise _HTTPStatusError(
        f"{response.status_code} {response.reason_phrase}: {detail}".strip(),
        request=response.request,
        response=response,
    )


def _tagged(name: str) -> str:
    """Ollama reads a bare model name as ":latest"; spell that out before comparing."""
    return name if ":" in name else f"{name}:latest"

# Sixty seconds is not enough for the default 8B model on a warm machine
# once a few explanations run at once; every other one came back as a
# timeout fallback.
REQUEST_TIMEOUT = 300

# Fifty variants, three at a time, at the per-request timeout is over an hour
# of staring at a progress bar. Cap the batch and keep what finished. Thirty
# minutes clears a full run of this project's own default model on an M1 Max
# with room to spare; fifteen did not.
BATCH_DEADLINE = 1800


# httpx trusts the environment by default: HTTP_PROXY, ALL_PROXY, .netrc, and on
# macOS the proxy configured in System Settings, which an MDM-managed laptop ships
# with. A proxy is a second machine, and this prompt has someone's genotype in it —
# pinning the address to 127.0.0.1 counts for nothing if the connection is handed
# to a proxy afterwards. Passed to every client here, ollama's included; it
# forwards **kwargs to httpx.
TRUST_ENV = False


class _OpenAICompatClient:
    """The two calls AIEngine makes, spoken to an OpenAI-style API instead.

    Not a general client: no streaming, no tools, and no authentication. The
    missing Authorization header is the point — this only ever talks to a
    server on this machine, and a hosted provider that wants a key is exactly
    what pin_to_loopback exists to turn away.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def list(self) -> Dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=10, follow_redirects=False, trust_env=TRUST_ENV
        ) as client:
            response = await client.get(f"{self.base_url}/models")
            _raise_for_status(response)
            # `or []`: a server that answers {"data": null} would otherwise
            # raise TypeError below and be reported as down.
            served = response.json().get("data") or []
            served = [m for m in served if isinstance(m, dict)]
        # Aliases kept apart from ids: llama-swap answers to both, so a name
        # has to be matched against both, but only the ids are worth printing
        # back to someone choosing one.
        return {
            "models": [{"model": m["id"]} for m in served if m.get("id")],
            "aliases": [a for m in served for a in _aliases_of(m)],
        }

    async def chat(self, model, messages, stream=False, **kwargs) -> Dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, follow_redirects=False, trust_env=TRUST_ENV
        ) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json={"model": model, "messages": messages, "stream": False},
            )
            _raise_for_status(response)
            content = response.json()["choices"][0]["message"]["content"]
        return {"message": {"content": content}}


class AIEngine:
    """
    AI explanation engine driving a local LLM, via Ollama or an
    OpenAI-compatible server on this machine.
    """
    
    def __init__(self, model: Optional[str] = None, host: Optional[str] = None):
        """
        Initialize the AI engine.
        
        Args:
            model: Model identifier (defaults to $ALLELIO_MODEL, then DEFAULT_MODEL)
            host: Ollama host URL (defaults to http://localhost:11434)

        Raises:
            ValueError: if a configured server address is not on this machine.
        """
        named = model or os.environ.get(MODEL_ENV) or ""
        if named:
            _refuse_cloud(named)
        self.model = named or DEFAULT_MODEL
        # A server with a single model loaded calls it whatever it likes, and
        # guessing "llama3.1:8b" would be wrong every time. An unnamed model is
        # filled in from the server on connect; a named one is a choice, and stays.
        self._model_named = bool(named)

        openai_base = os.environ.get(OPENAI_BASE_ENV)
        if openai_base:
            self.provider = OPENAI_COMPATIBLE
            self.host = pin_to_loopback(openai_base, OPENAI_BASE_ENV)
            self.client = _OpenAICompatClient(self.host)
        else:
            self.provider = OLLAMA
            self.host = pin_to_loopback(host or DEFAULT_HOST, "host")
            # follow_redirects: ollama's client turns it on by default, and a
            # 307 is all it takes to walk a prompt off the address that was
            # checked. httpx, and so _OpenAICompatClient, defaults to off.
            self.client = (
                None
                if AsyncClient is None
                else AsyncClient(
                    host=self.host, follow_redirects=False, trust_env=TRUST_ENV
                )
            )
            # ollama-python reads OLLAMA_API_KEY itself and turns it into a
            # bearer token, which httpx's trust_env has no say over. The only
            # server reachable from here is on this machine, so the header
            # cannot authenticate anything — it can only hand an Ollama Cloud
            # credential to whatever process got to :11434 first. getattr
            # because a test double has no httpx client underneath it.
            underlying = getattr(self.client, "_client", None)
            if underlying is not None:
                underlying.headers.pop("authorization", None)
        
        # The three things check_connection learns, and the only stored state
        # `status` is computed from. Nothing outside this class reads them.
        #
        # available: something answered at that address -- an answer includes an
        #   error status and a listing that outran its clock.
        self.available = False
        # listed: the listing came back and was parsed. Not "there is a listing
        #   with something in it": a server that answered {"data": []} has said
        #   it serves nothing, which is an answer, and a /v1/models that 404s
        #   has said nothing at all.
        self.listed = False
        # Set when the server answered and what it serves was refused. That is
        # not the same as nothing answering, and the caller prints the reason.
        self.refusal: Optional[str] = None
        # Why the last call failed, in the server's own words. Server-controlled
        # text: capped where it is set, escaped at every sink.
        self.last_error: Optional[str] = None
        # Filled in by check_connection, and the only listing anything asks for.
        self.served_models: List[str] = []
        # Matched against, but never shown: see _aliases_of.
        self.served_aliases: List[str] = []
    
    async def check_connection(self) -> bool:
        """
        Check if the configured model server is reachable.
        
        Returns:
            True if it answers, False otherwise
        """
        if self.client is None:
            return False
        
        self.refusal = None
        self.last_error = None
        try:
            # Try a simple tags request to verify connection
            response = await asyncio.wait_for(self.client.list(), timeout=5)
            self.served_models = _model_names(response)
            self.served_aliases = (
                [str(a) for a in response.get("aliases") or []]
                if isinstance(response, dict)
                else []
            )
            self.listed = True
        except Exception as exc:
            self.served_models = []
            self.served_aliases = []
            self.listed = False
            self.last_error = str(exc)[:200]
            # An error *status* is the server talking, and so is a listing that
            # ran past its clock; both are silence about the models rather than
            # silence from the host, so the chat call decides. Connection
            # refused is nothing answering, and there is nothing to try.
            self.available = isinstance(exc, _ANSWERED)
            return self.available

        if (
            not self._model_named
            and self.provider == OPENAI_COMPATIBLE
            and len(self.served_models) == 1
            and _PLAUSIBLE_MODEL_NAME.match(self.served_models[0])
        ):
            # One model loaded and nobody named it, so its name is not a
            # guess — take it, and the interface can print what is actually
            # answering. Two or more and there is nothing to infer: a
            # llama-swap config lists a dozen, and picking whichever came
            # first would load an 80B coder model to explain a genome.
            # Ollama is left out of this for the same reason.
            # Checked here too: __init__ never saw this name, and a signed-in
            # Ollama with one cloud model pulled serves exactly one.
            try:
                _refuse_cloud(self.served_models[0])
            except ValueError as exc:
                # The server answered; it is the model that is refused. Calling
                # that "no answer" sends them looking for a daemon that is
                # running fine.
                self.available = False
                self.refusal = str(exc)
                return False
            self.model = self.served_models[0]
            self._model_named = True

        self.available = True
        return True
    
    def _serves(self, name: str) -> bool:
        """Is this name in the listing -- ids or llama-swap aliases?

        Compared whole, not as a substring: "llama3.1:8b" used to be answered
        yes by a machine holding only "llama3.1:70b", and the run then failed
        at the first explanation instead of here, where it can still say why.

        Case-folded because Ollama resolves names case-insensitively -- measured,
        ALLELIO_MODEL=LLAMA3.1:8B is served by Ollama and was refused here.
        OpenAI-compatible ids are case-sensitive in principle, and folding them
        only widens what this is willing to *try*: a server without that
        spelling answers the chat call with a 404 and nothing is credited.
        """
        served = self.served_models + self.served_aliases
        return _tagged(name).lower() in {_tagged(n).lower() for n in served}

    @property
    def status(self) -> str:
        """What the server said about itself: one of five words.

        The order is the point. A refusal outranks everything -- the server
        answered, and what it serves is not going to be used, so "not serving
        that model" is the wrong thing to say about it. Nothing answering
        outranks the listing, because there is no listing. And a listing that
        never came back is silence, not a denial: a bare llama.cpp has no
        /v1/models at all and explains perfectly well.
        """
        if self.refusal:
            return REFUSED
        if not self.available:
            return UNREACHABLE
        if not self.listed:
            return UNLISTED
        return SERVING if self._serves(self.model) else REFUTED

    def will_explain(self) -> bool:
        """Whether a prompt will be sent to this server at all.

        The single gate. explain and generate_summary ask it themselves, so no
        caller has to switch the engine off by assigning to `available` to stop
        a prompt going out.
        """
        return self.status in (SERVING, UNLISTED)

    def reason(self) -> Optional[str]:
        """Why there will be no explanations, in one plain sentence, or None.

        Plain text, no markup: the CLI escapes it and adds its own hint line,
        the library bridge raises it, and the page has `status` instead. It can
        carry the server's own words, so every sink escapes it.
        """
        state = self.status
        if state == REFUSED:
            return self.refusal
        if state == UNREACHABLE:
            said = f" ({self.last_error})" if self.last_error else ""
            return (
                f"No answer from {self.provider} at {self.host}{said}."
            )
        if state == REFUTED:
            offered = ", ".join(self.served_models[:8])
            return (
                f"{self.provider} at {self.host} is not serving '{self.model}'."
                + (f" It offers: {offered}" if offered else "")
            )
        return None

    def check_model_available(self) -> bool:
        """
        Check whether the server actually has the configured model.

        Answered from the listing check_connection already fetched, so it costs
        no second request and cannot be asked before connecting.

        Returns:
            True if model is available, False otherwise
        """
        return self.status == SERVING

    def model_refuted(self) -> bool:
        """The server listed what it serves, and this model is not in it.

        Not the same as `not check_model_available()`: a server that would not
        list its models has not refuted anything, and neither has one that is
        not there. This is the difference the CLI, `info`, the upload and the
        library bridge all used to get wrong in four different ways.
        """
        return self.status == REFUTED
    
    @property
    def credit(self) -> str:
        """The model's full name, as it is shown wherever its work is shown.

        Read after the listing, never before: a server holding a single model
        gets to name it, and that adopted name is the one the reader needs.
        """
        return f"{self.model} ({self.provider} at {self.host})"

    async def explain(self, result) -> Explanation:
        """The same call, as a record of what came back and who wrote it.

        The fallback is the variant's own data wrapped in the disclaimer, which
        reads like an explanation — `model` is the only thing that separates a
        page the model wrote from one it did not.
        """
        # Check if AI is available
        if self.client is None or not self.will_explain():
            return Explanation(self._fallback_explanation(result), None)
        
        try:
            # Inside the guard, not above it: a variant this cannot build a
            # prompt from used to raise straight past every caller. The batch
            # then lost one card to its own outer guard and the CLI lost the
            # card entirely — no text, no row, no reason.
            user_prompt = build_variant_prompt(result)

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
                timeout=REQUEST_TIMEOUT
            )
            
            explanation = response['message']['content']
            
            # Run safety checks
            explanation, safety_warnings = check_safety(explanation)
            
            # Get variant-specific warnings
            variant_warnings = get_variant_warnings(result)
            
            # Wrap with disclaimers
            final_explanation = wrap_with_disclaimer(explanation, variant_warnings)
            
            # A later failure must not print the reason a call that has since
            # succeeded gave.
            self.last_error = None
            return Explanation(final_explanation, self.credit)
            
        except asyncio.TimeoutError:
            self.last_error = "Request timed out"
            return Explanation(
                self._fallback_explanation(result, reason="Request timed out"),
                None,
                "Request timed out",
            )
        except Exception as e:
            # Kept for the connection and status paths, which are one call at a
            # time; the card carries its own copy because the batch is not.
            self.last_error = str(e)[:200]
            return Explanation(
                self._fallback_explanation(result, reason=str(e)), None, str(e)[:200]
            )
    
    async def explain_variants_batch(
        self,
        results: List,
        max_concurrent: int = 3,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        deadline: float = BATCH_DEADLINE
    ) -> Dict[str, Explanation]:
        """
        Generate AI explanations for multiple variants with concurrency control.
        
        Args:
            results: List of VariantResult objects
            max_concurrent: Maximum concurrent requests to Ollama
            progress_callback: Optional callback function(completed, total) for progress tracking
            
        Returns:
            Dictionary mapping rsID to an Explanation — the text, and the name
            of the model that wrote it, or None where the call did not answer
            and the text is the variant's own data.
        """
        if not results:
            return {}
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def explain_with_semaphore(result):
            async with semaphore:
                return result.rsid, await self.explain(result)
        
        # Seeded, not empty: a variant the deadline cuts off still deserves the
        # gene, the ClinVar call and the GWAS traits that _fallback_explanation
        # writes. A finished task overwrites its seed.
        explanations = {
            r.rsid: Explanation(
                self._fallback_explanation(
                    r, reason="Explanation ran past the time limit"
                ),
                None,
            )
            for r in results
        }
        
        done = 0
        tasks = [
            asyncio.ensure_future(explain_with_semaphore(result))
            for result in results
        ]

        # Whatever is done when the clock runs out is what the user gets. The
        # per-request timeout on its own lets 50 variants, three at a time,
        # hold the upload open for well over an hour on a slow model.
        try:
            for coro in asyncio.as_completed(tasks, timeout=deadline):
                try:
                    rsid, explanation = await coro
                except asyncio.TimeoutError:
                    raise
                except Exception:
                    # One variant that fails outside explain's own
                    # guard used to cost one explanation. It should not cost
                    # the whole upload, minutes after the analysis is done.
                    done += 1
                    if progress_callback:
                        progress_callback(done, len(results))
                    continue
                # The seed is replaced by what came back, credit and all. A
                # task that finishes after the deadline is never awaited, so
                # its seed stands — uncredited, which is what it is.
                explanations[rsid] = explanation
                done += 1
                if progress_callback:
                    progress_callback(done, len(results))
        except asyncio.TimeoutError:
            pass
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        return explanations
    
    async def generate_summary(self, results: List) -> str:
        """
        Generate an executive summary of variant findings.
        
        Args:
            results: List of VariantResult objects
            
        Returns:
            Summary string grouped by category and highlighting significant findings
        """
        if self.client is None or not self.will_explain():
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
                # clinvar/gwas hold ClinVarEntry and GWASEntry objects, not dicts.
                def _pathogenic(e) -> bool:
                    # Same test the results list badges on, so the summary and
                    # the cards cannot disagree about one variant.
                    sig = str(getattr(e, 'clinical_significance', '')).lower()
                    if 'conflicting' in sig or 'benign' in sig:
                        return False
                    return 'pathogenic' in sig

                has_clinvar_pathogenic = any(_pathogenic(e) for e in clinvar)

                def _strong_gwas(e) -> bool:
                    p = getattr(e, 'p_value', None)
                    try:
                        return p is not None and float(p) < 1e-5
                    except (TypeError, ValueError):
                        return False

                if has_clinvar_pathogenic or any(_strong_gwas(e) for e in gwas):
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

        # The model was previously handed counts alone and asked to summarise
        # findings it had never been shown, so it answered by saying so. List them.
        listed = (high_impact + moderate)[:25]
        if listed:
            summary_parts.append("\nThe findings:")
            for r in listed:
                gene = ""
                for e in (r.clinvar_entries or []):
                    gene = getattr(e, 'gene', '') or gene
                for e in (r.gwas_entries or []):
                    gene = gene or getattr(e, 'mapped_gene', '')
                sig = ""
                for e in (r.clinvar_entries or []):
                    sig = getattr(e, 'clinical_significance', '') or sig
                traits = [getattr(e, 'trait', '') for e in (r.gwas_entries or [])]
                traits = [t for t in traits if t][:2]
                bits = [b for b in (gene, sig, "; ".join(traits)) if b]
                summary_parts.append(
                    f"- {r.rsid} ({r.genotype}): " + (" — ".join(bits) if bits else "no annotation")
                )
        
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
                timeout=REQUEST_TIMEOUT
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
