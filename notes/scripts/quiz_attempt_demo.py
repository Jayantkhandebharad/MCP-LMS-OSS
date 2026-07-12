#!/usr/bin/env python3
"""Phase 2 demo: complete a full quiz attempt over Moodle's REST API.

Walks the whole lifecycle as student1:
  start_attempt -> get_attempt_data (parse HTML!) -> process_attempt(finish) -> get_attempt_review

The ugly part is the point: answer submission requires parsing *rendered HTML*
form fields (q{attemptid}:{slot}_answer) out of the API response, because the
API returns the question exactly as the browser form would. Options are
shuffled per attempt, so answers must be matched by label text.

Usage: python3 quiz_attempt_demo.py <wstoken> [quizid]
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

BASE = "http://localhost:8080/webservice/rest/server.php"

# label text fragment -> what we believe is correct
CORRECT = {
    1: "Model Context Protocol",
    2: "Resources",
    3: "The server asks the client",
}


def call(token: str, function: str, **params):
    data = {"wstoken": token, "wsfunction": function, "moodlewsrestformat": "json", **params}
    req = urllib.request.Request(BASE, urllib.parse.urlencode(data).encode())
    with urllib.request.urlopen(req) as r:
        out = json.load(r)
    if isinstance(out, dict) and "exception" in out:
        raise RuntimeError(f"{function}: {out['errorcode']} - {out['message']}")
    return out


class RadioParser(HTMLParser):
    """Map each radio input's value -> its label text (Moodle wraps both in a div)."""

    def __init__(self):
        super().__init__()
        self.fields = {}      # name -> {value: label}
        self.hidden = {}      # name -> value  (sequencecheck etc.)
        self._pending = None  # (name, value) awaiting label text
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input" and a.get("type") == "radio":
            self._flush()
            self._pending = (a["name"], a["value"])
            self._buf = []
        elif tag == "input" and a.get("type") == "hidden" and a.get("name"):
            self.hidden[a["name"]] = a.get("value", "")

    def handle_data(self, data):
        if self._pending:
            self._buf.append(data)

    def _flush(self):
        if self._pending:
            name, value = self._pending
            label = re.sub(r"\s+", " ", "".join(self._buf)).strip(" .")
            self.fields.setdefault(name, {})[value] = label
            self._pending = None

    def close(self):
        self._flush()
        super().close()


def main():
    token = sys.argv[1]
    quizid = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    # A user can only have one attempt in progress; resume it if one exists.
    # (Gotcha: this is exactly what an MCP submit_quiz_answer tool must handle.)
    try:
        attempt = call(token, "mod_quiz_start_attempt", quizid=quizid)["attempt"]
    except RuntimeError as e:
        if "attemptstillinprogress" not in str(e):
            raise
        unfinished = call(token, "mod_quiz_get_user_attempts", quizid=quizid, status="unfinished")
        attempt = unfinished["attempts"][-1]
        print(f"resuming in-progress attempt {attempt['id']}")
    attemptid = attempt["id"]
    pages = sorted({int(p) for p in attempt["layout"].split(",") if p != "0"})
    print(f"attempt {attemptid} started, layout {attempt['layout']}")

    answers = {}
    for page in range(len(pages)):
        data = call(token, "mod_quiz_get_attempt_data", attemptid=attemptid, page=page)
        for q in data["questions"]:
            parser = RadioParser()
            parser.feed(q["html"])
            parser.close()
            name = next(n for n in parser.fields if n.endswith("_answer"))
            options = parser.fields[name]
            want = CORRECT[q["slot"]]
            value = next(v for v, label in options.items() if want in label)
            seqname = f"q{attemptid}:{q['slot']}_:sequencecheck"
            answers[name] = value
            answers[seqname] = parser.hidden[seqname]
            print(f"  slot {q['slot']} ({q['maxmark']} marks): '{want}' -> {name}={value}")

    # process_attempt takes data[i][name]/data[i][value] pairs
    flat = {}
    for i, (k, v) in enumerate(answers.items()):
        flat[f"data[{i}][name]"] = k
        flat[f"data[{i}][value]"] = v
    state = call(token, "mod_quiz_process_attempt", attemptid=attemptid, finishattempt=1, **flat)
    print(f"finished: state={state['state']}")

    review = call(token, "mod_quiz_get_attempt_review", attemptid=attemptid)
    print(f"grade: {review['grade']} | sum: {review['attempt']['sumgrades']}")
    for q in review["questions"]:
        print(f"  slot {q['slot']}: {q['state']} mark {q.get('mark')}/{q['maxmark']}")


if __name__ == "__main__":
    main()
