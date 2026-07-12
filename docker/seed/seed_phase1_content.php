<?php
/**
 * Phase 1 content seed — pages + weighted MCQ quiz for INTRO-MCP. Idempotent.
 *
 *   docker compose cp seed/seed_phase1_content.php moodle:/tmp/
 *   docker compose exec -T moodle php /tmp/seed_phase1_content.php
 *
 * Moodle's web services can't create activities, so this uses internal APIs:
 * add_moduleinfo() for modules, qformat_gift import for questions,
 * quiz_add_quiz_question() with per-question maxmark = the weightage.
 */

define('CLI_SCRIPT', true);
require '/var/www/html/config.php';
require_once $CFG->dirroot . '/course/lib.php';
require_once $CFG->dirroot . '/course/modlib.php';
require_once $CFG->dirroot . '/lib/questionlib.php';
require_once $CFG->dirroot . '/question/format.php';
require_once $CFG->dirroot . '/question/format/gift/format.php';
require_once $CFG->dirroot . '/mod/quiz/locallib.php';

function say($msg) { echo $msg . "\n"; }

$course = $DB->get_record('course', ['shortname' => 'INTRO-MCP'], '*', MUST_EXIST);
$admin = get_admin();
\core\session\manager::set_user($admin); // module creation checks capabilities

// ---------- 1. Page activities ----------
$pages = [
    [
        'section' => 1,
        'name' => 'What is the Model Context Protocol?',
        'content' => '<h3>The problem MCP solves</h3>
<p>Every AI assistant needs to reach the outside world: your files, your database,
your LMS. Before MCP, every app × every data source needed a custom integration.
MCP is a <strong>standard protocol</strong> — think "USB-C for AI" — so any client
(Claude Desktop, Cursor, ChatGPT) can talk to any server that speaks it.</p>
<h3>The shape of it</h3>
<p>An <em>MCP server</em> exposes capabilities; an <em>MCP client</em> (inside the
AI app) connects to it. They exchange JSON-RPC 2.0 messages over a transport —
<code>stdio</code> for local servers, <code>Streamable HTTP</code> for remote ones.</p>
<p>This very course is served to AI clients by an MCP server wrapping this Moodle
site. You are inside the demo.</p>',
    ],
    [
        'section' => 2,
        'name' => 'Tools, Resources, and Prompts',
        'content' => '<h3>The three primitives</h3>
<ul>
<li><strong>Tools</strong> — functions the <em>model</em> decides to call
(<code>list_my_courses</code>, <code>submit_quiz_answer</code>). Side effects allowed.</li>
<li><strong>Resources</strong> — read-only data the <em>application</em> attaches as
context, addressed by URI (<code>course://2/topic/1</code>). No side effects.</li>
<li><strong>Prompts</strong> — reusable templates the <em>user</em> picks explicitly
(a <code>/quiz_me</code> command). User-controlled.</li>
</ul>
<p>The rule of thumb: who initiates? Model → tool. App → resource. User → prompt.</p>',
    ],
];

$pagemoduleid = $DB->get_field('modules', 'id', ['name' => 'page'], MUST_EXIST);
foreach ($pages as $p) {
    if ($DB->record_exists_sql(
        "SELECT 1 FROM {page} WHERE course = ? AND name = ?", [$course->id, $p['name']])) {
        say("[skip] page '{$p['name']}' exists");
        continue;
    }
    $mi = new stdClass();
    $mi->modulename = 'page';
    $mi->module = $pagemoduleid;
    $mi->course = $course->id;
    $mi->section = $p['section'];
    $mi->name = $p['name'];
    $mi->introeditor = ['text' => '', 'format' => FORMAT_HTML, 'itemid' => 0];
    $mi->page = ['text' => $p['content'], 'format' => FORMAT_HTML, 'itemid' => 0];
    $mi->display = 5; // RESOURCELIB_DISPLAY_OPEN
    $mi->printheading = 1;
    $mi->printintro = 0;
    $mi->printlastmodified = 1;
    $mi->popupwidth = 620;
    $mi->popupheight = 450;
    $mi->visible = 1;
    $mi->visibleoncoursepage = 1;
    $mi->cmidnumber = '';
    $mi->groupmode = 0;
    $mi->groupingid = 0;
    $mi->completion = 0;
    add_moduleinfo($mi, $course);
    say("[ok] page '{$p['name']}' created in section {$p['section']}");
}

// ---------- 2. Questions via GIFT import ----------
// Moodle 5.x: course-context question categories are gone — questions live in
// a qbank module instance. question_make_default_categories() is deprecated
// and actually crashes (inserts parent=NULL into a NOT NULL column).
$qbankcm = \core_question\local\bank\question_bank_helper::get_default_open_instance_system_type($course, true);
$qbankcontext = context_module::instance($qbankcm->id);
$category = question_get_default_category($qbankcontext->id, true);
say("[ok] qbank instance cm {$qbankcm->id}, default category {$category->id}");

$gift = <<<'GIFT'
::MCP acronym::What does MCP stand for? {
=Model Context Protocol
~Model Communication Protocol
~Machine Context Protocol
~Managed Client Protocol
}

::Primitive for read-only data::Which MCP primitive exposes read-only data addressed by a URI, with no side effects? {
=Resources
~Tools
~Prompts
~Sampling
}

::Sampling direction::In MCP, "sampling" means one side asks the other to run an LLM completion. Who initiates it? {
=The server asks the client
~The client asks the server
~The user asks the server directly
~The model asks the IdP
}
GIFT;

$giftfile = '/tmp/mcp_questions.gift';
file_put_contents($giftfile, $gift);

$existingq = $DB->count_records_sql(
    "SELECT COUNT(1) FROM {question} q
      JOIN {question_versions} qv ON qv.questionid = q.id
      JOIN {question_bank_entries} qbe ON qbe.id = qv.questionbankentryid
     WHERE qbe.questioncategoryid = ?", [$category->id]);

$questionids = [];
if ($existingq >= 3) {
    say("[skip] questions already imported ($existingq in category)");
    $questionids = $DB->get_fieldset_sql(
        "SELECT q.id FROM {question} q
          JOIN {question_versions} qv ON qv.questionid = q.id
          JOIN {question_bank_entries} qbe ON qbe.id = qv.questionbankentryid
         WHERE qbe.questioncategoryid = ? ORDER BY q.id", [$category->id]);
} else {
    $qformat = new qformat_gift();
    $qformat->setCategory($category);
    $qformat->setContexts([$qbankcontext]);
    $qformat->setCourse($course);
    $qformat->setFilename($giftfile);
    $qformat->setRealfilename('mcp_questions.gift');
    $qformat->setMatchgrades('error');
    $qformat->setCatfromfile(false);
    $qformat->setStoponerror(true);
    if (!$qformat->importpreprocess() || !$qformat->importprocess() || !$qformat->importpostprocess()) {
        cli_error('GIFT import failed');
    }
    $questionids = $qformat->questionids;
    say('[ok] imported ' . count($questionids) . ' MCQ questions');
}

// ---------- 3. Quiz activity ----------
$quizname = 'MCP Basics Quiz';
$quiz = $DB->get_record('quiz', ['course' => $course->id, 'name' => $quizname]);
if (!$quiz) {
    $quizmoduleid = $DB->get_field('modules', 'id', ['name' => 'quiz'], MUST_EXIST);
    $mi = new stdClass();
    // Start from the site-wide quiz defaults (keys match form field names).
    foreach ((array) get_config('quiz') as $key => $value) {
        $mi->$key = $value;
    }
    $mi->modulename = 'quiz';
    $mi->module = $quizmoduleid;
    $mi->course = $course->id;
    $mi->section = 3;
    $mi->name = $quizname;
    $mi->introeditor = [
        'text' => '<p>Three questions, worth 1, 2 and 3 marks — 6 marks total. Unlimited attempts.</p>',
        'format' => FORMAT_HTML, 'itemid' => 0,
    ];
    $mi->quizpassword = '';
    $mi->grade = 6;           // grade scale = sum of marks, so marks map 1:1
    $mi->attempts = 0;        // unlimited
    $mi->timeopen = 0;
    $mi->timeclose = 0;
    $mi->timelimit = 0;
    $mi->visible = 1;
    $mi->visibleoncoursepage = 1;
    $mi->cmidnumber = '';
    $mi->groupmode = 0;
    $mi->groupingid = 0;
    $mi->completion = 0;
    $info = add_moduleinfo($mi, $course);
    $quiz = $DB->get_record('quiz', ['id' => $info->instance], '*', MUST_EXIST);
    say("[ok] quiz '$quizname' created in section 3");
} else {
    say("[skip] quiz '$quizname' exists");
}

// ---------- 4. Attach questions with weightage (maxmark) ----------
$weights = [1, 2, 3];
$existingslots = $DB->count_records('quiz_slots', ['quizid' => $quiz->id]);
if ($existingslots >= 3) {
    say("[skip] quiz already has $existingslots questions");
} else {
    foreach (array_values($questionids) as $i => $qid) {
        quiz_add_quiz_question($qid, $quiz, 0, $weights[$i]);
        say("[ok] question $qid added with maxmark {$weights[$i]}");
    }
    // Moodle 5.x: quiz_update_sumgrades() is gone; use the grade calculator.
    \mod_quiz\quiz_settings::create($quiz->id)->get_grade_calculator()->recompute_quiz_sumgrades();
    say('[ok] sumgrades recomputed');
}

say('=== content seed done ===');
