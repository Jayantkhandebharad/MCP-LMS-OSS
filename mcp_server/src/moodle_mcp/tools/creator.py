"""Creator-facing tools: course management for teachers/managers.

These are the tools a learner's client NEVER SEES (gating.py filters the
advertised list per identity) and cannot successfully call either:
1. each tool guards itself with can_manage_courses(), and
2. Moodle's own permission system is the final backstop regardless.
UX, defense in depth, and enforcement — three separate layers on purpose.
"""

from __future__ import annotations

from mcp.server.fastmcp import Context

from moodle_mcp.moodle_client import MoodleAPIError, MoodleClient
from moodle_mcp.server import mcp
from moodle_mcp.tools.learner import _error, _moodle

CREATOR_TOOLS = {"create_course", "publish_course", "enrol_student", "view_course_analytics"}

# Moodle's built-in archetype role ids (stable across stock installs).
STUDENT_ROLE_ID = 5
EDITING_TEACHER_ROLE_ID = 3

_NOT_CREATOR = (
    "Error: this tool requires course-management rights (teacher/manager). "
    "Your current identity can't edit any course. Use whoami to check who "
    "you are connected as."
)


async def _creator_client(ctx: Context) -> MoodleClient | None:
    """The caller's client if they may manage courses, else None."""
    client = _moodle(ctx)
    return client if await client.can_manage_courses() else None


@mcp.tool(
    name="create_course",
    annotations={
        "title": "Create a Course",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def create_course(fullname: str, shortname: str, summary: str, ctx: Context) -> str:
    """Create a new course (teacher/manager only).

    Args:
        fullname: Display name, e.g. "Kubernetes Fundamentals".
        shortname: Unique short code, e.g. "K8S-101" — creation fails if taken.
        summary: One-paragraph course description.

    Returns:
        The new course id and next steps. The course starts hidden — use
        publish_course to make it visible to students.
    """
    client = await _creator_client(ctx)
    if client is None:
        return _NOT_CREATOR
    try:
        categories = await client.call("core_course_get_categories", addsubcategories=0)
        result = await client.call(
            "core_course_create_courses",
            courses=[{
                "fullname": fullname,
                "shortname": shortname,
                "categoryid": categories[0]["id"],
                "summary": summary,
                "summaryformat": 1,
                "format": "topics",
                "visible": 0,
            }],
        )
    except MoodleAPIError as e:
        if e.errorcode == "shortnametaken":
            return f"Error: shortname '{shortname}' is already used by another course. Pick a different one."
        return _error(e)
    course = result[0]

    # The web UI assigns the creator as teacher on new courses; the WS
    # function does NOT (you'd create a course you cannot even open).
    # coursecreator carries moodle/role:assign, so self-assign explicitly.
    try:
        me = await client.my_userid()
        await client.call(
            "core_role_assign_roles",
            assignments=[{
                "roleid": EDITING_TEACHER_ROLE_ID,
                "userid": me,
                "contextlevel": "course",
                "instanceid": course["id"],
            }],
        )
    except MoodleAPIError as e:
        return (
            f"Created course id {course['id']} but could not make you its teacher "
            f"({e.errorcode}) — ask an admin to assign you to it."
        )
    return (
        f"Created course **{fullname}** (id: {course['id']}, shortname: {course['shortname']}), "
        "with you as its teacher. It is currently HIDDEN from students. Enrol people "
        "with enrol_student; make it visible with publish_course when ready."
    )


@mcp.tool(
    name="publish_course",
    annotations={
        "title": "Publish/Hide a Course",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def publish_course(course_id: int, visible: bool, ctx: Context) -> str:
    """Make a course visible to students, or hide it (teacher/manager only).

    Args:
        course_id: Course id (from create_course or list_my_courses).
        visible: True to publish, False to hide.
    """
    client = await _creator_client(ctx)
    if client is None:
        return _NOT_CREATOR
    try:
        result = await client.call(
            "core_course_update_courses",
            courses=[{"id": course_id, "visible": 1 if visible else 0}],
        )
    except MoodleAPIError as e:
        return _error(e)
    warnings = result.get("warnings", [])
    if warnings:
        return f"Error: {warnings[0].get('message', warnings[0])}"
    state = "visible to students" if visible else "hidden from students"
    return f"Course {course_id} is now {state}."


@mcp.tool(
    name="enrol_student",
    annotations={
        "title": "Enrol a Student",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def enrol_student(course_id: int, email: str, ctx: Context) -> str:
    """Enrol an existing user into a course as a student (teacher/manager only).

    Args:
        course_id: Target course id.
        email: The user's email, e.g. "student1@example.com". Email is used
            because Moodle shows teachers other users' emails but NOT their
            usernames.
    """
    client = await _creator_client(ctx)
    if client is None:
        return _NOT_CREATOR
    try:
        user = await _find_user_by_email(client, email)
        if user is None:
            return (
                f"Error: no user with email '{email}' among people you can see. "
                "Teachers can only find users who share a course with them; "
                "ask an admin to enrol someone entirely new."
            )
        await client.call(
            "enrol_manual_enrol_users",
            enrolments=[{
                "roleid": STUDENT_ROLE_ID,
                "userid": user["id"],
                "courseid": course_id,
            }],
        )
    except MoodleAPIError as e:
        return _error(e)
    return f"Enrolled {user['fullname']} ({email}) in course {course_id} as a student."


async def _find_user_by_email(client: MoodleClient, email: str) -> dict | None:
    """Site-wide lookup (admins/managers), else scan the caller's courses.

    Teachers cannot search arbitrary users — core_user_get_users_by_field
    silently filters to nothing — but they CAN see participants (with email)
    of their own courses.
    """
    users = await client.call("core_user_get_users_by_field", field="email", values=[email])
    if users:
        return users[0]
    for course in await client.my_courses():
        participants = await client.call(
            "core_enrol_get_enrolled_users", courseid=course["id"]
        )
        for p in participants:
            if p.get("email", "").lower() == email.lower():
                return p
    return None


@mcp.tool(
    name="view_course_analytics",
    annotations={
        "title": "View Course Analytics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def view_course_analytics(course_id: int, ctx: Context) -> str:
    """Per-student grade overview for a course (teacher/manager only).

    Args:
        course_id: Course id to report on.

    Returns:
        Markdown table: one row per enrolled student with each graded item
        and the course total. (A student calling this sees an error — they
        can only view their own grades via get_my_grades.)
    """
    client = await _creator_client(ctx)
    if client is None:
        return _NOT_CREATOR
    try:
        # No userid => all gradeable users; teachers may, students may not.
        result = await client.call("gradereport_user_get_grade_items", courseid=course_id)
    except MoodleAPIError as e:
        return _error(e)

    usergrades = result["usergrades"]
    if not usergrades:
        return f"No gradeable students in course {course_id}."

    items = [g.get("itemname") or "Course total" for g in usergrades[0]["gradeitems"]]
    lines = [
        f"# Course {course_id} — grades for {len(usergrades)} student(s)",
        "",
        "| Student | " + " | ".join(items) + " |",
        "|---" * (len(items) + 1) + "|",
    ]
    for ug in usergrades:
        grades = [g.get("gradeformatted") or "-" for g in ug["gradeitems"]]
        lines.append(f"| {ug['userfullname']} | " + " | ".join(grades) + " |")
    return "\n".join(lines)