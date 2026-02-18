# Why Your Genetic Data Is the Most Sensitive Data You Own

You probably think carefully about your passwords, your social security number, maybe your medical records. But there is one type of personal data that is more sensitive than all of these, and most people treat it casually: your genetic data.

If you've taken a consumer DNA test, you own a file that contains hundreds of thousands of data points about your biology. That file can reveal your disease risks, your family secrets, your ancestry, and your predispositions — and unlike a credit card number, it can never be changed. Here's why that matters, and why Allelio was built to keep it entirely on your computer.

## You Can't Change Your Genome

This is the fundamental difference between genetic data and every other kind of personal data. If your credit card is compromised, you get a new one. If your password leaks, you change it. If your email is hacked, you create a new account.

Your DNA is permanent. It is the same the day you're born and the day you die. If your genetic data is exposed, there is no reset button, no replacement, no way to un-share it. This alone makes it categorically different from any other type of sensitive information.

## It Doesn't Just Describe You

Your genome is not just your own. You share roughly 50% of your genetic variants with each parent and each child, about 25% with siblings, and decreasing amounts with more distant relatives. This means your genetic data reveals information about your family members — people who never consented to have their biology exposed.

If your data shows you carry a pathogenic BRCA1 variant, your siblings each have a 50% chance of carrying it too. If your data reveals unexpected ancestry, it may expose family secrets across generations. If your data is linked to your identity and becomes public, it affects everyone who shares your bloodline.

This is not hypothetical. Genetic genealogy databases have been used by law enforcement to identify suspects through their relatives' DNA. The Golden State Killer was caught in 2018 because distant relatives had uploaded their DNA to a public genealogy database. Whatever you think about that particular case, the principle is clear: your genetic data implicates others who may not have chosen to participate.

## It Can Predict Your Future

Most personal data describes your past or present — where you've been, what you've bought, who you've contacted. Genetic data is different because it contains probabilistic information about your future.

Certain variants are associated with elevated risk for Alzheimer's disease, Parkinson's disease, various cancers, cardiac conditions, autoimmune disorders, and hundreds of other conditions. This information can be profoundly distressing to learn about, even when the actual risk increase is modest. Knowing you carry two copies of the APOE4 allele (associated with significantly elevated Alzheimer's risk) is the kind of knowledge that can change how you see your entire future.

This predictive power is also why genetic data is valuable to entities that might not have your best interests at heart: insurers, employers, data brokers, and others who might use your biology against you.

## Legal Protections Are Incomplete

In the United States, the Genetic Information Nondiscrimination Act (GINA) of 2008 prohibits genetic discrimination in health insurance and employment. This is an important protection, but it has significant gaps.

GINA does not cover life insurance. It does not cover disability insurance. It does not cover long-term care insurance. It does not apply to employers with fewer than 15 employees. It does not apply to the military.

This means that if a life insurance company could access your genetic data, they could use it to deny you coverage or charge higher premiums. The same goes for disability and long-term care insurance. Some states have additional protections, but coverage varies widely.

Outside the United States, protections are even more uneven. Some countries have strong genetic privacy laws; others have none at all. The international patchwork of regulations means that genetic data shared online could be subject to different legal regimes depending on who accesses it and where.

## The Re-Identification Problem

You might think that stripping your name from a genetic data file makes it anonymous. It doesn't. A genome is, by definition, unique to you (unless you have an identical twin, and even then, somatic mutations create differences over time). Research has repeatedly shown that individuals can be re-identified from supposedly "anonymized" genetic data.

A landmark 2013 study demonstrated that men could be identified by cross-referencing their Y-chromosome markers with genealogy databases and public records. Since then, the re-identification toolkit has only grown more powerful. With the proliferation of direct-to-consumer genetic testing, the odds of being re-identified from a "de-identified" genetic dataset continue to increase.

This is not a theoretical concern. It's a mathematical certainty: if your genome is unique (it is), and if a sufficiently large reference dataset exists (it increasingly does), then your genetic data can be linked back to you regardless of what identifying information you strip away.

## What Happens When Genetic Data Leaks

There have already been significant breaches of genetic data. In October 2023, 23andMe disclosed that hackers had accessed the data of approximately 6.9 million users through a credential-stuffing attack. The stolen data included ancestry information, genetic relatedness data, and profile details.

Unlike a financial breach, the consequences of a genetic data breach don't have a clear endpoint. Your genome doesn't expire. The information stolen today will still be accurate in 10, 20, or 50 years. As genetic science advances, the same data may reveal new information that wasn't even knowable at the time of the breach.

## Why Allelio Was Built for Privacy

All of this is why Allelio was designed from the ground up to keep your genetic data on your computer and nowhere else.

When you use Allelio, your raw genotype file is read from your local disk and processed in local memory. The ClinVar and GWAS databases are downloaded once and stored locally. The AI model runs on your hardware through Ollama. Reports are generated locally and saved to your computer.

At no point does your genetic data leave your machine. There is no server to hack. There is no cloud database to breach. There is no account with your genome attached to your email address. The code is open-source and inspectable — you or anyone you trust can verify that no data is transmitted anywhere.

This isn't a marketing feature. It's the only responsible way to build a consumer genomics tool in a world where genetic data is permanently sensitive and legal protections are incomplete.

## What You Can Do

Beyond using privacy-respecting tools like Allelio, here are some principles for protecting your genetic data:

**Think before you upload.** Any time a service asks you to upload your raw genotype file, ask yourself: where does it go, who can access it, and what happens if the company is breached or acquired?

**Read privacy policies carefully.** Some services claim to delete your data but retain aggregate or anonymized versions. Given the re-identification risks, "anonymized" genetic data may not stay anonymous.

**Be cautious with public databases.** Uploading your genome to a public genealogy database means anyone with access to that database can see your data — including law enforcement.

**Secure your files.** Treat your raw genotype file and any reports with the same care you'd give your most sensitive financial records. Consider encrypting them at rest.

**Talk to your family.** If you share genetic results with relatives, you're also sharing information derived from their DNA. Make sure they're comfortable with that.

Your genome is the most personal thing about you. Treat it accordingly.

---

*Allelio is for educational purposes only and is not a substitute for medical advice. Learn more at [allelio.org].*
