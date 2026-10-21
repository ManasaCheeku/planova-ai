import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


class RecoveryProposalConflict(Exception):
    pass


def _database_path() -> Path:
    configured_path = os.environ.get("PLANOVA_DB_PATH")
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "planova.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('scheduled', 'completed', 'cancelled')),
            plan_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            title TEXT NOT NULL,
            due_date TEXT,
            status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'completed')),
            event_id TEXT REFERENCES events(id) ON DELETE SET NULL,
            description TEXT NOT NULL DEFAULT '',
            priority TEXT NOT NULL DEFAULT 'medium',
            assigned_to TEXT,
            estimated_cost REAL,
            completion_criteria TEXT NOT NULL DEFAULT '',
            dependencies_json TEXT NOT NULL DEFAULT '[]',
            generated INTEGER NOT NULL DEFAULT 0,
            autopilot_key TEXT
        );
        CREATE TABLE IF NOT EXISTS recovery_cases (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            disruption_type TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('open', 'resolved')),
            resolved_at TEXT,
            resolution TEXT,
            impact_json TEXT NOT NULL,
            options_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS recovery_proposals (
            id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL REFERENCES recovery_cases(id) ON DELETE CASCADE,
            event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            option_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('proposed', 'approved', 'rejected', 'applied', 'failed')),
            proposed_change_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            result_json TEXT
        );
        CREATE TABLE IF NOT EXISTS recovery_activity (
            id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL REFERENCES recovery_cases(id) ON DELETE CASCADE,
            proposal_id TEXT REFERENCES recovery_proposals(id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ai_conversations (
            id TEXT PRIMARY KEY,
            turns_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS event_expenses (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            idempotency_key TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            category TEXT NOT NULL,
            amount TEXT NOT NULL,
            expense_date TEXT NOT NULL,
            description TEXT NOT NULL,
            payment_status TEXT NOT NULL CHECK (payment_status IN ('committed', 'paid')),
            vendor_name TEXT,
            UNIQUE (event_id, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS idx_event_expenses_event_date
            ON event_expenses(event_id, expense_date, created_at);
        CREATE TABLE IF NOT EXISTS budget_proposals (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('proposed', 'applied', 'rejected')),
            rationale TEXT NOT NULL,
            proposed_changes_json TEXT NOT NULL,
            preview_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            result_json TEXT,
            UNIQUE (event_id, idempotency_key)
        );
        CREATE TABLE IF NOT EXISTS guests (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            group_name TEXT,
            party_size INTEGER NOT NULL CHECK (party_size >= 1 AND party_size <= 100),
            notes TEXT,
            dietary_requirements_json TEXT NOT NULL DEFAULT '[]',
            accessibility_requirements_json TEXT NOT NULL DEFAULT '[]',
            accommodation_requirements_json TEXT NOT NULL DEFAULT '[]',
            invitation_status TEXT NOT NULL CHECK (invitation_status IN ('not_prepared', 'drafted', 'queued', 'sent', 'delivered', 'failed')),
            rsvp_status TEXT NOT NULL CHECK (rsvp_status IN ('awaiting_response', 'attending', 'not_attending')),
            rsvp_party_size INTEGER,
            duplicate_of_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_guests_event_name
            ON guests(event_id, name COLLATE NOCASE, created_at);
        CREATE INDEX IF NOT EXISTS idx_guests_event_email
            ON guests(event_id, email) WHERE email IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_guests_event_phone
            ON guests(event_id, phone) WHERE phone IS NOT NULL;
        CREATE TABLE IF NOT EXISTS invitation_drafts (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('invitation', 'reminder')),
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            tone TEXT NOT NULL CHECK (tone IN ('formal', 'friendly', 'celebratory', 'professional')),
            language TEXT NOT NULL,
            group_name TEXT,
            rsvp_deadline TEXT,
            generated_by TEXT NOT NULL CHECK (generated_by IN ('manual', 'genai', 'deterministic')),
            missing_information_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_invitation_drafts_event_created
            ON invitation_drafts(event_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS rsvp_activity (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            guest_id TEXT NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            source TEXT NOT NULL,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_rsvp_activity_guest_created
            ON rsvp_activity(guest_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS delivery_batches (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            draft_id TEXT NOT NULL REFERENCES invitation_drafts(id) ON DELETE RESTRICT,
            kind TEXT NOT NULL CHECK (kind IN ('invitation', 'reminder')),
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft_only', 'completed', 'partial_failed', 'failed', 'unknown', 'cancelled')),
            delivery_mode TEXT NOT NULL CHECK (delivery_mode IN ('smtp', 'draft_only')),
            approved_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (event_id, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS idx_delivery_batches_event_created
            ON delivery_batches(event_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS delivery_attempts (
            id TEXT PRIMARY KEY,
            batch_id TEXT REFERENCES delivery_batches(id) ON DELETE SET NULL,
            event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            guest_id TEXT NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
            draft_id TEXT NOT NULL REFERENCES invitation_drafts(id) ON DELETE RESTRICT,
            channel TEXT NOT NULL CHECK (channel IN ('email')),
            status TEXT NOT NULL CHECK (status IN ('draft_only', 'queued', 'sent', 'delivered', 'failed', 'unknown', 'cancelled')),
            recipient_address TEXT NOT NULL,
            provider_message_id TEXT,
            transport_message_id TEXT,
            error_message TEXT,
            retry_of_id TEXT REFERENCES delivery_attempts(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            sent_at TEXT,
            delivered_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_delivery_attempts_event_guest
            ON delivery_attempts(event_id, guest_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_delivery_attempts_draft_guest
            ON delivery_attempts(draft_id, guest_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS reminder_preparations (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            draft_id TEXT NOT NULL REFERENCES invitation_drafts(id) ON DELETE CASCADE,
            guest_ids_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('prepared', 'sent', 'cancelled')),
            delivery_batch_id TEXT REFERENCES delivery_batches(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reminder_preparations_event_created
            ON reminder_preparations(event_id, created_at DESC);

        
CREATE TABLE IF NOT EXISTS vendors (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    contact_name TEXT,
    contact_email TEXT,
    contact_phone TEXT,
    notes TEXT,
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_vendors_event
ON vendors(event_id);

CREATE TABLE IF NOT EXISTS vendor_quotes (
    id TEXT PRIMARY KEY,
    vendor_id TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    valid_until TEXT,
    includes TEXT NOT NULL DEFAULT '[]',
    excludes TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'quoted'
        CHECK (status IN ('quoted', 'accepted', 'rejected')),
    FOREIGN KEY (vendor_id) REFERENCES vendors(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_vendor_quotes_vendor
ON vendor_quotes(vendor_id);

        """
        
    )
    task_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(tasks)")
    }
    migrations = {
        "description": "ALTER TABLE tasks ADD COLUMN description TEXT NOT NULL DEFAULT ''",
        "priority": "ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'",
        "assigned_to": "ALTER TABLE tasks ADD COLUMN assigned_to TEXT",
        "estimated_cost": "ALTER TABLE tasks ADD COLUMN estimated_cost REAL",
        "completion_criteria": "ALTER TABLE tasks ADD COLUMN completion_criteria TEXT NOT NULL DEFAULT ''",
        "dependencies_json": "ALTER TABLE tasks ADD COLUMN dependencies_json TEXT NOT NULL DEFAULT '[]'",
        "generated": "ALTER TABLE tasks ADD COLUMN generated INTEGER NOT NULL DEFAULT 0",
        "autopilot_key": "ALTER TABLE tasks ADD COLUMN autopilot_key TEXT",
    }
    for column, statement in migrations.items():
        if column not in task_columns:
            connection.execute(statement)
    task_schema = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'tasks'"
    ).fetchone()
    if task_schema and "'in_progress'" not in task_schema["sql"]:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE tasks_prompt8 ("
            "id TEXT PRIMARY KEY, created_at TEXT NOT NULL, title TEXT NOT NULL, "
            "due_date TEXT, status TEXT NOT NULL CHECK "
            "(status IN ('pending', 'in_progress', 'completed')), "
            "event_id TEXT REFERENCES events(id) ON DELETE SET NULL, "
            "description TEXT NOT NULL DEFAULT '', priority TEXT NOT NULL DEFAULT 'medium', "
            "assigned_to TEXT, estimated_cost REAL, "
            "completion_criteria TEXT NOT NULL DEFAULT '', "
            "dependencies_json TEXT NOT NULL DEFAULT '[]', generated INTEGER NOT NULL DEFAULT 0, "
            "autopilot_key TEXT)"
        )
        connection.execute(
            "INSERT INTO tasks_prompt8 (id, created_at, title, due_date, status, event_id, "
            "description, priority, assigned_to, estimated_cost, completion_criteria, "
            "dependencies_json, generated, autopilot_key) "
            "SELECT id, created_at, title, due_date, status, event_id, description, priority, "
            "assigned_to, estimated_cost, completion_criteria, dependencies_json, generated, "
            "autopilot_key FROM tasks"
        )
        connection.execute("DROP TABLE tasks")
        connection.execute("ALTER TABLE tasks_prompt8 RENAME TO tasks")
    recovery_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(recovery_cases)")
    }
    if "resolved_at" not in recovery_columns:
        connection.execute("ALTER TABLE recovery_cases ADD COLUMN resolved_at TEXT")
    if "resolution" not in recovery_columns:
        connection.execute("ALTER TABLE recovery_cases ADD COLUMN resolution TEXT")
    budget_proposal_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(budget_proposals)")
    }
    if "preview_json" not in budget_proposal_columns:
        connection.execute(
            "ALTER TABLE budget_proposals ADD COLUMN preview_json TEXT NOT NULL DEFAULT '{}'"
        )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_autopilot_key "
        "ON tasks(event_id, autopilot_key) WHERE autopilot_key IS NOT NULL"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_recovery_proposal_once "
        "ON recovery_proposals(case_id, option_id) "
        "WHERE status IN ('proposed', 'approved', 'applied')"
    )
    connection.commit()
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_ai_conversation(conversation_id: str) -> list[dict[str, str]] | None:
    with closing(_connect()) as connection, connection:
        connection.execute(
            "DELETE FROM ai_conversations "
            "WHERE julianday(updated_at) < julianday('now', '-30 days')"
        )
        row = connection.execute(
            "SELECT turns_json FROM ai_conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
    return json.loads(row["turns_json"]) if row else None


def save_ai_conversation(
    conversation_id: str, turns: list[dict[str, str]]
) -> None:
    with closing(_connect()) as connection, connection:
        connection.execute(
            "INSERT INTO ai_conversations (id, turns_json, updated_at) "
            "VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "turns_json = excluded.turns_json, updated_at = excluded.updated_at",
            (
                conversation_id,
                json.dumps(turns[-12:], ensure_ascii=False),
                _now(),
            ),
        )


def save_event(plan: dict[str, Any]) -> dict[str, Any]:
    event_id = str(uuid.uuid4())
    created_at = _now()
    stored_plan = {**plan, "event_id": event_id, "created_at": created_at}
    with closing(_connect()) as connection, connection:
        connection.execute(
            "INSERT INTO events (id, created_at, status, plan_json) VALUES (?, ?, 'scheduled', ?)",
            (
                event_id,
                created_at,
                json.dumps(stored_plan, separators=(",", ":"), ensure_ascii=False),
            ),
        )
    return stored_plan


def load_dashboard_records() -> dict[str, list[dict[str, Any]]]:
    with closing(_connect()) as connection, connection:
        event_rows = connection.execute(
            "SELECT id, created_at, status, plan_json FROM events ORDER BY created_at DESC"
        ).fetchall()
        task_rows = connection.execute(
            "SELECT id, created_at, title, due_date, status, event_id, description, priority, "
            "assigned_to, estimated_cost, completion_criteria, dependencies_json, generated "
            "FROM tasks ORDER BY "
            "CASE status WHEN 'pending' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END, "
            "due_date, created_at DESC"
        ).fetchall()

    return {
        "events": [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "status": row["status"],
                "plan": json.loads(row["plan_json"]),
            }
            for row in event_rows
        ],
        "tasks": [
            {
                **dict(row),
                "dependencies": json.loads(row["dependencies_json"]),
                "generated": bool(row["generated"]),
            }
            for row in task_rows
        ],
    }


def load_event(event_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT id, created_at, status, plan_json FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "status": row["status"],
        "plan": json.loads(row["plan_json"]),
    }


def event_exists(event_id: str) -> bool:
    with closing(_connect()) as connection, connection:
        row = connection.execute("SELECT 1 FROM events WHERE id = ?", (event_id,)).fetchone()
    return row is not None


def create_task(
    title: str,
    due_date: date | None,
    event_id: str | None,
    *,
    description: str = "",
    priority: str = "medium",
    assigned_to: str | None = None,
    estimated_cost: float | None = None,
    completion_criteria: str = "",
    dependencies: list[str] | None = None,
    generated: bool = False,
    autopilot_key: str | None = None,
) -> dict[str, Any]:
    task = {
        "id": str(uuid.uuid4()),
        "created_at": _now(),
        "title": title,
        "due_date": due_date.isoformat() if due_date else None,
        "status": "pending",
        "event_id": event_id,
        "description": description,
        "priority": priority,
        "assigned_to": assigned_to,
        "estimated_cost": estimated_cost,
        "completion_criteria": completion_criteria,
        "dependencies_json": json.dumps(dependencies or []),
        "generated": int(generated),
        "autopilot_key": autopilot_key,
    }
    with closing(_connect()) as connection, connection:
        _validate_task_dependencies(
            connection, event_id, dependencies or [], task["id"]
        )
        connection.execute(
            "INSERT OR IGNORE INTO tasks (id, created_at, title, due_date, status, event_id, "
            "description, priority, assigned_to, estimated_cost, completion_criteria, "
            "dependencies_json, generated, autopilot_key) VALUES (:id, :created_at, :title, "
            ":due_date, :status, :event_id, :description, :priority, :assigned_to, "
            ":estimated_cost, :completion_criteria, :dependencies_json, :generated, :autopilot_key)",
            task,
        )
        row = connection.execute(
            "SELECT id, created_at, title, due_date, status, event_id, description, priority, "
            "assigned_to, estimated_cost, completion_criteria, dependencies_json, generated "
            "FROM tasks WHERE id = ? OR (event_id = ? AND autopilot_key = ?)",
            (task["id"], event_id, autopilot_key),
        ).fetchone()
    return _task_dict(row)


def _task_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["dependencies"] = json.loads(result.pop("dependencies_json"))
    result["generated"] = bool(result["generated"])
    return result


def _validate_task_dependencies(
    connection: sqlite3.Connection,
    event_id: str | None,
    dependencies: list[str],
    task_id: str,
) -> None:
    if task_id in dependencies:
        raise ValueError("A task cannot depend on itself.")
    if len(dependencies) != len(set(dependencies)):
        raise ValueError("Task dependencies must be unique.")
    for dependency_id in dependencies:
        dependency = connection.execute(
            "SELECT id, event_id FROM tasks WHERE id = ?", (dependency_id,)
        ).fetchone()
        if dependency is None:
            raise ValueError(f"Dependency task {dependency_id} was not found.")
        if dependency["event_id"] != event_id:
            raise ValueError("Task dependencies must belong to the same event.")

    graph = {
        row["id"]: json.loads(row["dependencies_json"])
        for row in connection.execute(
            "SELECT id, dependencies_json FROM tasks WHERE event_id IS ?",
            (event_id,),
        ).fetchall()
    }
    graph[task_id] = dependencies
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(current: str) -> None:
        if current in visiting:
            raise ValueError("Task dependencies cannot contain a cycle.")
        if current in visited:
            return
        visiting.add(current)
        for child in graph.get(current, []):
            visit(child)
        visiting.remove(current)
        visited.add(current)

    visit(task_id)


def update_task_record(task_id: str, changes: dict[str, Any]) -> bool:
    allowed_fields = {
        "title",
        "due_date",
        "status",
        "description",
        "priority",
        "assigned_to",
        "estimated_cost",
        "completion_criteria",
        "dependencies",
    }
    changes = {key: value for key, value in changes.items() if key in allowed_fields}
    if not changes:
        raise ValueError("provide at least one task field to update")
    if "due_date" in changes and isinstance(changes["due_date"], date):
        changes["due_date"] = changes["due_date"].isoformat()
    if "dependencies" in changes:
        changes["dependencies_json"] = json.dumps(changes.pop("dependencies"))
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, event_id, status, dependencies_json FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            return False
        next_status = changes.get("status", row["status"])
        next_dependencies = changes.get(
            "dependencies_json", row["dependencies_json"]
        )
        dependency_ids = json.loads(next_dependencies)
        _validate_task_dependencies(
            connection, row["event_id"], dependency_ids, task_id
        )
        if next_status in {"in_progress", "completed"}:
            for dependency_id in dependency_ids:
                dependency = connection.execute(
                    "SELECT status FROM tasks WHERE id = ?", (dependency_id,)
                ).fetchone()
                if dependency is None or dependency["status"] != "completed":
                    raise ValueError(
                        "Complete the task's dependencies before starting or completing it."
                    )
        if row["status"] == "completed" and next_status != "completed":
            dependent_rows = connection.execute(
                "SELECT id, title, status, dependencies_json FROM tasks WHERE event_id IS ?",
                (row["event_id"],),
            ).fetchall()
            for dependent in dependent_rows:
                if (
                    dependent["status"] == "completed"
                    and task_id in json.loads(dependent["dependencies_json"])
                ):
                    raise ValueError(
                        f"Reopen dependent task '{dependent['title']}' before reopening this task."
                    )
        cursor = connection.execute(
            "UPDATE tasks SET "
            + ", ".join(f"{field} = :{field}" for field in changes)
            + " WHERE id = :task_id",
            {**changes, "task_id": task_id},
        )
    return cursor.rowcount > 0


def ensure_workflow_tasks(
    event_id: str, event_date: date | None, templates: tuple[dict[str, Any], ...]
) -> None:
    with closing(_connect()) as connection, connection:
        key_to_id: dict[str, str] = {}
        for template in templates:
            key = template["key"]
            due_date = (
                (event_date + timedelta(days=template["offset"])).isoformat()
                if event_date
                else None
            )
            connection.execute(
                "INSERT OR IGNORE INTO tasks (id, created_at, title, due_date, status, event_id, "
                "description, priority, estimated_cost, completion_criteria, generated, autopilot_key) "
                "VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, 1, ?)",
                (
                    str(uuid.uuid4()),
                    _now(),
                    template["title"],
                    due_date,
                    event_id,
                    template["description"],
                    template["priority"],
                    template["estimated_cost"],
                    template["criteria"],
                    key,
                ),
            )
            row = connection.execute(
                "SELECT id FROM tasks WHERE event_id = ? AND autopilot_key = ?",
                (event_id, key),
            ).fetchone()
            key_to_id[key] = row["id"]

        for template in templates:
            dependency_ids = [
                key_to_id[key] for key in template["dependencies"]
            ]
            due_date = (
                (event_date + timedelta(days=template["offset"])).isoformat()
                if event_date
                else None
            )
            connection.execute(
                "UPDATE tasks SET due_date = ?, estimated_cost = ?, dependencies_json = ? "
                "WHERE event_id = ? AND autopilot_key = ? AND generated = 1",
                (
                    due_date,
                    template["estimated_cost"],
                    json.dumps(dependency_ids),
                    event_id,
                    template["key"],
                ),
            )


def load_task(task_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT id, created_at, title, due_date, status, event_id, description, priority, "
            "assigned_to, estimated_cost, completion_criteria, dependencies_json, generated "
            "FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    return _task_dict(row) if row else None


def create_recovery_case(case: dict[str, Any]) -> dict[str, Any]:
    with closing(_connect()) as connection, connection:
        connection.execute(
            "INSERT INTO recovery_cases (id, event_id, created_at, source, disruption_type, "
            "description, status, resolved_at, resolution, impact_json, options_json) "
            "VALUES (:id, :event_id, :created_at, :source, :disruption_type, :description, "
            ":status, NULL, NULL, :impact_json, :options_json)",
            {
                **case,
                "impact_json": json.dumps(case["impact"], ensure_ascii=False),
                "options_json": json.dumps(case["options"], ensure_ascii=False),
            },
        )
        connection.execute(
            "INSERT INTO recovery_activity (id, case_id, action, status, details, created_at) "
            "VALUES (?, ?, 'disruption_reported', 'recorded', ?, ?)",
            (
                str(uuid.uuid4()),
                case["id"],
                case["description"],
                case["created_at"],
            ),
        )
    return case


def resolve_recovery_case(case_id: str, summary: str) -> dict[str, Any] | None:
    now = _now()
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT status FROM recovery_cases WHERE id = ?", (case_id,)
        ).fetchone()
        if row is None:
            return None
        if row["status"] != "open":
            raise ValueError("The recovery case is already resolved.")
        pending = connection.execute(
            "SELECT 1 FROM recovery_proposals WHERE case_id = ? AND status = 'proposed' LIMIT 1",
            (case_id,),
        ).fetchone()
        if pending:
            raise ValueError("Decide all pending proposals before resolving this case.")
        connection.execute(
            "UPDATE recovery_cases SET status = 'resolved', resolved_at = ?, resolution = ? "
            "WHERE id = ? AND status = 'open'",
            (now, summary, case_id),
        )
        connection.execute(
            "INSERT INTO recovery_activity (id, case_id, action, status, details, created_at) "
            "VALUES (?, ?, 'case_resolved', 'resolved', ?, ?)",
            (str(uuid.uuid4()), case_id, summary, now),
        )
    return load_recovery_case(case_id)


def load_recovery_case(case_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT * FROM recovery_cases WHERE id = ?", (case_id,)
        ).fetchone()
        activity_rows = connection.execute(
            "SELECT id, proposal_id, action, status, details, created_at "
            "FROM recovery_activity WHERE case_id = ? ORDER BY created_at, id",
            (case_id,),
        ).fetchall()
        proposal_rows = connection.execute(
            "SELECT * FROM recovery_proposals WHERE case_id = ? ORDER BY created_at",
            (case_id,),
        ).fetchall()
    if row is None:
        return None
    return {
        **dict(row),
        "impact": json.loads(row["impact_json"]),
        "options": json.loads(row["options_json"]),
        "activity": [dict(item) for item in activity_rows],
        "proposals": [
            {
                **dict(item),
                "proposed_change": json.loads(item["proposed_change_json"]),
                "result": json.loads(item["result_json"]) if item["result_json"] else None,
            }
            for item in proposal_rows
        ],
    }


def list_recovery_cases(event_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT id FROM recovery_cases WHERE event_id = ? ORDER BY created_at DESC",
            (event_id,),
        ).fetchall()
    return [case for row in rows if (case := load_recovery_case(row["id"])) is not None]


def create_recovery_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    now = proposal["created_at"]
    try:
        with closing(_connect()) as connection, connection:
            connection.execute(
                "INSERT INTO recovery_proposals (id, case_id, event_id, option_id, status, "
                "proposed_change_json, created_at, updated_at) "
                "VALUES (:id, :case_id, :event_id, :option_id, 'proposed', :proposed_change_json, "
                ":created_at, :updated_at)",
                {
                    **proposal,
                    "proposed_change_json": json.dumps(
                        proposal["proposed_change"], ensure_ascii=False
                    ),
                    "updated_at": now,
                },
            )
            connection.execute(
                "INSERT INTO recovery_activity (id, case_id, proposal_id, action, status, details, created_at) "
                "VALUES (?, ?, ?, 'proposal_created', 'awaiting_approval', ?, ?)",
                (
                    str(uuid.uuid4()),
                    proposal["case_id"],
                    proposal["id"],
                    f"Option {proposal['option_id']} proposed for review.",
                    now,
                ),
            )
    except sqlite3.IntegrityError as error:
        raise RecoveryProposalConflict(
            "This recovery option already has a pending or applied proposal."
        ) from error
    case = load_recovery_case(proposal["case_id"])
    if case is None:
        raise RuntimeError("The recovery case disappeared after proposal creation.")
    created = next(
        (item for item in case["proposals"] if item["id"] == proposal["id"]),
        None,
    )
    if created is None:
        raise RuntimeError("The saved recovery proposal could not be reloaded.")
    return created


def decide_recovery_proposal(
    proposal_id: str, decision: str
) -> dict[str, Any] | None:
    now = _now()
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM recovery_proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
        if row is None:
            return None
        if row["status"] != "proposed":
            raise ValueError(f"Proposal is already {row['status']}.")
        new_status = "rejected" if decision == "reject" else "approved"
        cursor = connection.execute(
            "UPDATE recovery_proposals SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, proposal_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("Proposal was already processed.")
        result: dict[str, Any] = {}
        if decision == "approve":
            change = json.loads(row["proposed_change_json"])
            event_row = connection.execute(
                "SELECT plan_json FROM events WHERE id = ?", (row["event_id"],)
            ).fetchone()
            if event_row is None:
                raise ValueError("The saved event no longer exists.")
            current_plan = json.loads(event_row["plan_json"])
            if change:
                event_plan = current_plan
                event = event_plan["event"]
                for field, value in change.items():
                    if field == "estimated_costs":
                        event[field].update(value)
                    else:
                        event[field] = value
                from backend.app.schemas.events import EventCreate
                from backend.app.services.event_planner import build_event_plan

                updated_plan = build_event_plan(EventCreate.model_validate(event))
                updated_plan["event_id"] = row["event_id"]
                updated_plan["created_at"] = event_plan.get("created_at")
                connection.execute(
                    "UPDATE events SET plan_json = ? WHERE id = ?",
                    (
                        json.dumps(updated_plan, separators=(",", ":"), ensure_ascii=False),
                        row["event_id"],
                    ),
                )
                current_plan = updated_plan
                task_offsets = {
                    "confirm_event_date": -30,
                    "confirm_guest_count": -21,
                    "verify_venue": -28,
                    "finalize_requirements": -21,
                    "collect_estimates": -14,
                    "confirm_catering": -7,
                    "send_invitations": -14,
                    "final_readiness_review": -2,
                }
                cost_categories = {
                    "verify_venue": "venue",
                    "confirm_catering": "catering",
                }
                event_date = (
                    date.fromisoformat(event["event_date"])
                    if event.get("event_date")
                    else None
                )
                for key, offset in task_offsets.items():
                    due_date = (
                        (event_date + timedelta(days=offset)).isoformat()
                        if event_date
                        else None
                    )
                    category = cost_categories.get(key)
                    estimated_cost = (
                        event.get("estimated_costs", {}).get(category)
                        if category
                        else None
                    )
                    connection.execute(
                        "UPDATE tasks SET due_date = ?, estimated_cost = ? "
                        "WHERE event_id = ? AND autopilot_key = ? AND generated = 1",
                        (due_date, estimated_cost, row["event_id"], key),
                    )
            result = {
                "event_id": row["event_id"],
                "applied_changes": change,
                "remaining_blockers": [
                    {
                        "title": risk["title"],
                        "reason": risk["reason"],
                        "severity": risk["severity"],
                    }
                    for risk in current_plan.get("risks", [])
                ],
                "external_actions_executed": [],
                "message": (
                    "The approved changes were applied to the local event plan."
                    if change
                    else "The recommendation was recorded locally; no event fields or external systems changed."
                ),
            }
            result_status = "applied" if change else "approved"
            connection.execute(
                "UPDATE recovery_proposals SET status = ?, updated_at = ?, "
                "result_json = ? WHERE id = ?",
                (
                    result_status,
                    now,
                    json.dumps(result, ensure_ascii=False),
                    proposal_id,
                ),
            )
        connection.execute(
            "INSERT INTO recovery_activity (id, case_id, proposal_id, action, status, details, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                row["case_id"],
                proposal_id,
                (
                    "approved_and_applied"
                    if result.get("applied_changes")
                    else "recommendation_approved"
                )
                if decision == "approve"
                else "rejected",
                result_status if decision == "approve" else "rejected",
                result["message"] if decision == "approve" else "Proposal rejected; no event or external system was changed.",
                now,
            ),
        )
        result_row = connection.execute(
            "SELECT * FROM recovery_proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
    return {
        **dict(result_row),
        "proposed_change": json.loads(result_row["proposed_change_json"]),
        "result": json.loads(result_row["result_json"]) if result_row["result_json"] else None,
    }


def update_task_status(task_id: str, status: str) -> bool:
    return update_task_record(task_id, {"status": status})


def update_event_status(event_id: str, status: str) -> bool:
    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            "UPDATE events SET status = ? WHERE id = ?", (status, event_id)
        )
    return cursor.rowcount > 0


def list_event_expenses(event_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM event_expenses WHERE event_id = ? "
            "ORDER BY expense_date DESC, created_at DESC, id DESC",
            (event_id,),
        ).fetchall()
    return [_expense_dict(row) for row in rows]


def _expense_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["amount"] = float(Decimal(result["amount"]))
    return result


def create_event_expense(
    event_id: str, expense: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    now = _now()
    expense_id = str(uuid.uuid4())
    serialized_amount = str(
        Decimal(str(expense["amount"])).quantize(Decimal("0.01"))
    )
    values = {
        **expense,
        "id": expense_id,
        "event_id": event_id,
        "created_at": now,
        "updated_at": now,
        "amount": serialized_amount,
    }
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT * FROM event_expenses WHERE event_id = ? AND idempotency_key = ?",
            (event_id, expense["idempotency_key"]),
        ).fetchone()
        if existing:
            stored = _expense_dict(existing)
            matches = all(
                str(stored[field]) == str(values[field])
                for field in (
                    "category",
                    "expense_date",
                    "description",
                    "payment_status",
                    "vendor_name",
                )
            ) and Decimal(str(stored["amount"])) == Decimal(str(values["amount"]))
            if not matches:
                raise ValueError("The idempotency key was already used for another expense.")
            return stored, False
        connection.execute(
            "INSERT INTO event_expenses (id, event_id, idempotency_key, created_at, "
            "updated_at, category, amount, expense_date, description, payment_status, "
            "vendor_name) VALUES (:id, :event_id, :idempotency_key, :created_at, "
            ":updated_at, :category, :amount, :expense_date, :description, "
            ":payment_status, :vendor_name)",
            values,
        )
        row = connection.execute(
            "SELECT * FROM event_expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    return _expense_dict(row), True


def update_event_expense(
    event_id: str, expense_id: str, changes: dict[str, Any]
) -> dict[str, Any] | None:
    if not changes:
        raise ValueError("provide at least one expense field to update")
    changes = dict(changes)
    if "amount" in changes:
        changes["amount"] = str(
            Decimal(str(changes["amount"])).quantize(Decimal("0.01"))
        )
    changes["updated_at"] = _now()
    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            "UPDATE event_expenses SET "
            + ", ".join(f"{field} = :{field}" for field in changes)
            + " WHERE event_id = :event_id AND id = :id",
            {**changes, "event_id": event_id, "id": expense_id},
        )
        if cursor.rowcount != 1:
            return None
        row = connection.execute(
            "SELECT * FROM event_expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    return _expense_dict(row)


def list_budget_proposals(event_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM budget_proposals WHERE event_id = ? ORDER BY created_at DESC",
            (event_id,),
        ).fetchall()
    return [_budget_proposal_dict(row) for row in rows]


def _budget_proposal_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["proposed_changes"] = json.loads(result.pop("proposed_changes_json"))
    result["preview"] = json.loads(result.pop("preview_json") or "{}")
    result["result"] = json.loads(result["result_json"]) if result["result_json"] else None
    result.pop("result_json", None)
    return result


def create_budget_proposal(
    proposal: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    now = _now()
    proposal_id = str(uuid.uuid4())
    values = {
        **proposal,
        "id": proposal_id,
        "status": "proposed",
        "created_at": now,
        "updated_at": now,
        "proposed_changes_json": json.dumps(
            proposal["proposed_changes"], ensure_ascii=False
        ),
        "preview_json": json.dumps(proposal["preview"], ensure_ascii=False),
    }
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT * FROM budget_proposals WHERE event_id = ? AND idempotency_key = ?",
            (proposal["event_id"], proposal["idempotency_key"]),
        ).fetchone()
        if existing:
            stored = _budget_proposal_dict(existing)
            if (
                stored["proposed_changes"] != proposal["proposed_changes"]
                or stored["rationale"] != proposal["rationale"]
            ):
                raise ValueError("The idempotency key was already used for another proposal.")
            return stored, False
        connection.execute(
            "INSERT INTO budget_proposals (id, event_id, idempotency_key, status, rationale, "
            "proposed_changes_json, preview_json, created_at, updated_at) VALUES (:id, :event_id, "
            ":idempotency_key, :status, :rationale, :proposed_changes_json, "
            ":preview_json, :created_at, :updated_at)",
            values,
        )
        row = connection.execute(
            "SELECT * FROM budget_proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
    return _budget_proposal_dict(row), True


def decide_budget_proposal(
    proposal_id: str, decision: str
) -> dict[str, Any] | None:
    now = _now()
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM budget_proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
        if row is None:
            return None
        if row["status"] != "proposed":
            raise ValueError(f"Budget proposal is already {row['status']}.")
        if decision == "reject":
            connection.execute(
                "UPDATE budget_proposals SET status = 'rejected', updated_at = ? WHERE id = ?",
                (now, proposal_id),
            )
        else:
            event_row = connection.execute(
                "SELECT plan_json FROM events WHERE id = ?", (row["event_id"],)
            ).fetchone()
            if event_row is None:
                raise ValueError("The saved event no longer exists.")
            plan = json.loads(event_row["plan_json"])
            event_data = plan["event"]
            changes = json.loads(row["proposed_changes_json"])
            for field, value in changes.items():
                if field in {"estimated_costs", "category_allocations"}:
                    event_data[field] = {**event_data.get(field, {}), **value}
                else:
                    event_data[field] = value
            from backend.app.schemas.events import EventCreate
            from backend.app.services.event_planner import build_event_plan

            updated_plan = build_event_plan(EventCreate.model_validate(event_data))
            updated_plan["event_id"] = row["event_id"]
            updated_plan["created_at"] = plan.get("created_at")
            connection.execute(
                "UPDATE events SET plan_json = ? WHERE id = ?",
                (
                    json.dumps(updated_plan, separators=(",", ":"), ensure_ascii=False),
                    row["event_id"],
                ),
            )
            connection.execute(
                "UPDATE budget_proposals SET status = 'applied', updated_at = ?, "
                "result_json = ? WHERE id = ?",
                (
                    now,
                    json.dumps(
                        {
                            "message": "The approved budget-plan change was applied locally.",
                            "updated_budget": updated_plan["budget_analysis"]["budget"],
                            "currency": updated_plan["budget_analysis"]["currency"],
                            "remaining_risks": updated_plan["risks"],
                        },
                        ensure_ascii=False,
                    ),
                    proposal_id,
                ),
            )
        result = connection.execute(
            "SELECT * FROM budget_proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
    return _budget_proposal_dict(result)


# Smart Invitations & RSVP persistence.  These helpers intentionally live beside the
# existing dashboard store so all event-bound data shares the same SQLite lifecycle and
# foreign-key protections.
def _guest_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    for column, target in (
        ("dietary_requirements_json", "dietary_requirements"),
        ("accessibility_requirements_json", "accessibility_requirements"),
        ("accommodation_requirements_json", "accommodation_requirements"),
    ):
        result[target] = json.loads(result.pop(column) or "[]")
    return result


def list_event_guests(event_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM guests WHERE event_id = ? "
            "ORDER BY name COLLATE NOCASE, created_at, id",
            (event_id,),
        ).fetchall()
    return [_guest_dict(row) for row in rows]


def load_event_guest(event_id: str, guest_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT * FROM guests WHERE event_id = ? AND id = ?",
            (event_id, guest_id),
        ).fetchone()
    return _guest_dict(row) if row else None


def create_event_guest(event_id: str, guest: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    values = {
        **guest,
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "created_at": now,
        "updated_at": now,
        "dietary_requirements_json": json.dumps(
            guest.get("dietary_requirements", []), ensure_ascii=False
        ),
        "accessibility_requirements_json": json.dumps(
            guest.get("accessibility_requirements", []), ensure_ascii=False
        ),
        "accommodation_requirements_json": json.dumps(
            guest.get("accommodation_requirements", []), ensure_ascii=False
        ),
        "duplicate_of_id": guest.get("duplicate_of_id"),
    }
    with closing(_connect()) as connection, connection:
        connection.execute(
            "INSERT INTO guests (id, event_id, created_at, updated_at, name, email, phone, "
            "group_name, party_size, notes, dietary_requirements_json, "
            "accessibility_requirements_json, accommodation_requirements_json, "
            "invitation_status, rsvp_status, rsvp_party_size, duplicate_of_id) VALUES "
            "(:id, :event_id, :created_at, :updated_at, :name, :email, :phone, "
            ":group_name, :party_size, :notes, :dietary_requirements_json, "
            ":accessibility_requirements_json, :accommodation_requirements_json, "
            ":invitation_status, :rsvp_status, :rsvp_party_size, :duplicate_of_id)",
            values,
        )
        connection.execute(
            "INSERT INTO rsvp_activity (id, event_id, guest_id, action, source, details_json, created_at) "
            "VALUES (?, ?, ?, 'guest_created', 'host', ?, ?)",
            (
                str(uuid.uuid4()),
                event_id,
                values["id"],
                json.dumps({"rsvp_status": values["rsvp_status"]}, ensure_ascii=False),
                now,
            ),
        )
        row = connection.execute("SELECT * FROM guests WHERE id = ?", (values["id"],)).fetchone()
    return _guest_dict(row)


def update_event_guest(
    event_id: str, guest_id: str, changes: dict[str, Any]
) -> dict[str, Any] | None:
    if not changes:
        raise ValueError("provide at least one guest field to update")
    values = dict(changes)
    json_columns = {
        "dietary_requirements": "dietary_requirements_json",
        "accessibility_requirements": "accessibility_requirements_json",
        "accommodation_requirements": "accommodation_requirements_json",
    }
    for field, column in json_columns.items():
        if field in values:
            values[column] = json.dumps(values.pop(field), ensure_ascii=False)
    values["updated_at"] = _now()
    allowed = {
        "name",
        "email",
        "phone",
        "group_name",
        "party_size",
        "notes",
        "dietary_requirements_json",
        "accessibility_requirements_json",
        "accommodation_requirements_json",
        "invitation_status",
        "rsvp_party_size",
        "duplicate_of_id",
        "updated_at",
    }
    unexpected = set(values) - allowed
    if unexpected:
        raise ValueError("unsupported guest update fields")
    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            "UPDATE guests SET "
            + ", ".join(f"{field} = :{field}" for field in values)
            + " WHERE event_id = :event_id AND id = :id",
            {**values, "event_id": event_id, "id": guest_id},
        )
        if cursor.rowcount != 1:
            return None
        connection.execute(
            "INSERT INTO rsvp_activity (id, event_id, guest_id, action, source, details_json, created_at) "
            "VALUES (?, ?, ?, 'guest_updated', 'host', ?, ?)",
            (
                str(uuid.uuid4()),
                event_id,
                guest_id,
                json.dumps({"fields": sorted(key for key in values if key != "updated_at")}),
                values["updated_at"],
            ),
        )
        row = connection.execute("SELECT * FROM guests WHERE id = ?", (guest_id,)).fetchone()
    return _guest_dict(row)


def delete_event_guest(event_id: str, guest_id: str) -> bool:
    with closing(_connect()) as connection, connection:
        connection.execute(
            "UPDATE guests SET duplicate_of_id = NULL WHERE event_id = ? AND duplicate_of_id = ?",
            (event_id, guest_id),
        )
        cursor = connection.execute(
            "DELETE FROM guests WHERE event_id = ? AND id = ?", (event_id, guest_id)
        )
    return cursor.rowcount == 1


def list_guest_duplicate_suggestions(event_id: str) -> list[dict[str, Any]]:
    guests = [guest for guest in list_event_guests(event_id) if not guest["duplicate_of_id"]]
    suggestions: list[dict[str, Any]] = []
    for index, guest in enumerate(guests):
        for candidate in guests[index + 1 :]:
            reasons: list[str] = []
            email_match = bool(guest["email"] and guest["email"] == candidate["email"])
            phone_match = bool(guest["phone"] and guest["phone"] == candidate["phone"])
            if email_match:
                reasons.append("email")
            if phone_match:
                reasons.append("phone")
            if (
                guest["name"].casefold() == candidate["name"].casefold()
                and (email_match or phone_match)
            ):
                reasons.append("name_and_contact")
            if reasons:
                suggestions.append(
                    {
                        "guest_id": candidate["id"],
                        "possible_duplicate_id": guest["id"],
                        "match_reasons": reasons,
                    }
                )
    return suggestions


def record_guest_rsvp(
    event_id: str, guest_id: str, changes: dict[str, Any]
) -> dict[str, Any] | None:
    now = _now()
    with closing(_connect()) as connection, connection:
        row = connection.execute(
            "SELECT * FROM guests WHERE event_id = ? AND id = ?", (event_id, guest_id)
        ).fetchone()
        if row is None:
            return None
        current = _guest_dict(row)
        status_value = changes["rsvp_status"]
        party_size = changes.get("party_size")
        if status_value == "attending":
            party_size = party_size if party_size is not None else current["rsvp_party_size"] or current["party_size"]
            if party_size > current["party_size"]:
                raise ValueError("party_size cannot exceed the invited party_size")
        else:
            party_size = None
        update_values: dict[str, Any] = {
            "rsvp_status": status_value,
            "rsvp_party_size": party_size,
            "updated_at": now,
        }
        for field, column in (
            ("notes", "notes"),
            ("dietary_requirements", "dietary_requirements_json"),
            ("accessibility_requirements", "accessibility_requirements_json"),
            ("accommodation_requirements", "accommodation_requirements_json"),
        ):
            if field in changes:
                update_values[column] = (
                    json.dumps(changes[field], ensure_ascii=False)
                    if field.endswith("requirements")
                    else changes[field]
                )
        connection.execute(
            "UPDATE guests SET "
            + ", ".join(f"{field} = :{field}" for field in update_values)
            + " WHERE id = :id",
            {**update_values, "id": guest_id},
        )
        details = {
            "from": current["rsvp_status"],
            "to": status_value,
            "party_size": party_size,
        }
        connection.execute(
            "INSERT INTO rsvp_activity (id, event_id, guest_id, action, source, details_json, created_at) "
            "VALUES (?, ?, ?, 'rsvp_recorded', ?, ?, ?)",
            (
                str(uuid.uuid4()),
                event_id,
                guest_id,
                changes.get("source", "manual"),
                json.dumps(details, ensure_ascii=False),
                now,
            ),
        )
        result = connection.execute("SELECT * FROM guests WHERE id = ?", (guest_id,)).fetchone()
    return _guest_dict(result)


def list_rsvp_activity(event_id: str, guest_id: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM rsvp_activity WHERE event_id = ?"
    params: list[str] = [event_id]
    if guest_id is not None:
        query += " AND guest_id = ?"
        params.append(guest_id)
    query += " ORDER BY created_at DESC, id DESC"
    with closing(_connect()) as connection:
        rows = connection.execute(query, params).fetchall()
    return [
        {
            **dict(row),
            "details": json.loads(row["details_json"]),
        }
        for row in rows
    ]


def _draft_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["missing_information"] = json.loads(result.pop("missing_information_json") or "[]")
    return result


def list_invitation_drafts(event_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM invitation_drafts WHERE event_id = ? ORDER BY created_at DESC, id DESC",
            (event_id,),
        ).fetchall()
    return [_draft_dict(row) for row in rows]


def load_invitation_draft(event_id: str, draft_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT * FROM invitation_drafts WHERE event_id = ? AND id = ?",
            (event_id, draft_id),
        ).fetchone()
    return _draft_dict(row) if row else None


def create_invitation_draft(event_id: str, draft: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    values = {
        **draft,
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "created_at": now,
        "updated_at": now,
        "rsvp_deadline": (
            draft["rsvp_deadline"].isoformat()
            if isinstance(draft.get("rsvp_deadline"), date)
            else draft.get("rsvp_deadline")
        ),
        "missing_information_json": json.dumps(
            draft.get("missing_information", []), ensure_ascii=False
        ),
    }
    with closing(_connect()) as connection, connection:
        connection.execute(
            "INSERT INTO invitation_drafts (id, event_id, kind, subject, body, tone, language, "
            "group_name, rsvp_deadline, generated_by, missing_information_json, created_at, updated_at) "
            "VALUES (:id, :event_id, :kind, :subject, :body, :tone, :language, :group_name, "
            ":rsvp_deadline, :generated_by, :missing_information_json, :created_at, :updated_at)",
            values,
        )
        row = connection.execute(
            "SELECT * FROM invitation_drafts WHERE id = ?", (values["id"],)
        ).fetchone()
    return _draft_dict(row)


def update_invitation_draft(
    event_id: str, draft_id: str, changes: dict[str, Any]
) -> dict[str, Any] | None:
    if not changes:
        raise ValueError("provide at least one draft field to update")
    values = dict(changes)
    if "rsvp_deadline" in values and isinstance(values["rsvp_deadline"], date):
        values["rsvp_deadline"] = values["rsvp_deadline"].isoformat()
    values["updated_at"] = _now()
    allowed = {"subject", "body", "tone", "language", "group_name", "rsvp_deadline", "updated_at"}
    if set(values) - allowed:
        raise ValueError("unsupported draft update fields")
    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            "UPDATE invitation_drafts SET "
            + ", ".join(f"{field} = :{field}" for field in values)
            + " WHERE event_id = :event_id AND id = :id",
            {**values, "event_id": event_id, "id": draft_id},
        )
        if cursor.rowcount != 1:
            return None
        row = connection.execute("SELECT * FROM invitation_drafts WHERE id = ?", (draft_id,)).fetchone()
    return _draft_dict(row)


def _attempt_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def list_delivery_attempts(event_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM delivery_attempts WHERE event_id = ? ORDER BY created_at DESC, id DESC",
            (event_id,),
        ).fetchall()
    return [_attempt_dict(row) for row in rows]


def load_delivery_attempt(event_id: str, attempt_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT * FROM delivery_attempts WHERE event_id = ? AND id = ?",
            (event_id, attempt_id),
        ).fetchone()
    return _attempt_dict(row) if row else None


def _batch_dict(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    attempts = connection.execute(
        "SELECT * FROM delivery_attempts WHERE batch_id = ? ORDER BY created_at, id",
        (row["id"],),
    ).fetchall()
    result["attempts"] = [_attempt_dict(attempt) for attempt in attempts]
    return result


def load_delivery_batch(event_id: str, batch_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT * FROM delivery_batches WHERE event_id = ? AND id = ?",
            (event_id, batch_id),
        ).fetchone()
        return _batch_dict(connection, row) if row else None


def find_delivery_batch_by_idempotency(
    event_id: str, idempotency_key: str
) -> dict[str, Any] | None:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT * FROM delivery_batches WHERE event_id = ? AND idempotency_key = ?",
            (event_id, idempotency_key),
        ).fetchone()
        return _batch_dict(connection, row) if row else None


def create_delivery_batch(
    event_id: str,
    draft_id: str,
    kind: str,
    idempotency_key: str,
    delivery_mode: str,
    recipients: list[dict[str, str]],
    *,
    retry_of_id: str | None = None,
) -> tuple[dict[str, Any], bool]:
    now = _now()
    batch_id = str(uuid.uuid4())
    initial_status = "draft_only" if delivery_mode == "draft_only" else "unknown"
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT * FROM delivery_batches WHERE event_id = ? AND idempotency_key = ?",
            (event_id, idempotency_key),
        ).fetchone()
        if existing is not None:
            stored = _batch_dict(connection, existing)
            if stored["draft_id"] != draft_id:
                raise ValueError("The idempotency key was already used for another delivery.")
            return stored, False
        connection.execute(
            "INSERT INTO delivery_batches (id, event_id, draft_id, kind, idempotency_key, status, "
            "delivery_mode, approved_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                batch_id,
                event_id,
                draft_id,
                kind,
                idempotency_key,
                initial_status,
                delivery_mode,
                now,
                now,
                now,
            ),
        )
        if delivery_mode == "smtp":
            for recipient in recipients:
                connection.execute(
                    "INSERT INTO delivery_attempts (id, batch_id, event_id, guest_id, draft_id, channel, "
                    "status, recipient_address, provider_message_id, transport_message_id, error_message, "
                    "retry_of_id, created_at, updated_at, sent_at, delivered_at) "
                    "VALUES (?, ?, ?, ?, ?, 'email', 'queued', ?, NULL, NULL, NULL, ?, ?, ?, NULL, NULL)",
                    (
                        str(uuid.uuid4()),
                        batch_id,
                        event_id,
                        recipient["guest_id"],
                        draft_id,
                        recipient["email"],
                        retry_of_id,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    "UPDATE guests SET invitation_status = 'queued', updated_at = ? "
                    "WHERE event_id = ? AND id = ?",
                    (now, event_id, recipient["guest_id"]),
                )
        row = connection.execute(
            "SELECT * FROM delivery_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        result = _batch_dict(connection, row)
    return result, True


def update_delivery_attempt(
    event_id: str, attempt_id: str, changes: dict[str, Any]
) -> dict[str, Any] | None:
    if not changes:
        raise ValueError("provide at least one attempt update field")
    allowed = {
        "status",
        "provider_message_id",
        "transport_message_id",
        "error_message",
        "sent_at",
        "delivered_at",
    }
    if set(changes) - allowed:
        raise ValueError("unsupported delivery attempt update fields")
    values = {**changes, "updated_at": _now()}
    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            "UPDATE delivery_attempts SET "
            + ", ".join(f"{field} = :{field}" for field in values)
            + " WHERE event_id = :event_id AND id = :id",
            {**values, "event_id": event_id, "id": attempt_id},
        )
        if cursor.rowcount != 1:
            return None
        row = connection.execute("SELECT * FROM delivery_attempts WHERE id = ?", (attempt_id,)).fetchone()
    return _attempt_dict(row)


def update_delivery_batch_status(
    event_id: str, batch_id: str, status_value: str
) -> dict[str, Any] | None:
    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            "UPDATE delivery_batches SET status = ?, updated_at = ? WHERE event_id = ? AND id = ?",
            (status_value, _now(), event_id, batch_id),
        )
        if cursor.rowcount != 1:
            return None
        row = connection.execute("SELECT * FROM delivery_batches WHERE id = ?", (batch_id,)).fetchone()
        return _batch_dict(connection, row)


def has_active_delivery_for_guest(event_id: str, draft_id: str, guest_id: str) -> bool:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT 1 FROM delivery_attempts WHERE event_id = ? AND draft_id = ? AND guest_id = ? "
            "AND status IN ('queued', 'sent', 'delivered', 'unknown') LIMIT 1",
            (event_id, draft_id, guest_id),
        ).fetchone()
    return row is not None


def update_guest_invitation_status(
    event_id: str, guest_id: str, status_value: str
) -> dict[str, Any] | None:
    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            "UPDATE guests SET invitation_status = ?, updated_at = ? "
            "WHERE event_id = ? AND id = ?",
            (status_value, _now(), event_id, guest_id),
        )
        if cursor.rowcount != 1:
            return None
        row = connection.execute("SELECT * FROM guests WHERE id = ?", (guest_id,)).fetchone()
    return _guest_dict(row)


def create_reminder_preparation(
    event_id: str, draft_id: str, guest_ids: list[str]
) -> dict[str, Any]:
    now = _now()
    preparation_id = str(uuid.uuid4())
    with closing(_connect()) as connection, connection:
        connection.execute(
            "INSERT INTO reminder_preparations (id, event_id, draft_id, guest_ids_json, status, "
            "delivery_batch_id, created_at, updated_at) VALUES (?, ?, ?, ?, 'prepared', NULL, ?, ?)",
            (preparation_id, event_id, draft_id, json.dumps(guest_ids), now, now),
        )
        row = connection.execute(
            "SELECT * FROM reminder_preparations WHERE id = ?", (preparation_id,)
        ).fetchone()
    return _reminder_preparation_dict(row)


def _reminder_preparation_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["guest_ids"] = json.loads(result.pop("guest_ids_json") or "[]")
    return result


def list_reminder_preparations(event_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM reminder_preparations WHERE event_id = ? ORDER BY created_at DESC, id DESC",
            (event_id,),
        ).fetchall()
    return [_reminder_preparation_dict(row) for row in rows]


def load_reminder_preparation(
    event_id: str, preparation_id: str
) -> dict[str, Any] | None:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT * FROM reminder_preparations WHERE event_id = ? AND id = ?",
            (event_id, preparation_id),
        ).fetchone()
    return _reminder_preparation_dict(row) if row else None


def update_reminder_preparation(
    event_id: str,
    preparation_id: str,
    *,
    status_value: str,
    delivery_batch_id: str | None = None,
) -> dict[str, Any] | None:
    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            "UPDATE reminder_preparations SET status = ?, delivery_batch_id = ?, updated_at = ? "
            "WHERE event_id = ? AND id = ?",
            (status_value, delivery_batch_id, _now(), event_id, preparation_id),
        )
        if cursor.rowcount != 1:
            return None
        row = connection.execute(
            "SELECT * FROM reminder_preparations WHERE id = ?", (preparation_id,)
        ).fetchone()
    return _reminder_preparation_dict(row)


