# What Is Ollama? How Allelio Runs AI on Your Computer Without Sending Data Anywhere

When people hear that Allelio uses AI to explain genetic variants, their first question is often: "Where does my data go?" The answer is nowhere. Allelio uses a tool called Ollama to run a large language model entirely on your computer. No cloud. No API calls. No data leaving your machine.

But what is Ollama, exactly? And how is it possible to run AI locally? Let's break it down.

## The Cloud AI Problem

Most AI tools you've used — ChatGPT, Google Gemini, Claude — run on massive servers in data centers. When you type a question, your text is sent over the internet to that company's servers, processed by their model, and the response is sent back.

For general questions, this is fine. But for genetic data, it's a serious problem. Sending your DNA variants to a cloud server means trusting that company with some of the most sensitive personal information that exists. You'd need to trust their security, their data retention policies, their employees, and their future decisions about your data.

Allelio avoids this entirely by running the AI locally.

## What Ollama Is

Ollama is an open-source tool that makes it easy to download and run large language models (LLMs) on your own computer. Think of it as a runtime environment for AI models — similar to how a web browser is a runtime for websites.

Ollama handles the complex technical work of loading model weights into memory, managing GPU or CPU resources, and providing a simple interface that applications like Allelio can talk to. Without Ollama, running a local LLM would require deep knowledge of machine learning frameworks, model formats, and hardware optimization. Ollama packages all of that into a single, user-friendly tool.

It runs on macOS, Linux, and Windows, and supports a wide range of open-source models. You install it once, pull the model you want (similar to downloading an app), and it's ready to use — offline, private, and under your control.

## How Allelio Uses Ollama

When you run Allelio with AI explanations enabled, here's what happens behind the scenes.

First, Allelio checks that Ollama is running on your computer and that the required model is available. By default, Allelio uses Meta's Llama 3.1 8B model — an 8-billion-parameter language model that's capable enough to produce helpful explanations while being small enough to run on most modern computers.

For each variant that Allelio wants to explain, it constructs a carefully designed prompt. This prompt includes the variant's rsID, the gene it's associated with, the ClinVar classification, the GWAS associations, and your genotype. It also includes system instructions that tell the model to explain the variant in plain English, avoid definitive medical language, and emphasize that the information is educational.

Allelio sends this prompt to Ollama through a local API (localhost — meaning it never touches the internet). Ollama runs the model, generates a response, and sends it back to Allelio. Allelio then runs the response through safety filters that check for overly diagnostic language, adds appropriate disclaimers, and presents the result to you.

The entire process happens on your hardware. The only network activity is between Allelio and Ollama on your own machine.

## What Hardware Do You Need?

Running an LLM locally does require some computing resources, but less than you might think.

For the default Llama 3.1 8B model, you'll need at least 8 GB of RAM (16 GB recommended) and a few gigabytes of free disk space for the model weights. The model can run on CPU alone, but it will be faster if you have a dedicated GPU — especially an NVIDIA GPU with CUDA support, or an Apple Silicon Mac (M1/M2/M3/M4), which handles local AI models particularly well.

On a modern laptop with 16 GB of RAM, generating an explanation for a single variant typically takes a few seconds. Allelio processes variants in batches with limited concurrency to avoid overwhelming your system.

If your hardware is more limited, you can use a smaller model. Ollama offers models at various sizes, and Allelio lets you configure which model to use. A 3B-parameter model will be faster and lighter, though the explanations may be less detailed.

## Why Local AI Matters for Genomics

The privacy advantage of local AI is obvious, but there are other benefits too.

**No internet required.** After the initial setup (downloading Ollama and the model), Allelio works completely offline. You can analyze your genome on an airplane, in a remote cabin, or with your Wi-Fi deliberately turned off.

**No rate limits or API costs.** Cloud AI services often charge per request or impose usage limits. With local AI, you can analyze as many variants as you want, as many times as you want, at no cost.

**No terms of service changes.** Cloud services can change their privacy policies at any time. A service that promises not to train on your data today might change that policy tomorrow after an acquisition. With local AI, the model runs on your machine and your data stays on your machine, regardless of any company's future decisions.

**Reproducibility.** The same model running on your machine will produce consistent results. You're not subject to model updates, A/B tests, or backend changes that cloud providers make without notice.

## The Trade-Offs

Local AI isn't without drawbacks. The models that can run on consumer hardware are smaller and less capable than the massive models running on cloud infrastructure. Llama 3.1 8B is impressive for its size, but it doesn't match the performance of much larger models for complex reasoning tasks.

For Allelio's purposes — translating scientific variant data into plain-English educational explanations — an 8B model is more than adequate. The explanations are grounded in structured data (ClinVar classifications, GWAS statistics, gene information), which reduces the model's tendency to hallucinate. But it's still an AI model, and its explanations should always be taken as educational summaries, not expert opinions.

## Setting Up Ollama

Installing Ollama is straightforward:

On **macOS** or **Linux**, you can install it from ollama.com with a single command. On **Windows**, there's a downloadable installer.

Once installed, pulling the default model is one command:

```
ollama pull llama3.1:8b
```

This downloads the model (about 4.7 GB) to your computer. After that, Ollama runs as a background service, and Allelio connects to it automatically when you run an analysis.

If you want to use a different model, you can pull it the same way and configure Allelio to use it with the `--model` flag.

## The Bigger Picture

Ollama is part of a broader trend toward local, private AI. As models get smaller and hardware gets faster, more and more AI capabilities are moving from the cloud to personal devices. For sensitive applications like genomics, this shift is not just convenient — it's essential.

Allelio was built on the conviction that understanding your own genome shouldn't require trusting a corporation with your most personal data. Ollama makes that conviction technically possible.

---

*Allelio is for educational purposes only and is not a substitute for medical advice. Learn more at [allelio.org].*
