#!/usr/bin/env python3
"""
Scan Inbox.md entries and check whether arXiv metadata exposes repository links.

The script follows the screening rule in AGENT.md: direct repository evidence
should come from arXiv summary/comment metadata, not from second-hand guesses.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HEADING_RE = re.compile(r"^##\s+(?P<date>\d{4}-\d{2}-\d{2})\s+更新")
ENTRY_RE = re.compile(
    r"^-\s+\[(?P<checked>[ xX])\]\s+"
    r"(?:\*\*\[(?P<category>[^\]]+)\]\*\*\s+)?"
    r"(?P<body>.*)$"
)
ARXIV_LINK_RE = re.compile(r"\[(?P<title>[^\]]+)\]\((?P<link>https?://arxiv\.org/abs/(?P<id>[^)]+))\)")
ARXIV_ID_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(?P<id>[^\s?#)]+)", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s<>\]\)\"']+")

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

COMING_SOON_PHRASES = (
    "code coming soon",
    "code will be released",
    "will release the code",
    "code and benchmark will be available soon",
    "will be available soon",
    "coming soon",
)


@dataclass
class InboxPaper:
    update_date: str
    checked: bool
    category: str
    title: str
    arxiv_link: str
    arxiv_id: str
    raw_arxiv_id: str


@dataclass
class ArxivMetadata:
    arxiv_id: str
    title: str = ""
    summary: str = ""
    comment: str = ""
    published: str = ""
    updated: str = ""


@dataclass
class LinkEvidence:
    url: str
    source: str
    kind: str


@dataclass
class CodeCheck:
    paper: InboxPaper
    metadata: Optional[ArxivMetadata]
    status: str
    evidence: List[LinkEvidence] = field(default_factory=list)
    coming_soon: bool = False
    error: str = ""


def parse_date(value: Optional[str]) -> Optional[dt.date]:
    if not value:
        return None
    return dt.date.fromisoformat(value)


def in_date_range(value: str, start: Optional[dt.date], end: Optional[dt.date]) -> bool:
    current = dt.date.fromisoformat(value)
    if start and current < start:
        return False
    if end and current > end:
        return False
    return True


def normalize_arxiv_id(raw: str) -> str:
    value = (raw or "").strip().split("?")[0].split("#")[0]
    return re.sub(r"v\d+$", "", value, flags=re.IGNORECASE)


def arxiv_id_from_url(url: str) -> str:
    match = ARXIV_ID_RE.search(url or "")
    return normalize_arxiv_id(match.group("id")) if match else ""


def clean_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def parse_inbox(
    inbox_path: str,
    date_from: Optional[dt.date],
    date_to: Optional[dt.date],
    unchecked_only: bool,
) -> List[InboxPaper]:
    papers: List[InboxPaper] = []
    current_date: Optional[str] = None
    seen_ids = set()

    with open(inbox_path, "r", encoding="utf-8") as f:
        for line in f:
            heading = HEADING_RE.match(line)
            if heading:
                current_date = heading.group("date")
                continue

            if not current_date or not in_date_range(current_date, date_from, date_to):
                continue

            entry = ENTRY_RE.match(line)
            if not entry:
                continue

            checked = entry.group("checked").lower() == "x"
            if unchecked_only and checked:
                continue

            body = entry.group("body") or ""
            arxiv = ARXIV_LINK_RE.search(body)
            if not arxiv:
                continue

            raw_id = arxiv.group("id")
            arxiv_id = normalize_arxiv_id(raw_id)
            if not arxiv_id or arxiv_id in seen_ids:
                continue

            seen_ids.add(arxiv_id)
            papers.append(
                InboxPaper(
                    update_date=current_date,
                    checked=checked,
                    category=entry.group("category") or "",
                    title=clean_text(arxiv.group("title")),
                    arxiv_link=arxiv.group("link"),
                    arxiv_id=arxiv_id,
                    raw_arxiv_id=raw_id,
                )
            )

    return papers


def batched(values: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def fetch_arxiv_batch(
    ids: Sequence[str],
    base_url: str,
    timeout: int,
    user_agent: str,
) -> Dict[str, ArxivMetadata]:
    query = urllib.parse.urlencode(
        {"id_list": ",".join(ids), "max_results": str(len(ids))},
        safe=",",
    )
    url = f"{base_url}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})

    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()

    root = ET.fromstring(payload)
    results: Dict[str, ArxivMetadata] = {}

    for entry in root.findall("atom:entry", ATOM_NS):
        id_text = clean_text(entry.findtext("atom:id", default="", namespaces=ATOM_NS))
        arxiv_id = arxiv_id_from_url(id_text)
        if not arxiv_id:
            continue

        comment_node = entry.find("arxiv:comment", ATOM_NS)
        comment = clean_text(comment_node.text if comment_node is not None else "")

        results[arxiv_id] = ArxivMetadata(
            arxiv_id=arxiv_id,
            title=clean_text(entry.findtext("atom:title", default="", namespaces=ATOM_NS)),
            summary=clean_text(entry.findtext("atom:summary", default="", namespaces=ATOM_NS)),
            comment=comment,
            published=clean_text(entry.findtext("atom:published", default="", namespaces=ATOM_NS)),
            updated=clean_text(entry.findtext("atom:updated", default="", namespaces=ATOM_NS)),
        )

    return results


def fetch_arxiv_metadata(
    ids: Sequence[str],
    base_url: str,
    batch_size: int,
    delay_seconds: float,
    timeout: int,
    user_agent: str,
) -> Tuple[Dict[str, ArxivMetadata], Dict[str, str]]:
    metadata: Dict[str, ArxivMetadata] = {}
    errors: Dict[str, str] = {}

    batches = list(batched(list(ids), max(1, batch_size)))
    for index, batch in enumerate(batches, start=1):
        try:
            metadata.update(fetch_arxiv_batch(batch, base_url, timeout, user_agent))
        except Exception as exc:  # keep per-paper errors in the final report
            message = str(exc)
            for arxiv_id in batch:
                errors[arxiv_id] = message

        if index < len(batches) and delay_seconds > 0:
            time.sleep(delay_seconds)

    return metadata, errors


def extract_urls(text: str) -> List[str]:
    urls = []
    for match in URL_RE.finditer(text or ""):
        url = html.unescape(match.group(0)).rstrip(".,;:")
        urls.append(url)
    return urls


def classify_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.strip("/")
    parts = [p for p in path.split("/") if p]

    if host.endswith("github.io") or "project-page" in path.lower():
        return "project_page"

    if host in {"github.com", "gitlab.com", "bitbucket.org"}:
        if len(parts) < 2:
            return "other"
        repo_name = parts[1].lower()
        if repo_name.endswith(".github.io") or repo_name in {"project-page", "project_page"}:
            return "project_page"
        return "code"

    if host == "huggingface.co":
        if parts and parts[0] == "datasets":
            return "dataset"
        if parts and parts[0] == "spaces":
            return "project_page"
        return "code"

    if "project" in host or "project" in path.lower():
        return "project_page"

    return "other"


def has_coming_soon(text: str) -> bool:
    lowered = (text or "").lower()
    return any(phrase in lowered for phrase in COMING_SOON_PHRASES)


def check_paper(paper: InboxPaper, metadata: Optional[ArxivMetadata], error: str = "") -> CodeCheck:
    if error:
        return CodeCheck(paper=paper, metadata=metadata, status="fetch_error", error=error)
    if not metadata:
        return CodeCheck(paper=paper, metadata=metadata, status="missing_metadata")

    evidence: List[LinkEvidence] = []
    for source, text in (("summary", metadata.summary), ("comment", metadata.comment)):
        for url in extract_urls(text):
            evidence.append(LinkEvidence(url=url, source=source, kind=classify_url(url)))

    combined_text = f"{metadata.summary} {metadata.comment}"
    coming_soon = has_coming_soon(combined_text)

    kinds = {item.kind for item in evidence}
    if "code" in kinds:
        status = "direct_code"
    elif coming_soon:
        status = "coming_soon"
    elif "dataset" in kinds:
        status = "dataset_only"
    elif "project_page" in kinds:
        status = "project_page"
    elif evidence:
        status = "other_link"
    else:
        status = "no_link"

    return CodeCheck(
        paper=paper,
        metadata=metadata,
        status=status,
        evidence=evidence,
        coming_soon=coming_soon,
    )


def unique_links(items: Iterable[LinkEvidence], kinds: Optional[set] = None) -> List[LinkEvidence]:
    result = []
    seen = set()
    for item in items:
        if kinds is not None and item.kind not in kinds:
            continue
        key = (item.url, item.source, item.kind)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def render_links(items: Iterable[LinkEvidence], kinds: Optional[set] = None) -> str:
    selected = unique_links(items, kinds)
    if not selected:
        return "-"
    return ", ".join(f"[{item.kind}:{item.source}]({item.url})" for item in selected)


def render_markdown(checks: Sequence[CodeCheck], source_name: str, date_from: str, date_to: str) -> str:
    grouped: Dict[str, List[CodeCheck]] = {}
    for check in checks:
        grouped.setdefault(check.status, []).append(check)

    order = [
        ("direct_code", "Direct Code Evidence"),
        ("project_page", "Project Page Only"),
        ("dataset_only", "Dataset / HF Dataset Only"),
        ("coming_soon", "Coming Soon"),
        ("other_link", "Other Links"),
        ("no_link", "No Link Evidence"),
        ("missing_metadata", "Missing Metadata"),
        ("fetch_error", "Fetch Errors"),
    ]

    lines = [
        "# arXiv Code Repository Check",
        "",
        f"Source: `{source_name}`",
        f"Date range: `{date_from or 'begin'}` to `{date_to or 'end'}`",
        f"Total papers: {len(checks)}",
        "",
        "## Summary",
        "",
    ]

    for status, label in order:
        lines.append(f"- {label}: {len(grouped.get(status, []))}")
    lines.append("")

    for status, label in order:
        items = grouped.get(status, [])
        if not items:
            continue
        lines.append(f"## {label}")
        lines.append("")
        for check in items:
            paper = check.paper
            lines.append(
                f"- **[{paper.category or '-'}] [{paper.title}]({paper.arxiv_link})** "
                f"({paper.update_date}, `{paper.arxiv_id}`)"
            )
            if check.error:
                lines.append(f"  - error: `{check.error}`")
            else:
                lines.append(f"  - code: {render_links(check.evidence, {'code'})}")
                lines.append(f"  - project/data/other: {render_links(check.evidence, {'project_page', 'dataset', 'other'})}")
                if check.coming_soon:
                    lines.append("  - note: contains a coming-soon style claim")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check arXiv summary/comment metadata for direct code repository evidence."
    )
    parser.add_argument(
        "--input",
        default=os.path.join(BASE_DIR, "Inbox.md"),
        help="Inbox markdown file to scan. Default: %(default)s",
    )
    parser.add_argument("--date-from", help="Start update date, inclusive, e.g. 2026-05-22.")
    parser.add_argument("--date-to", help="End update date, inclusive, e.g. 2026-05-24.")
    parser.add_argument(
        "--output",
        default="",
        help="Write Markdown report to this path. Omit to print to stdout.",
    )
    parser.add_argument(
        "--unchecked-only",
        action="store_true",
        help="Only scan unchecked Inbox entries.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only parse Inbox entries and print arXiv IDs; do not query arXiv.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Number of arXiv IDs per API request. Default: %(default)s",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=3.0,
        help="Delay between arXiv API batches. Default follows arXiv politeness guidance.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout in seconds. Default: %(default)s",
    )
    parser.add_argument(
        "--base-url",
        default="https://export.arxiv.org/api/query",
        help="arXiv API endpoint. Default: %(default)s",
    )
    parser.add_argument(
        "--user-agent",
        default="MyArxiv-Agent code repo checker (+https://github.com/)",
        help="HTTP User-Agent for arXiv API requests.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    date_from = parse_date(args.date_from)
    date_to = parse_date(args.date_to)
    inbox_path = os.path.abspath(args.input)

    papers = parse_inbox(inbox_path, date_from, date_to, args.unchecked_only)
    if args.dry_run:
        for paper in papers:
            print(f"{paper.update_date}\t{paper.arxiv_id}\t{paper.title}")
        print(f"\nParsed {len(papers)} papers.", file=sys.stderr)
        return 0

    ids = [paper.arxiv_id for paper in papers]
    metadata, errors = fetch_arxiv_metadata(
        ids=ids,
        base_url=args.base_url,
        batch_size=args.batch_size,
        delay_seconds=args.delay_seconds,
        timeout=args.timeout,
        user_agent=args.user_agent,
    )

    checks = [
        check_paper(paper, metadata.get(paper.arxiv_id), errors.get(paper.arxiv_id, ""))
        for paper in papers
    ]

    report = render_markdown(
        checks=checks,
        source_name=os.path.relpath(inbox_path, BASE_DIR),
        date_from=args.date_from or "",
        date_to=args.date_to or "",
    )

    if args.output:
        output_path = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
    else:
        print(report, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
