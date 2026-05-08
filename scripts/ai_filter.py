"""
AI-based paper scoring plugin.

Scores fetched papers via an OpenAI-compatible LLM API (Ollama, vLLM, OpenAI, etc.)
and filters out papers below a configurable threshold. Filtered papers are written
to a separate audit file so nothing is silently lost.
"""

import os
import re
import json
import datetime
import time

import requests

from config_loader import load_config, get_config_value

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_JSON_RE = re.compile(r"\{[^{}]*\"score\"\s*:\s*-?\d+[^{}]*\}", re.DOTALL)


def _build_prompt(config):
    interests = get_config_value(config, "ai_filter.interests", "")
    not_interests = get_config_value(config, "ai_filter.not_interests", "")

    parts = [
        "You are a research paper filter. Rate the paper's relevance to the researcher's interests.",
    ]
    if interests:
        parts.append(f"Interested in:\n{interests}")
    if not_interests:
        parts.append(f"NOT interested in:\n{not_interests}")
    parts.append(
        "Score: 8-10 directly relevant, 5-7 somewhat, 2-4 tangential, 0-1 irrelevant.\n"
        'Reply with ONLY a JSON object: {"score": <int 0-10>, "reason": "<one brief sentence>"}'
    )
    return "\n\n".join(parts)


def _resolve_api_key(raw: str) -> str:
    if not raw:
        return ""
    if raw.startswith("$"):
        return os.environ.get(raw[1:], "")
    return raw


def _parse_score(content: str):
    m = _JSON_RE.search(content)
    if not m:
        return None, "parse error"
    try:
        obj = json.loads(m.group())
        score = max(0, min(10, int(obj.get("score", 0))))
        reason = str(obj.get("reason", ""))[:120]
        return score, reason
    except (json.JSONDecodeError, ValueError, TypeError):
        return None, "parse error"


def score_papers(papers, config):
    """Score papers via LLM. Returns (kept, filtered) lists. Papers that fail scoring are kept."""
    enabled = get_config_value(config, "ai_filter.enabled", False)
    if not enabled or not papers:
        return papers, []

    api_base = str(get_config_value(config, "ai_filter.api_base", "http://localhost:11434/v1")).rstrip("/")
    api_key = _resolve_api_key(str(get_config_value(config, "ai_filter.api_key", "")))
    model = str(get_config_value(config, "ai_filter.model", "qwen2.5:7b"))
    min_score = int(get_config_value(config, "ai_filter.min_score", 6))
    max_tokens = int(get_config_value(config, "ai_filter.max_tokens", 1024))
    timeout = int(get_config_value(config, "ai_filter.timeout_seconds", 30))
    delay = float(get_config_value(config, "ai_filter.request_delay_seconds", 0.3))

    prompt = _build_prompt(config)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    kept = []
    filtered = []
    total = len(papers)

    print(f"\nAI 评分中 ({model}, 阈值 >= {min_score})...")

    for i, p in enumerate(papers):
        paper_text = f"Title: {p['title']}\nAbstract: {p['summary']}"

        try:
            resp = requests.post(
                f"{api_base}/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": paper_text},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.0,
                },
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            message = resp.json()["choices"][0]["message"]
            # 推理模型 (DeepSeek V4 等) 可能 content 为空而实际输出在 reasoning_content
            content = message.get("content", "") or message.get("reasoning_content", "")
            score, reason = _parse_score(content)

        except Exception as e:
            print(f"  [{i+1}/{total}] ERROR {e} — 保留")
            kept.append(p)
            if delay > 0:
                time.sleep(delay)
            continue

        p["ai_score"] = score if score is not None else 0
        p["ai_reason"] = reason

        if score is not None and score >= min_score:
            kept.append(p)
        else:
            filtered.append(p)

        status = f"score={score}" if score is not None else "parse_err"
        print(f"  [{i+1}/{total}] {status} | {p['title'][:80]}")

        if delay > 0:
            time.sleep(delay)

    print(f"AI 评分完成：保留 {len(kept)} 篇，过滤 {len(filtered)} 篇")
    return kept, filtered


def write_filtered_inbox(filtered, config):
    """Append filtered-out papers to the filtered inbox file for audit."""
    if not filtered:
        return

    filtered_rel = get_config_value(config, "ai_filter.filtered_inbox", "Inbox-filtered.md")
    file_path = os.path.join(BASE_DIR, filtered_rel)
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    min_score = int(get_config_value(config, "ai_filter.min_score", 6))

    lines = []
    if not os.path.exists(file_path):
        lines.append("# 📥 Filtered Papers (below AI score threshold)\n\n")
        lines.append(
            f"Papers scoring below {min_score}/10. Kept here for audit — "
            "adjust `ai_filter.min_score` or `ai_filter.interests` in config.yaml "
            "if too many relevant papers appear here.\n\n"
        )
        lines.append("---\n\n")

    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            existing = f.read()
    else:
        existing = "".join(lines)
        lines = []

    lines.append(f"## {today_str} 过滤 {len(filtered)} 篇\n")

    for p in filtered:
        score = p.get("ai_score", "?")
        reason = p.get("ai_reason", "")
        lines.append(
            f"- [ ] (score={score}) **[{p['category']}]** "
            f"[{p['title']}]({p['link']}) "
            f"*by {p['author']} ({p['published']})* "
            f"— {reason}\n"
        )
    lines.append("\n")

    # Insert after delimiter or at end
    delimiter = "---"
    if delimiter in existing:
        idx = existing.index(delimiter) + len(delimiter)
        # Find end of line after delimiter
        nl = existing.find("\n", idx)
        insert_at = nl + 1 if nl != -1 else idx
        new_content = existing[:insert_at] + "\n" + "".join(lines) + existing[insert_at:]
    else:
        new_content = existing + "\n" + "".join(lines)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"已过滤论文写入 {file_path}")
