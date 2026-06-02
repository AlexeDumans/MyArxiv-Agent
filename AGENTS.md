# AGENT.md

Scope: this file applies only to the current project directory `/home/martina/Ropes/MyArxiv-Agent` and its descendants.

## Inbox Screening Rules

When summarizing or curating papers from `Inbox.md`, optimize for papers that are both relevant to the interests in `config.yaml` and likely to be reproducible or unusually important.

### Primary Preference: Real Code Evidence

Prioritize papers whose arXiv `summary` or `comment` directly contains a concrete repository link, such as:

- GitHub, GitLab, or Bitbucket code repositories.
- Hugging Face repositories only when they clearly include model/code/evaluation assets, not dataset-only resources.
- Benchmark repositories when they include runnable evaluation code or scripts.

When a paper is selected because of code evidence, record the evidence source explicitly:

- `summary`
- `comment`
- both, if applicable

Do not treat vague statements as code evidence.

### Strong Skepticism: Coming Soon

Treat these as not having code:

- `code coming soon`
- `code will be released`
- `code and benchmark will be available soon`
- project pages with disabled/empty code buttons
- GitHub repositories that only host the project page and not the method, benchmark, model, or evaluation code

These papers may be placed in a "follow-up / needs recheck" section, but should not be promoted to the main recommended list on reproducibility grounds.

### Exception: Truly Innovative Theory

A paper may be selected without code only if its theoretical contribution looks unusually novel, fundamental, or potentially disruptive.

For this exception, explain why code is not required. The note should identify the conceptual contribution, for example:

- a new problem formulation
- a new theoretical lens or impossibility/result claim
- a surprising mechanism-level explanation
- a framework that changes how related work should be evaluated

Do not use this exception for ordinary incremental methods, routine benchmarks, minor architecture tweaks, or application papers without clear reproducibility.

## Priority Labels

Use these labels consistently when producing curated summaries:

- `P0`: Strongly relevant and either has direct code evidence or is theoretically exceptional.
- `P1`: Relevant and useful, but weaker fit, less central, or code evidence is present but the contribution is more incremental.
- `P2`: Maybe useful later, dataset-only, peripheral, or lacks strong evidence.
- `Track`: Interesting but not ready to prioritize, especially "coming soon" code claims.
- `Drop`: Low relevance to the configured interests, even if code exists.

## Recommended Workflow

1. Parse `Inbox.md` entries and extract arXiv IDs, titles, categories, dates, summaries, and checked state.
2. For promising papers, verify arXiv metadata when needed, especially `summary` and `comment`.
3. Search only for direct repository links in `summary` or `comment` unless the user explicitly asks for broader web verification.
4. Rank by relevance first, then by code evidence, then by expected impact.
5. Keep "coming soon" papers out of the main list unless they qualify under the theory exception.
6. Preserve the original `Inbox.md` unless the user explicitly asks to edit, check, delete, or reorder entries.

## Output Format

When creating a curated Markdown summary, include:

- Source range or update date.
- Screening criteria.
- A quick recommendation list with direct code links.
- P0/P1 sections grouped by topic.
- A follow-up section for "coming soon", dataset-only, project-page-only, or needs-recheck cases.
- A short action note for whether anything should be checked in `Inbox.md`.

For each recommended paper, include:

- title and arXiv link
- code/repository link
- evidence source: `summary` or `comment`
- one concise reason it is worth keeping

## Biases To Maintain

- Prefer real, inspectable artifacts over promises.
- Prefer direct arXiv metadata evidence over second-hand claims.
- Do not overvalue a paper merely because it has code if it is off-topic.
- Do not discard a genuinely disruptive theoretical paper solely because it lacks code.
- Keep edits surgical and avoid changing unrelated files.
