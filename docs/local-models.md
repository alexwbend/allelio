# Running a local model well

Allelio explains your results with a model that runs on your own machine. That
is the whole point: your genome is read, matched, and explained without any of
it leaving your computer. This guide is about doing that part with confidence.
It is not about configuration. The README's [Using a different local
model](../README.md#using-a-different-local-model) section covers the settings.

## Knowing your data stayed local

Allelio only ever talks to a model on this machine, and it enforces that rather
than trusting it:

- Before any prompt is sent, Allelio resolves the model server's address and
  checks that it is a loopback address, meaning your own machine. If it resolves
  to anything else, Allelio refuses at startup and no prompt is ever sent.
- It connects to the address it checked, so a name cannot resolve to loopback
  for the check and to somewhere else for the request.
- Proxy environment variables are ignored, redirects are not followed, and no
  authorization header is sent, so nothing can quietly reroute a prompt.

The status line at the top of the page tells you where things stand in one word:

- **serving**: a local model is answering and its name is shown. This is the
  only state in which a prompt is sent.
- **unreachable**: nothing is answering at that address yet, usually because the
  model server is not running.
- **refused**: the server answered, but the model it would use is an Ollama
  cloud model, which runs off your machine. Allelio will not send your data to
  it.
- **refuted**: the server answered and listed its models, but the one you asked
  for is not among them.
- **unlisted**: the server answered but would not say which models it has.

If it does not say **serving**, no prompt was sent. You lose the plain-English
explanations and you keep everything else: the ClinVar and GWAS findings are
still there for every variant, and the results say plainly that no model wrote
them.

## Picking a model your machine can run

A model that is too big for your RAM will swap to disk and crawl, or fail to
load. Rough guidance, for the 4-bit builds these servers usually download:

| Your RAM | A comfortable model size |
|----------|--------------------------|
| 8 GB     | 3B to 8B, for example `llama3.1:8b`, the default |
| 16 GB    | up to about 13B |
| 32 GB    | up to about 30B |
| 64 GB or more | 70B if you want it |

Bigger is not automatically better here. An 8B model explains a ClinVar or GWAS
finding perfectly well, and it answers in seconds rather than minutes. Start
with the default, and only reach for something larger if the explanations feel
thin.

## What good looks like

- The status says **serving** and names the model.
- Explanations come back in seconds each, not minutes. A run is 50 explanations,
  so per-call speed adds up.
- Each explanation reads like a person describing the finding, and the results
  name the model that wrote them, so you always know what you are reading.

## Why local is worth the extra setup

Running a model yourself is a bit more work than sending your data to a hosted
API. That work is the privacy. Your genome is not something you can un-share
once it has left your machine, so Allelio is built so it never has to. A few
minutes setting up a local model buys you that, for good.
