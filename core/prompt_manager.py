"""Prompt templates for different analysis modes."""

from __future__ import annotations

from enum import Enum


class PromptMode(str, Enum):
    """Available vision analysis modes."""

    GIT = "git"
    ENGLISH = "english"
    CODE = "code"


_PROMPTS: dict[PromptMode, str] = {
    PromptMode.GIT: (
        "You are a senior Git mentor reviewing a screenshot from a developer's screen. "
        "Identify any Git-related content (commits, diffs, branch names, merge conflicts, "
        "CI status). Explain what you see clearly and suggest concrete next steps. "
        "If no Git content is visible, say so briefly."
    ),
    PromptMode.ENGLISH: (
        "You are a professional English language coach. Analyze visible text in the "
        "screenshot for grammar, clarity, tone, and spelling. Provide corrected versions "
        "where helpful and explain key improvements concisely."
    ),
    PromptMode.CODE: (
        "You are a senior software engineer doing a quick code review from a screenshot. "
        "Identify the language/framework if possible, explain what the code does, point out "
        "bugs or smells, and suggest improvements. Be concise and actionable."
    ),
}


def get_system_prompt(mode: PromptMode) -> str:
    """Return the system prompt for the given analysis mode."""
    return _PROMPTS[mode]


def list_modes() -> list[PromptMode]:
    """Return all available prompt modes."""
    return list(PromptMode)
