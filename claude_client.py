import anthropic
import json
import os
from datetime import date

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

DEPTH_LABELS = {
    1: "one sentence only — the key takeaway",
    2: "2-sentence summary",
    3: "3-sentence summary with context",
    4: "full paragraph with detailed analysis",
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

PROMPT_ARCHETYPES = {
    "debate": "A debate challenge that puts the subscriber in a realistic professional scenario they could actually face given their role and goal — not an abstract question.",
    "synthesis": "A synthesis question connecting two of today's items — what does the combination mean for the subscriber's goal?",
    "prediction": "A forward-looking prediction question with a specific timeframe (e.g. 'In the next 18 months...').",
    "devils_advocate": "The strongest argument against the consensus view in today's content — what if the conventional wisdom is wrong?",
    "scenario": "A 'you're in the room' scenario directly relevant to the subscriber's career goal and today's news.",
}


def personalise_briefing(user: dict, raw_articles: list[dict], today: date) -> dict:
    """
    Takes raw articles from Perplexity and adds personalisation via Claude.
    Returns a structured briefing dict with items and optional prompts.
    """
    name = user.get('name', 'the subscriber')
    goal = user.get('primary_goal', 'professional development and growth')
    engage_style = user.get('engage_style') or 'Give me the signal'
    depth = int(user.get('depth_score') or 2)
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
        f'Also generate 3 critical thinking prompts. Choose the most appropriate archetypes '
        f'for today\'s content from: {json.dumps(PROMPT_ARCHETYPES)}. '
        f'Each prompt must be specific to today\'s content AND to {name}\'s goal. '
        f'A generic prompt that could apply to any subscriber is not acceptable. '
        f'Include a "prompts" key: {{"debate": "...", "synthesis": "...", "prediction": "..."}}'
        if include_prompts else
        'Do NOT include a "prompts" key.'
    )

    system = (
        f"You are the personalisation engine for Early Edge, a goal-aligned daily briefing.\n\n"
        f"THE SUBSCRIBER:\n"
        f"- Name: {name}\n"
        f"- Primary goal: \"{goal}\"\n"
        f"- Career stage: {user.get('career_stage', '')}\n"
        f"- Industry: {user.get('industry', '')}\n"
        f"- Reading style: {style_instruction}\n\n"
        f"HARD RULES — never violate these:\n"
        f"- The 'why_it_matters' field MUST reference {name}'s goal verbatim or very closely. "
        f"If it could apply to any subscriber, it is not personal enough — rewrite it.\n"
        f"- Never recommend buying, selling, or holding any financial instrument.\n"
        f"- Never give legal, medical, or personal financial advice.\n"
        f"- Never reproduce more than one sentence verbatim from a source.\n"
        f"- All source URLs must come from the input — never invent or modify URLs.\n"
        f"- Return ONLY valid JSON. No preamble, no explanation, no markdown fences."
    )

    articles_json = json.dumps(raw_articles, indent=2)

    user_message = f"""Today is {today.strftime('%A, %d %B %Y')}.

Here are the 5 articles found for {name}:

{articles_json}

Transform these into a personalised Early Edge briefing.

For each item provide:
- number (1-5)
- category (one of: Breaking News, Market Signal, Analysis, Technology, Culture & Geopolitics)
- headline (use or lightly edit the original — max 12 words)
- summary ({depth_instruction}) — rewritten in your own words, never reproduce verbatim text
- why_it_matters: MUST reference "{goal}" specifically — this is the most important field
- source (publication name from input — do not change)
- url (from input — do not change)
- commercial: false

{prompts_instruction}

Return a single JSON object:
{{
  "items": [
    {{
      "number": 1,
      "category": "...",
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
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )

    result_text = response.content[0].text.strip()
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
1. Does any item make a specific factual claim about a named company or individual that could be inaccurate?
2. Does any item contain investment advice or a recommendation to take financial action?
3. Does any item appear to reproduce more than one sentence verbatim from a source?
4. Does the "why_it_matters" line for each item specifically reference the subscriber's goal? Flag any that are generic.
5. Does any item's content relate to topics on the subscriber's exclusion list?

Briefing to validate:
{content_str}

Return ONLY valid JSON:
{{"valid": true, "flags": []}}

If issues found:
{{"valid": false, "flags": ["description of issue"]}}"""

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
