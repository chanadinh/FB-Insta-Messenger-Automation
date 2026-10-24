"""Filter known outgoing text, including historical truncated CSV previews."""

import re


def normalize_message_text(text: str) -> str:
    text = re.sub(r"^\s*\[(?:IG|FB)\]\s*", "", text)
    text = re.sub(r"^\s*\[(?:reply|follow-up \d+)\]\s*", "", text)
    return " ".join(text.lower().split())


def matches_sent_message(text: str, sent_messages: list[str]) -> bool:
    normalized = normalize_message_text(text)
    for sent in sent_messages:
        outgoing = normalize_message_text(sent)
        if outgoing and normalized == outgoing:
            return True
        # Older logs stored exactly 80 characters and cannot recover the suffix.
        if len(sent) == 80 and outgoing and normalized.startswith(outgoing):
            return True
    return False
