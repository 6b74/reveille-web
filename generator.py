import anthropic
import json
import os
import time
from datetime import datetime, timezone

SECTION_TITLES = {
    "cyber": "Cyber",
    "geopolitical": "Geopolitical",
    "military": "Military",
    "intel_osint": "Intel / OSINT",
}

SECTION_PROMPT = """You are an intelligence analyst writing a daily brief for a public-facing website.
Your audience ranges from cyber professionals to informed general readers.

You will be given a list of news articles from the past 24 hours in the {section} category.
Write a section of the daily brief with the following structure, returned as JSON only:

{{
  "id": "{section_id}",
  "title": "{title}",
  "intro": "One sentence framing what today's {section} picture looks like overall.",
  "items": [
    {{
      "headline": "A clear, specific headline in your own words (not copied from the article)",
      "summary": "2-3 sentences. What happened, why it matters, what to watch. Be specific and analytical.",
      "source": "Publication name",
      "url": "Article URL"
    }}
  ]
}}

Rules:
- Select the 3-4 most significant articles. Skip duplicates and low-signal items.
- Write all headlines and summaries in your own words.
- Be direct and analytical. No filler phrases.
- Return JSON only. No markdown, no preamble.

Articles:
{articles}"""

EXEC_SUMMARY_PROMPT = """You are an intelligence analyst. Based on these four section briefs from today's daily intelligence report, write a 3-4 sentence executive summary that synthesizes the most important cross-cutting themes. What is the overall intelligence picture today? Are any threads connected?

Be direct and analytical. Return plain text only, no JSON, no markdown.

Sections:
{sections}"""


def get_client():
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def api_call_with_retry(fn, retries=3, wait=30):
    """Call an Anthropic API function with retry on 529 overloaded errors."""
    for attempt in range(retries):
        try:
            return fn()
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt < retries - 1:
                print(f"  API overloaded, retrying in {wait}s... (attempt {attempt + 1}/{retries})")
                time.sleep(wait)
            else:
                raise


def generate_section(section_id, articles):
    if not articles:
        return None

    # trim to top 15 candidates to keep prompt size manageable
    candidates = articles[:15]
    articles_text = "\n\n".join([
        f"Title: {a['title']}\nSource: {a['source']}\nURL: {a['url']}\nSummary: {a['summary']}"
        for a in candidates
    ])

    prompt = SECTION_PROMPT.format(
        section=SECTION_TITLES.get(section_id, section_id),
        section_id=section_id,
        title=SECTION_TITLES.get(section_id, section_id),
        articles=articles_text,
    )

    response = api_call_with_retry(lambda: get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    ))

    raw = response.content[0].text.strip()

    # strip any accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw.strip())


def generate_executive_summary(sections):
    sections_text = "\n\n".join([
        f"[{s['title']}]\n" + "\n".join([f"- {item['headline']}" for item in s['items']])
        for s in sections if s
    ])

    response = api_call_with_retry(lambda: get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": EXEC_SUMMARY_PROMPT.format(sections=sections_text)}],
    ))

    return response.content[0].text.strip()


def generate_brief(feeds_by_section, issue_number):
    today = datetime.now(timezone.utc)
    sections = []

    for section_id in ["cyber", "geopolitical", "military", "intel_osint"]:
        print(f"  generating {section_id}...")
        articles = feeds_by_section.get(section_id, [])
        section = generate_section(section_id, articles)
        if section:
            sections.append(section)

    print("  generating executive summary...")
    exec_summary = generate_executive_summary(sections)

    total_articles = sum(len(v) for v in feeds_by_section.values())
    total_published = sum(len(s["items"]) for s in sections)

    return {
        "date": today.strftime("%Y-%m-%d"),
        "generated_at": today.isoformat(),
        "issue": issue_number,
        "executive_summary": exec_summary,
        "sections": sections,
        "stats": {
            "feeds_processed": sum(
                len(urls)
                for urls in json.load(open("feeds.json")).values()
            ),
            "articles_reviewed": total_articles,
            "items_published": total_published,
        },
    }

