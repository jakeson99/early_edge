import anthropic
import json
import os
from datetime import date

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

DEPTH_LABELS = {
    1: "one sentence only — the key takeaway",
    2: "headline + one-sentence summary + one-sentence relevance note",
    3: "headline + 2–3 sentence summary + why it matters for their goal",
    4: "headline + full paragraph briefing + detailed analysis of relevance to their goal",
}

STYLE_INSTRUCTIONS = {
    "Give me the signal": (
        "Be direct and actionable. Lead with the implication, not the story. "
        "What does this mean right now for someone with their goal?"
    ),
    "Give me the story": (
        "Provide context and narrative. Help the user understand the why behind the news, "
        "not just the what. Set the scene."
    ),
    "Challenge me": (
        "Lead with the counter-intuitive or uncomfortable angle. Surface the view "
        "most people aren't taking. Challenge assumptions."
    ),
    "Connect the dots": (
        "Emphasise synthesis. Show how this item connects to broader trends, "
        "to other items in the briefing, or to the user's longer-term goals."
    ),
}


def generate_briefing(user: dict, today: date) -> dict:
    domains = user.get('domains') or 'General business and current affairs'
    regions = user.get('regions') or 'Global'
    engage_style = user.get('engage_style') or 'Give me the signal'
    depth = int(user.get('depth_score') or 2)
    exclusions = user.get('exclusions') or ''
    prompts_freq = user.get('prompts_freq') or 'Yes, every day'

    style_instruction = STYLE_INSTRUCTIONS.get(engage_style, STYLE_INSTRUCTIONS["Give me the signal"])
    depth_instruction = DEPTH_LABELS.get(depth, DEPTH_LABELS[2])

    # Decide whether to include prompts today
    include_prompts = False
    if prompts_freq == 'Yes, every day':
        include_prompts = True
    elif prompts_freq == 'A few times a week':
        include_prompts = today.weekday() in (0, 2, 4)  # Mon, Wed, Fri
    elif prompts_freq == 'Only when relevant':
        include_prompts = True  # Claude will judge

    prompts_instruction = (
        'Also include a "prompts" key with three critical thinking questions: '
        '"debate" (argue the opposite of one of the items), '
        '"synthesis" (connect two items to the user\'s goal), '
        '"prediction" (what happens in the next 12 months given this).'
        if include_prompts else
        'Do NOT include a "prompts" key.'
    )

    admired_line = f"Track news about these specific organisations or people: {user['admired_orgs']}." \
        if user.get('admired_orgs') else ''
    exclusion_line = f"NEVER include content about: {exclusions}. Hard rule — no exceptions." \
        if exclusions else ''
    gaps_line = f"Intentionally address this knowledge gap: {user['knowledge_gaps']}." \
        if user.get('knowledge_gaps') else ''

    system = (
        f"You are a personal intelligence curator for {user['name']}, "
        f"a {user.get('career_stage', 'professional')}. "
        f"Their primary goal: {user.get('primary_goal', 'professional development and growth')}. "
        f"Writing style: {style_instruction}"
    )

    user_message = f"""Today is {today.strftime('%A, %d %B %Y')}.

Search the web for today's most relevant news, analysis, and signals for this person:

Profile:
- Role: {user.get('role', 'professional')}
- Industry: {user.get('industry', '')}
- Knowledge domains to cover: {domains}
- Regions to track: {regions}
- Goal timeline: {user.get('timeline', '')}
{gaps_line}
{admired_line}
{exclusion_line}

Select exactly 5 items. Cover these categories (weighted toward the user's domains):
1. Breaking news in their goal domain
2. Market or financial signal
3. Long-form analysis or strategic essay
4. Technology or innovation development
5. Cultural, geopolitical, or historical context piece

For each item, provide:
- headline
- summary ({depth_instruction})
- why_it_matters (directly tied to their specific goal — be personal and precise)
- source (publication name)
- url (real, working URL)
- category (one of the five above)

{prompts_instruction}

Return ONLY valid JSON in this exact structure — no markdown, no preamble:
{{
  "items": [
    {{
      "number": 1,
      "category": "Breaking News",
      "headline": "...",
      "summary": "...",
      "why_it_matters": "...",
      "source": "...",
      "url": "https://..."
    }}
  ],
  "prompts": {{
    "debate": "...",
    "synthesis": "...",
    "prediction": "..."
  }}
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )

    # Extract text content from response blocks
    result_text = ""
    for block in response.content:
        if hasattr(block, 'text'):
            result_text += block.text

    # Strip any accidental markdown fences
    result_text = result_text.strip()
    if result_text.startswith("```"):
        parts = result_text.split("```")
        result_text = parts[1]
        if result_text.startswith("json"):
            result_text = result_text[4:]

    return json.loads(result_text.strip())
