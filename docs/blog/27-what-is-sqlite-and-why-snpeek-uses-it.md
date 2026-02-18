# What Is SQLite? How Allelio Stores Genetic Databases on Your Computer

When you run Allelio to analyze your DNA data, something interesting happens behind the scenes. Your computer needs to look up hundreds of thousands of genetic variants against databases of known information—databases containing millions of variants from ClinVar, GWAS Catalog, and other sources. How does Allelio do this quickly, locally, and privately? The answer involves something called SQLite, and understanding it helps you appreciate why Allelio's approach to privacy is powerful.

## What Is a Database?

Before we talk about SQLite, let's step back. A database is just organized information—like a library catalog, but digital. Imagine you have a spreadsheet with millions of rows listing genetic variants, their effects, and associated diseases. Looking up one variant in that spreadsheet means scanning through millions of rows. That's slow.

A database organizes that same information in a smart way—using indexes and structures—so that looking up one variant is nearly instant, even if there are millions of variants total. Databases are how companies like Google search the internet in milliseconds, and how banks instantly verify your account balance.

Most databases you hear about—the ones behind Facebook, Gmail, or your bank's website—live on a server somewhere in the cloud. Your computer sends a request over the internet, the server searches its database, and sends back a result.

## Enter SQLite: A Database on Your Computer

SQLite is different. It's a database that lives on your computer, in a single file. No server needed. No internet connection required. No company storing your information in the cloud.

SQLite is one of the most widely used pieces of software in the world. It powers Android phones, iPhones, web browsers, and countless applications. Chances are, you're using SQLite several times a day without knowing it.

What makes SQLite special is its simplicity and self-containment. It's tiny—the entire SQLite program is about 500 kilobytes. It requires no installation or setup. You just have a file (usually with a .db extension) sitting on your computer, and any program can open it, search it, and read from it.

## How Allelio Uses SQLite

When you install Allelio, the setup process downloads or builds a SQLite database file containing:

- **ClinVar Data**: Millions of known genetic variants and their clinical significance (pathogenic, likely pathogenic, benign, likely benign, uncertain).
- **GWAS Catalog Data**: Variants associated with diseases from genome-wide association studies, along with effect sizes and population information.
- **Local Indexes**: Structures that make searching super fast—so Allelio can look up a variant and find its data in milliseconds rather than seconds.

This database lives in a file at `~/.allelio/data/allelio.db` (or wherever your Allelio configuration points). It's all on your computer.

When you run `allelio analyze` on your raw DNA file, Allelio:

1. Reads through your variants
2. Looks each one up in the local SQLite database
3. Retrieves clinical and research information
4. Analyzes it with a local AI model (Ollama)
5. Generates a report

All of this happens without your data leaving your computer. The databases never leave your computer. Your raw DNA data never touches a server.

## WAL Mode: Making SQLite Fast

Behind the scenes, Allelio uses something called WAL mode (Write-Ahead Logging) to make the database fast and reliable. WAL mode allows reads and writes to happen simultaneously—so Allelio can be looking up variants and analyzing them while also potentially updating the database if new data arrives.

This is a technical detail, but it matters: it means Allelio performs well even with very large databases. Genetic databases are huge, and WAL mode helps SQLite stay fast.

## Setup and Updates: How Databases Get on Your Computer

When you first install Allelio, you might run:

```bash
allelio setup
```

This command:

- Checks if you have Ollama installed (for the local AI model)
- Creates the `~/.allelio/data/` directory
- Downloads or builds the SQLite database with current ClinVar and GWAS data
- Sets up any necessary indexes

Depending on your internet speed and the size of the databases, this might take a few minutes to hours. It's a one-time setup.

Later, if new ClinVar data is released or GWAS studies are updated, you can run:

```bash
allelio update
```

This command refreshes the database with the latest data, so your results reflect current genetic knowledge.

## Why SQLite Is Better Than the Cloud for Genetics

You might wonder: why not just have Allelio query a cloud database? Faster internet, more powerful servers, fewer files to manage. But there are compelling reasons to use a local database:

**Privacy**: Your genetic data never leaves your computer. There's no log of your searches on a company server. No one can subpoena your Allelio queries because they're not stored anywhere but your machine.

**Offline Capability**: Once the database is downloaded, you can use Allelio without internet. Analyzing your genome shouldn't require a network connection.

**Security**: Local data is harder to hack than data on a server. There's no central database of users' Allelio queries to compromise.

**Control**: You decide when to update your database. You're not dependent on a company keeping their servers running or charging money for access.

**Cost**: Allelio can be free because there's no ongoing server cost. It's just code and data that run on your computer.

**Latency**: Querying a local database is faster than sending requests over the internet, even if your connection is fast. Every millisecond matters when you're looking up hundreds of thousands of variants.

## The Tradeoff: Storage Space

The tradeoff is storage. ClinVar and GWAS Catalog data together can be several gigabytes. On your computer, that takes up real disk space. A cloud solution would need less local storage.

But for most modern computers, a few gigabytes is negligible. It's a worthwhile tradeoff for the privacy and control you gain.

## SQLite and Data Integrity

One question people sometimes ask: is data safe in a SQLite file? What if the file gets corrupted?

SQLite has built-in protections. It writes data in a way that ensures consistency—even if your computer crashes mid-write, the database remains valid. You can copy the file, back it up, move it between computers. It's remarkably robust.

The databases Allelio uses are read-mostly (you're rarely writing to them), so corruption is extremely unlikely.

## Looking Under the Hood

If you're curious, you can actually look at Allelio's database yourself using SQLite tools. On macOS or Linux, you can install sqlite3 and browse the database:

```bash
sqlite3 ~/.allelio/data/allelio.db
```

Then you can query it directly, explore what variants are in there, see how the data is organized. It's all transparent and accessible on your own computer.

## The Bigger Picture

SQLite is part of what makes Allelio different from many consumer genetics companies. You're not trusting your genetic data to someone else's server. You're not trading your privacy for convenience. Your data stays with you, and the analysis happens locally.

Understanding SQLite—what it is and how it works—helps you appreciate why this is possible. Databases don't need to live in the cloud. Powerful analysis doesn't need a distant server. With the right tools and architecture, you can analyze your genome with the power of modern genetics databases without ever uploading your raw DNA.

That's the Allelio philosophy: genetic knowledge should be local, private, and yours to control.

---

*Allelio is for educational purposes only and is not a substitute for medical advice. Learn more at [allelio.org].*
