<?php
/**
 * Phase 4 seed — RBAC prerequisites. Idempotent.
 *
 *   docker compose cp seed/seed_phase4.php moodle:/tmp/
 *   docker compose exec -T moodle php /tmp/seed_phase4.php
 *
 * 1. Adds the web-service functions the creator tools + role gating need.
 * 2. Grants teacher1 the `coursecreator` role at category level — Moodle
 *    roles are contextual: editingteacher (inside a course) cannot create
 *    courses; course creation lives at the category/system level.
 */

define('CLI_SCRIPT', true);
require '/var/www/html/config.php';
require_once $CFG->dirroot . '/webservice/lib.php';

function say($msg) { echo $msg . "\n"; }

// ---------- 1. Additional service functions ----------
$service = $DB->get_record('external_services', ['shortname' => 'mcp_service'], '*', MUST_EXIST);
$wsman = new webservice();
$functions = [
    // capability-derived booleans per course (role gating without role names)
    'core_course_get_user_administration_options',
    // creator tools
    'core_course_update_courses',   // publish/unpublish (visible flag), rename
    'core_course_delete_courses',   // test cleanup + admin-ish tool later
    'core_role_assign_roles',       // creator self-assigns teacher on new courses
];
foreach ($functions as $fn) {
    if (!$DB->record_exists('external_functions', ['name' => $fn])) {
        say("[warn] $fn does not exist in this Moodle — skipped");
        continue;
    }
    if (!$DB->record_exists('external_services_functions',
            ['externalserviceid' => $service->id, 'functionname' => $fn])) {
        $wsman->add_external_function_to_service($fn, $service->id);
        say("[ok] added $fn");
    } else {
        say("[skip] $fn already in service");
    }
}

// ---------- 2. teacher1 -> coursecreator at category level ----------
$teacher = $DB->get_record('user', ['username' => 'teacher1', 'deleted' => 0], '*', MUST_EXIST);
$role = $DB->get_record('role', ['shortname' => 'coursecreator'], '*', MUST_EXIST);
$categoryid = $DB->get_field_sql('SELECT MIN(id) FROM {course_categories}');
$context = context_coursecat::instance($categoryid);

if ($DB->record_exists('role_assignments',
        ['roleid' => $role->id, 'userid' => $teacher->id, 'contextid' => $context->id])) {
    say('[skip] teacher1 already coursecreator in category ' . $categoryid);
} else {
    role_assign($role->id, $teacher->id, $context->id);
    say("[ok] teacher1 granted coursecreator in category $categoryid");
}

// ---------- 3. Let coursecreators enter courses they don't participate in ----------
// The WS create_courses does NOT auto-assign the creator to the new course
// (the web UI does). To self-assign as teacher afterwards they must pass
// require_login on a course they're not enrolled in — which needs these:
$sys = context_system::instance();
foreach (['moodle/course:view', 'moodle/course:viewhiddencourses',
          'moodle/role:assign'] as $cap) {
    assign_capability($cap, CAP_ALLOW, $role->id, $sys->id, true);
    say("[ok] $cap -> coursecreator");
}
// role:assign alone is not enough — the allow-assign matrix also gates
// WHICH roles can be handed out (Site admin → Users → Define roles → Allow
// role assignments). Let coursecreators appoint editingteachers:
$editingteacher = $DB->get_record('role', ['shortname' => 'editingteacher'], '*', MUST_EXIST);
if (!$DB->record_exists('role_allow_assign',
        ['roleid' => $role->id, 'allowassign' => $editingteacher->id])) {
    core_role_set_assign_allowed($role->id, $editingteacher->id);
    say('[ok] allow-assign: coursecreator may assign editingteacher');
}
purge_all_caches();

// ---------- 4. No SMTP in the lab ----------
// Without this, Moodle's attempt to email enrolment notifications throws
// "Message was not sent." INSIDE web-service calls, breaking them.
set_config('noemailever', 1);
say('[ok] noemailever=1');

say('=== phase 4 seed done ===');
