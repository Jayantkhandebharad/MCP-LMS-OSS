"""Parse Moodle's rendered quiz HTML into structured questions.

Moodle's quiz API does not return question data — it returns the same HTML a
browser form would get (see notes/api-cheatsheet.md). To let an LLM take a
quiz we must extract, per question:

- the question text
- the radio options (value -> label), which are SHUFFLED per attempt
- the exact form field names to post back (q{attempt}:{slot}_answer)
- the hidden sequencecheck fields Moodle uses for optimistic concurrency

This module is the "clean tools over a messy API" showcase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class ParsedQuestion:
    slot: int
    max_mark: float
    text: str
    options: dict[str, str]  # form value -> option label
    answer_field: str  # e.g. "q4:1_answer"
    hidden_fields: dict[str, str]  # sequencecheck etc., must be posted back


class _QuestionHTMLParser(HTMLParser):
    """Single pass over one question's HTML: question text, radios, hidden inputs."""

    def __init__(self) -> None:
        super().__init__()
        self.radio_fields: dict[str, dict[str, str]] = {}  # name -> {value: label}
        self.hidden: dict[str, str] = {}
        self._qtext_depth = 0  # >0 while inside the div.qtext subtree
        self._qtext_parts: list[str] = []
        self._pending_radio: tuple[str, str] | None = None
        self._label_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if self._qtext_depth:
            self._qtext_depth += 1
        elif tag == "div" and "qtext" in classes:
            self._qtext_depth = 1
        if tag == "input":
            if a.get("type") == "radio":
                self._flush_radio()
                self._pending_radio = (a.get("name", ""), a.get("value", ""))
                self._label_parts = []
            elif a.get("type") == "hidden" and a.get("name"):
                self.hidden[a["name"]] = a.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if self._qtext_depth:
            self._qtext_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._qtext_depth:
            self._qtext_parts.append(data)
        if self._pending_radio:
            self._label_parts.append(data)

    def _flush_radio(self) -> None:
        if self._pending_radio:
            name, value = self._pending_radio
            label = _clean(" ".join(self._label_parts))
            # Moodle prefixes labels with "a.", "b." etc.
            label = re.sub(r"^[a-z]\.\s*", "", label)
            self.radio_fields.setdefault(name, {})[value] = label
            self._pending_radio = None

    @property
    def question_text(self) -> str:
        return _clean(" ".join(self._qtext_parts))

    def finish(self) -> None:
        self._flush_radio()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" . ")


def parse_question(slot: int, max_mark: float, html: str) -> ParsedQuestion:
    """Extract one structured question from Moodle's attempt-data HTML."""
    parser = _QuestionHTMLParser()
    parser.feed(html)
    parser.finish()

    answer_field = next(
        (name for name in parser.radio_fields if name.endswith("_answer")), None
    )
    if answer_field is None:
        raise ValueError(
            f"slot {slot}: no radio answer field found — only multiple-choice "
            "questions are supported so far"
        )
    return ParsedQuestion(
        slot=slot,
        max_mark=max_mark,
        text=parser.question_text,
        options=parser.radio_fields[answer_field],
        answer_field=answer_field,
        hidden_fields={k: v for k, v in parser.hidden.items() if "sequencecheck" in k},
    )


def html_to_text(html: str) -> str:
    """Readable plain text from Moodle content HTML (pages, summaries)."""

    class Extractor(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:
            self.parts.append(data)

        def handle_endtag(self, tag: str) -> None:
            if tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "ul", "ol", "br"}:
                self.parts.append("\n")

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "li":
                self.parts.append("- ")
            elif tag == "br":
                self.parts.append("\n")

    extractor = Extractor()
    extractor.feed(html)
    text = "".join(extractor.parts)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
