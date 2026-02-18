# How Allelio Parses Your DNA File: From Raw Data to Genetic Insights in Seconds

You upload a file. A few seconds later, you're looking at a categorized list of your genetic variants with clinical annotations and AI explanations. But what actually happens in between? How does Allelio take a messy text file and turn it into something meaningful?

This article walks through the parsing process — the critical first step where your raw genome data gets read, cleaned, and prepared for analysis.

## Why Parsing Matters

Your raw genome data file is just text. Hundreds of thousands of lines, each representing a single position in your DNA. But different DNA testing companies format that text differently. 23andMe uses one layout, AncestryDNA uses another, and clinical sequencing produces VCF files with their own entirely different structure.

Before Allelio can look up your variants in ClinVar or the GWAS Catalog, it needs to understand what it's reading. The parser's job is to take any supported file format, extract the essential information from each line — the variant identifier, the chromosome, the position, and your genotype — and normalize everything into a single, consistent internal format.

If the parser gets this wrong, everything downstream fails. A misread genotype, a skipped variant, or a format confusion would produce incorrect results. So parsing, while invisible to you as a user, is arguably the most important step in the pipeline.

## Step 1: Format Detection

The first thing Allelio does when you upload a file is figure out what kind of file it is. It doesn't rely on the file extension — that can be wrong or missing. Instead, it reads the first 50 lines of the file and looks for telltale signatures.

**VCF files** start with metadata lines beginning with "##", including a format declaration like `##fileformat=VCFv4.1`. Allelio checks for this (case-insensitively, since different tools capitalize it differently) and, crucially, also looks for the `#CHROM` header line that precedes the data. Some VCF files have dozens of metadata lines, which is why Allelio reads up to 50 lines instead of just a few.

**AncestryDNA files** have a distinctive header row containing the column name "allele1" or "allele2" — because AncestryDNA splits your genotype into two separate columns.

**23andMe files** use comment lines starting with "#" and have a simple four-column tab-separated layout.

If none of these signatures match, Allelio raises an error rather than guessing. A wrong guess would be worse than no guess at all.

## Step 2: Line-by-Line Extraction

Once the format is identified, Allelio hands the file to the appropriate specialized parser. Each parser knows the exact layout of its format and reads the file line by line.

For a **23andMe file**, the parser skips comment lines (starting with #), splits each data line by tabs, and extracts four fields: rsID, chromosome, position, and genotype. It's straightforward because 23andMe's format is clean and consistent.

For an **AncestryDNA file**, the parser needs an extra step. AncestryDNA reports each allele in a separate column, so the parser combines them into a single genotype string. If allele1 is "A" and allele2 is "G", the parser produces the genotype "AG".

For a **VCF file**, parsing is more complex. VCF encodes genotypes using numbers that reference the REF and ALT alleles defined in each line. A genotype of "0/1" means one copy of the reference allele and one copy of the first alternate allele. The parser has to read the REF and ALT fields, interpret the GT (genotype) field, and convert the numerical encoding back into actual DNA letters. It also sorts the alleles alphabetically for consistency.

## Step 3: Filtering No-Calls

Not every position on a genotyping chip produces a readable result. Sometimes the chemistry doesn't work, the signal is ambiguous, or the DNA quality at that region is poor. These failed readings are called "no-calls," and every format represents them differently.

23andMe uses "--" for no-calls. AncestryDNA uses "0" or "00". Some files use other markers.

Allelio's parsers filter these out automatically. A no-call variant can't tell you anything useful — you don't know what you actually carry at that position — so including it in the analysis would only create noise. The parsers also validate that rsIDs follow expected patterns (starting with "rs" or "i") to catch any malformed lines.

## Step 4: Building the Variant List

After parsing and filtering, what remains is a clean list of Variant objects. Each one carries four pieces of data: the rsID (like rs429358), the chromosome (like "19"), the position (like 44908684), and your genotype (like "CT").

A typical 23andMe file starts with around 600,000-700,000 lines but produces roughly 580,000-650,000 usable variants after no-calls and invalid lines are removed. This list is what gets passed to the next stage of the pipeline — the database lookup.

## What Happens Next

With your variants cleaned and normalized, Allelio performs a batch lookup against its local ClinVar and GWAS Catalog databases. Every one of your variant rsIDs is searched in the database. Matches are pulled back with their clinical annotations, categorized by significance, ranked by importance, and (optionally) sent to the local AI for plain-English explanations.

But none of that would work without the parser doing its job first — quietly, in milliseconds, turning a raw text file into structured data ready for analysis.

## The Design Choices Behind It

A few design decisions in Allelio's parser are worth highlighting.

**Local-only processing.** Your file never leaves your computer. The parser reads it directly from disk into memory, processes it in Python, and discards the raw text as soon as the variants are extracted.

**Format auto-detection over manual selection.** Rather than asking you to tell Allelio what format your file is in (which you might not know), the tool figures it out automatically. This reduces friction and eliminates a common source of user error.

**Strict validation over lenient guessing.** If Allelio can't confidently identify your file format, it tells you rather than guessing. This is a deliberate safety choice. In a tool that deals with health-related information, a wrong parse is worse than no parse.

**No-call filtering.** Some tools include no-calls in their output, which can lead to misleading "variant not found" results. Allelio removes them upfront so that every variant in your results is a real reading from the chip.

These choices reflect Allelio's broader philosophy: accuracy and transparency over convenience, and your privacy above all else.

---

*Allelio is for educational purposes only and is not a substitute for medical advice. Learn more at [allelio.org].*
