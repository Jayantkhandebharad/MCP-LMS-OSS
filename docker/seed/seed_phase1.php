<?php
/**
 * Phase 1 seed script — idempotent. Run inside the moodle container:
 *
 *   docker compose cp seed/seed_phase1.php moodle:/tmp/seed_phase1.php
 *   docker compose exec -T moodle php /tmp/seed_phase1.php
 *
 * Does everything scriptable: web services + REST protocol, test users,
 * courses, enrolments, external service + per-user tokens (printed at end).
 * Course *content* (pages, quiz) is created via the admin UI afterwards —
 * Moodle's web services have no create-activity functions.
 */

define('CLI_SCRIPT', true);
require '/var/www/html/config.php';
require_once $CFG->dirroot . '/course/lib.php';
require_once $CFG->dirroot . '/user/lib.php';
require_once $CFG->dirroot . '/lib/enrollib.php';
require_once $CFG->dirroot . '/webservice/lib.php';
require_once $CFG->dirroot . '/lib/externallib.php';

function say($msg) { echo $msg . "\n"; }

// ---------- 1. Enable web services + REST ----------
set_config('enablewebservices', 1);
$protocols = array_filter(explode(',', (string) get_config('core', 'webserviceprotocols')));
if (!in_array('rest', $protocols)) {
    $protocols[] = 'rest';
    set_config('webserviceprotocols', implode(',', $protocols));
}
say('[ok] web services enabled, REST protocol active');

// Let every authenticated user use the REST protocol (tokens still required).
$authuserrole = $DB->get_record('role', ['shortname' => 'user'], '*', MUST_EXIST);
assign_capability('webservice/rest:use', CAP_ALLOW, $authuserrole->id,
    context_system::instance()->id, true);
say('[ok] webservice/rest:use allowed for authenticated users');

// ---------- 2. Test users ----------
$users = [
    ['username' => 'student1', 'firstname' => 'Sam',  'lastname' => 'Student',
     'email' => 'student1@example.com', 'password' => 'Student1!pass'],
    ['username' => 'teacher1', 'firstname' => 'Tina', 'lastname' => 'Teacher',
     'email' => 'teacher1@example.com', 'password' => 'Teacher1!pass'],
];
$userids = [];
foreach ($users as $u) {
    $existing = $DB->get_record('user', ['username' => $u['username'], 'deleted' => 0]);
    if ($existing) {
        $userids[$u['username']] = $existing->id;
        say("[skip] user {$u['username']} exists (id {$existing->id})");
        continue;
    }
    $user = (object) $u;
    $user->auth = 'manual';
    $user->confirmed = 1;
    $user->mnethostid = $CFG->mnet_localhost_id;
    $id = user_create_user($user, true, false);
    $userids[$u['username']] = $id;
    say("[ok] created user {$u['username']} (id $id)");
}

// ---------- 3. Courses ----------
$defaultcategory = $DB->get_field_sql('SELECT MIN(id) FROM {course_categories}');
$courses = [
    ['fullname' => 'Intro to MCP', 'shortname' => 'INTRO-MCP',
     'summary' => 'The Model Context Protocol from zero: what it is, its primitives, and how servers talk to AI clients.',
     'numsections' => 3],
    ['fullname' => 'Docker Fundamentals', 'shortname' => 'DOCKER-101',
     'summary' => 'Containers, images, volumes and compose — the minimum to self-host anything.',
     'numsections' => 2],
];
$courseids = [];
foreach ($courses as $c) {
    $existing = $DB->get_record('course', ['shortname' => $c['shortname']]);
    if ($existing) {
        $courseids[$c['shortname']] = $existing->id;
        say("[skip] course {$c['shortname']} exists (id {$existing->id})");
        continue;
    }
    $course = create_course((object) array_merge($c, [
        'category' => $defaultcategory,
        'format' => 'topics',
        'visible' => 1,
        'summaryformat' => FORMAT_HTML,
    ]));
    $courseids[$c['shortname']] = $course->id;
    say("[ok] created course {$c['shortname']} (id {$course->id})");
}

// Name the INTRO-MCP topic sections so the course has real structure.
$sections = [1 => 'What is MCP?', 2 => 'MCP Primitives', 3 => 'Check Your Knowledge'];
foreach ($sections as $num => $name) {
    $section = $DB->get_record('course_sections',
        ['course' => $courseids['INTRO-MCP'], 'section' => $num]);
    if ($section && $section->name !== $name) {
        course_update_section($courseids['INTRO-MCP'], $section, ['name' => $name]);
        say("[ok] section $num named '$name'");
    }
}

// ---------- 4. Enrolments ----------
$enrolments = [
    ['student1', 'INTRO-MCP', 'student'],
    ['student1', 'DOCKER-101', 'student'],
    ['teacher1', 'INTRO-MCP', 'editingteacher'],
];
$manual = enrol_get_plugin('manual');
foreach ($enrolments as [$username, $shortname, $rolename]) {
    $role = $DB->get_record('role', ['shortname' => $rolename], '*', MUST_EXIST);
    $instance = $DB->get_record('enrol',
        ['courseid' => $courseids[$shortname], 'enrol' => 'manual'], '*', MUST_EXIST);
    $manual->enrol_user($instance, $userids[$username], $role->id); // idempotent
    say("[ok] $username enrolled in $shortname as $rolename");
}

// ---------- 5. External service + functions ----------
$wsman = new webservice();
$service = $DB->get_record('external_services', ['shortname' => 'mcp_service']);
if (!$service) {
    $serviceid = $wsman->add_external_service((object) [
        'name' => 'MCP Service', 'shortname' => 'mcp_service',
        'enabled' => 1, 'restrictedusers' => 0,
        'downloadfiles' => 1, 'uploadfiles' => 0,
    ]);
    $service = $DB->get_record('external_services', ['id' => $serviceid]);
    say("[ok] external service mcp_service created (id $serviceid)");
} else {
    say("[skip] external service mcp_service exists (id {$service->id})");
}

$functions = [
    'core_webservice_get_site_info',
    // courses & content
    'core_course_get_courses', 'core_course_get_courses_by_field',
    'core_course_get_contents', 'core_course_search_courses',
    'core_course_get_categories', 'core_course_create_courses',
    'core_course_edit_section', 'core_course_get_course_module',
    // enrolment & users
    'core_enrol_get_users_courses', 'core_enrol_get_enrolled_users',
    'enrol_manual_enrol_users', 'core_user_get_users_by_field',
    'core_user_create_users',
    // quiz
    'mod_quiz_get_quizzes_by_courses', 'mod_quiz_get_quiz_access_information',
    'mod_quiz_start_attempt', 'mod_quiz_get_attempt_data',
    'mod_quiz_process_attempt', 'mod_quiz_get_attempt_review',
    'mod_quiz_get_user_attempts', 'mod_quiz_get_user_best_grade',
    'mod_quiz_view_quiz',
    // materials
    'mod_page_get_pages_by_courses', 'mod_resource_get_resources_by_courses',
    // grades & progress
    'gradereport_user_get_grade_items', 'gradereport_overview_get_course_grades',
    'core_completion_get_activities_completion_status',
    'core_completion_get_course_completion_status',
];
$added = 0;
foreach ($functions as $fn) {
    if (!$DB->record_exists('external_functions', ['name' => $fn])) {
        say("[warn] function $fn does not exist in this Moodle — skipped");
        continue;
    }
    if (!$DB->record_exists('external_services_functions',
            ['externalserviceid' => $service->id, 'functionname' => $fn])) {
        $wsman->add_external_function_to_service($fn, $service->id);
        $added++;
    }
}
say("[ok] service functions ensured ($added newly added)");

// ---------- 6. Tokens ----------
$admin = get_admin();
$tokenusers = ['admin' => $admin->id] + $userids;
say('');
say('=== API TOKENS (append to docker/.env — gitignored) ===');
foreach ($tokenusers as $username => $userid) {
    $existing = $DB->get_record('external_tokens',
        ['userid' => $userid, 'externalserviceid' => $service->id]);
    if ($existing) {
        $token = $existing->token;
    } else {
        $token = \core_external\util::generate_token(EXTERNAL_TOKEN_PERMANENT,
            $service, $userid, context_system::instance());
    }
    say('MOODLE_TOKEN_' . strtoupper($username) . '=' . $token);
}
say('=== done ===');
