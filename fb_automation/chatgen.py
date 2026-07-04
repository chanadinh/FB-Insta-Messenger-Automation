from __future__ import annotations

from openai import OpenAI


def generate_follow_ups(
    first_message: str,
    contact_name: str,
    api_key: str,
    model: str = "gpt-5.4",
    num_messages: int = 3,
    tone: str = "friendly and casual",
) -> list[str]:
    """Use OpenAI to generate a sequence of follow-up chat messages.

    Returns a list of follow-up messages (not including the first message).
    """
    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are helping someone chat with {contact_name} on Facebook Messenger in Vietnamese. "
                    f"The tone should be {tone}. "
                    f"The messages should be in Vietnamese. "
                    f"Generate exactly {num_messages} short follow-up messages that naturally "
                    f"continue from the first message below. "
                    f"Each message should be 1-2 sentences max, like real texting. "
                    f"Return ONLY the messages, one per line, no numbering, no quotes."
                ),
            },
            {
                "role": "user",
                "content": f"First message already sent: \"{first_message}\"\n\nGenerate {num_messages} follow-up messages.",
            },
        ],
        temperature=0.9,
    )

    raw = response.choices[0].message.content.strip()
    follow_ups = [line.strip() for line in raw.splitlines() if line.strip()]

    return follow_ups[:num_messages]


def generate_reminder_message(
    idea: str,
    contact_name: str,
    api_key: str,
    model: str = "gpt-5.4",
    tone: str = "friendly and casual",
) -> str:
    """Turn a short reminder idea into one natural chat message."""
    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You write one short Messenger/Instagram DM for {contact_name}. "
                    f"Tone: {tone}. Language: Vietnamese unless the idea says otherwise. "
                    f"1–2 sentences max, like real texting. No quotes, no labels."
                ),
            },
            {
                "role": "user",
                "content": f"Reminder idea: {idea}",
            },
        ],
        temperature=0.8,
    )

    return response.choices[0].message.content.strip()
