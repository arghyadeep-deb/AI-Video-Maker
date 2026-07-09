"""Impersonation guard for avatar persona descriptions —
specs/04-tasks/task-19-moderation-consent.md: styling prompts must "hard-forbid
'make me look like <named real person>' edits".

Legitimate personas describe a role or style ("wise elderly astrologer",
"friendly businessman", "Indian classical musician") - these are generic
even when they happen to contain a capitalized word. What this guards
against specifically is the *structural* pattern of a resemblance verb
("look like", "dress as", ...) directly followed by what reads as a
specific person's proper name (two-plus consecutive capitalized words) -
narrow on purpose, to avoid rejecting ordinary persona descriptions that
simply contain an adjective + noun that both happen to be capitalized.

This is a basic-due-diligence heuristic for a 1-2 user private site, not
an adversarial-user-proof filter - see the task's own framing ("the
responsible floor for likeness tech", not the full public-abuse
apparatus, which is explicitly out of scope here).
"""
import re

_RESEMBLANCE_VERBS = (
    r"(?:[Ll]ook(?:s|ing)? like|[Rr]esembl(?:e|ing)|[Dd]ress(?:ed)? (?:up )?as|"
    r"[Bb]ecome|[Aa]s if (?:[Ii]'?m|[Yy]ou'?re))"
)
# Deliberately case-sensitive: capitalization is the actual signal that
# distinguishes a specific person's proper name ("Tom Cruise") from a
# generic persona descriptor. re.IGNORECASE would need to apply to the verb
# phrase only, not this half of the pattern.
_PROPER_NAME = r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+"

IMPERSONATION_PATTERN = re.compile(rf"\b{_RESEMBLANCE_VERBS}\s+{_PROPER_NAME}\b")

IMPERSONATION_MESSAGE = (
    "Personas must describe a role or style (e.g. \"wise elderly astrologer\"), "
    "not a request to resemble a specific named person"
)


def check_persona_description(persona_description: str) -> str | None:
    """Returns an error message if this looks like a request to resemble a
    specific named real person, else None."""
    if IMPERSONATION_PATTERN.search(persona_description):
        return IMPERSONATION_MESSAGE
    return None
