"""Unit tests for the quiz HTML parser — no Moodle needed."""

from moodle_mcp.quiz_parser import html_to_text, parse_question

# Trimmed-down but structurally faithful Moodle 5.x question HTML.
QUESTION_HTML = """
<div id="question-4-1" class="que multichoice deferredfeedback notyetanswered">
  <div class="info"><h3 class="no">Question <span class="qno">1</span></h3></div>
  <div class="content">
    <div class="formulation clearfix">
      <input type="hidden" name="q4:1_:sequencecheck" value="1">
      <div class="qtext"><p>What does MCP stand for?</p></div>
      <fieldset class="answer">
        <div class="r0">
          <input type="radio" name="q4:1_answer" value="0" id="q4_1_answer0">
          <label for="q4_1_answer0"><span class="answernumber">a. </span>Machine Context Protocol</label>
        </div>
        <div class="r1">
          <input type="radio" name="q4:1_answer" value="1" id="q4_1_answer1">
          <label for="q4_1_answer1"><span class="answernumber">b. </span>Model Context Protocol</label>
        </div>
      </fieldset>
    </div>
  </div>
</div>
"""


def test_parse_question_extracts_everything():
    q = parse_question(1, 2.0, QUESTION_HTML)
    assert q.text == "What does MCP stand for?"
    assert q.answer_field == "q4:1_answer"
    assert q.options == {
        "0": "Machine Context Protocol",
        "1": "Model Context Protocol",
    }
    assert q.hidden_fields == {"q4:1_:sequencecheck": "1"}
    assert q.max_mark == 2.0


def test_parse_question_without_radios_raises():
    import pytest

    with pytest.raises(ValueError, match="multiple-choice"):
        parse_question(1, 1.0, "<div class='qtext'>essay question</div>")


def test_html_to_text():
    html = "<h3>Title</h3><p>Para one.</p><ul><li>alpha</li><li>beta</li></ul>"
    text = html_to_text(html)
    assert "Title" in text
    assert "- alpha" in text
    assert "<" not in text
