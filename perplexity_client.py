import json
import os
import requests
from datetime import date

PERPLEXITY_API_KEY = os.environ.get('PERPLEXITY_API_KEY', '')
PERPLEXITY_URL = 'https://api.perplexity.ai/chat/completions'
PERPLEXITY_MODEL = 'sonar'


def _build_query(user: dict, today: date) -> str:
    today_str = today.strftime('%d %B %Y')

    goal = user.get('primary_goal') or 'professional development and career growth'
    domains = user.get('domains') or 'business, economics, and current affairs'
    regions = user.get('regions') or 'Global'
    countries = user.get('countries') or ''
    admired = user.get('admired_orgs') or ''
    exclusions = user.get('exclusions') or ''

    parts = [
        f"Today is {today_str}. Find exactly 5 real, distinct articles or news items published in the last 48 hours.",
        f"They must be genuinely relevant to a professional whose primary goal is: \"{goal}\".",
        f"Focus on these knowledge domains: {domains}.",
        f"Prioritise content from or relevant to: {regions}.",
    ]

    if countries:
        parts.append(f"Pay particular attention to developments in: {countries}.")
    if admired:
        parts.append(f"Where relevant, include news about: {admired}.")
    if exclusions:
        parts.append(f"Do NOT include any content about: {exclusions}.")

    parts += [
        "Cover a mix of: breaking news, market signals, long-form analysis, technology, and cultural/geopolitical context.",
        "For each item return: headline, a 2-sentence summary in your own words (never reproduce verbatim text), publication name, full URL, and publication date.",
        "Only include articles with real, working URLs. If you are not confident a URL is accurate, omit that item.",
        "Return ONLY a valid JSON array with no preamble, explanation, or markdown fences.",
        'Format: [{"headline": "", "summary": "", "source_name": "", "source_url": "", "published_date": ""}]',
    ]

    return ' '.join(parts)


def fetch_articles(user: dict, today: date, query_override: str = None) -> list[dict]:
    """
    Calls Perplexity to retrieve 5 real, sourced articles relevant to the user's profile.
    Returns a list of raw article dicts.
    Raises on API error or if fewer than 3 items are returned.
    """
    query = query_override or _build_query(user, today)
    print(f'[perplexity] Query for {user.get("email")}: {query[:300]}')

    response = requests.post(
        PERPLEXITY_URL,
        headers={
            'Authorization': f'Bearer {PERPLEXITY_API_KEY}',
            'Content-Type': 'application/json',
        },
        json={
            'model': PERPLEXITY_MODEL,
            'messages': [
                {
                    'role': 'system',
                    'content': (
                        'You are a precise research assistant. '
                        'Return only valid JSON arrays. '
                        'Never fabricate URLs or publication names. '
                        'If you cannot find 5 real articles, return fewer rather than inventing sources.'
                    ),
                },
                {
                    'role': 'user',
                    'content': query,
                },
            ],
            'temperature': 0.2,
            'max_tokens': 2000,
            'return_citations': True,
        },
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            f'Perplexity API error: {response.status_code} {response.text[:200]}'
        )

    data = response.json()
    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')

    if not content:
        raise RuntimeError('Perplexity returned empty content')

    # Strip accidental markdown fences
    clean = content.strip()
    if clean.startswith('```'):
        parts = clean.split('```')
        clean = parts[1]
        if clean.startswith('json'):
            clean = clean[4:]
        clean = clean.strip()

    try:
        items = json.loads(clean)
    except json.JSONDecodeError as e:
        raise RuntimeError(f'Perplexity response was not valid JSON: {clean[:300]}') from e

    if not isinstance(items, list) or len(items) < 3:
        print(f'[perplexity] Raw response: {clean[:500]}')
        raise RuntimeError(f'Perplexity returned fewer than 3 items ({len(items) if isinstance(items, list) else 0})')

    return items[:5]
