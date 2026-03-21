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

    include_prompts = False
    if prompts_freq == 'Yes, every day':
        include_prompts = True
    elif prompts_freq == 'A few times a week':
        include_prompts = today.weekday() in (0, 2, 4)
    elif prompts_freq == 'Only when relevant':
        include_prompts = True

    prompts_instruction = (
        'Also include a "prompts" key with three critical thinking questions:\n'
        '- "debate": put the subscriber in a specific, realistic professional scenario '
        'they might face given their role and goal — not an abstract question\n'
        '- "synthesis": connect two of today\'s five items to the subscriber\'s goal\n'
        '- "prediction": a forward-looking question with a specific timeframe (e.g. "In 18 months...")'
        if include_prompts else
        'Do NOT include a "prompts" key.'
    )

    admired_line = f"Track news about these specific organisations or people: {user['admired_orgs']}." \
        if user.get('admired_orgs') else ''
    exclusion_line = f"NEVER include content about: {exclusions}. Hard rule — no exceptions." \
        if exclusions else ''
    gaps_line = f"Intentionally address this knowledge gap: {user['knowledge_gaps']}." \
        if user.get('knowledge_gaps') else ''

    name = user.get('name', 'the subscriber')
    goal = user.get('primary_goal', 'professional development and growth')

    system = (
        f"You are a personal intelligence curator for Early Edge.\n\n"
        f"The subscriber's name is: {name}\n"
        f"Their primary goal is: {goal}\n"
        f"Their knowledge focus areas are: {domains}\n"
        f"Their geographic focus is: {regions}\n"
        f"Their reading style preference is: {style_instruction}\n"
        f"Topics to exclude: {exclusions or 'None'}\n\n"
        f"HARD RULES — never violate these:\n"
        f"- Never recommend buying, selling, or holding any financial instrument. "
        f"Describe market movements only.\n"
        f"- Never give legal, medical, or personal financial advice.\n"
        f"- Never reproduce more than one sentence verbatim from any source.\n"
        f"- Always name the source publication for every item.\n"
        f"- If you are not confident a specific claim about a named company or individual "
        f"is accurate, do not include it.\n"
        f"- Never include content from the subscriber's exclusion list.\n"
        f"- The 'why_it_matters' line must reference the subscriber's goal verbatim or very "
        f"closely. If it could apply to any subscriber, rewrite it."
    )

    user_message = f"""Today is {today.strftime('%A, %d %B %Y')}.

Search the web for today's most relevant news, analysis, and signals for this person.

Profile:
- Role: {user.get('role', 'professional')}
- Industry: {user.get('industry', '')}
- Career stage: {user.get('career_stage', '')}
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
- headline (max 12 words)
- summary ({depth_instruction}) — write in your own words, never reproduce verbatim text from the source
- why_it_matters: a line that references {name}'s specific goal directly — this MUST be personalised to them, not generic. Reference their goal text specifically.
- source (publication name)
- url (real, working URL)
- category (one of the five above)
- commercial: false (set to true only if this is sponsored/affiliate content)

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
      "url": "https://...",
      "commercial": false
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

    result_text = ""
    for block in response.content:
        if hasattr(block, 'text'):
            result_text += block.text

    result_text = result_text.strip()
    if result_text.startswith("```"):
        parts = result_text.split("```")
        result_text = parts[1]
        if result_text.startswith("json"):
            result_text = result_text[4:]

    return json.loads(result_text.strip())


def validate_briefing(briefing: dict, user: dict) -> dict:
    """Second-pass validation. Returns {"valid": bool, "flags": [str]}."""
    content_str = json.dumps(briefing, indent=2)
    goal = user.get('primary_goal', '')
    exclusions = user.get('exclusions', '') or 'None'
    name = user.get('name', '')

    validation_prompt = f"""You are a content validator for Early Edge briefings.

Subscriber name: {name}
Subscriber goal: {goal}
Exclusions: {exclusions}

Review this briefing and check for ALL of the following issues:
1. Does any item make a specific factual claim about a named company or individual that could be inaccurate or unverifiable?
2. Does any item contain investment advice or a recommendation to take financial action (buy, sell, invest, purchase shares, etc.)?
3. Does any item appear to reproduce more than one sentence verbatim from a source?
4. Does the "why_it_matters" line for each item specifically reference the subscriber's goal? Flag any that are generic and could apply to any subscriber.
5. Does any item's content relate to topics on the subscriber's exclusion list?

Briefing to validate:
{content_str}

Return ONLY valid JSON:
{{
  "valid": true,
  "flags": []
}}

If you find issues, set valid to false and list each issue clearly:
{{
  "valid": false,
  "flags": ["Item 2: contains investment recommendation — 'consider buying'", "Item 4: why_it_matters is generic"]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": validation_prompt}],
    )

    result_text = response.content[0].text.strip()
    if result_text.startswith("```"):
        parts = result_text.split("```")
        result_text = parts[1]
        if result_text.startswith("json"):
            result_text = result_text[4:]

    return json.loads(result_text.strip())
