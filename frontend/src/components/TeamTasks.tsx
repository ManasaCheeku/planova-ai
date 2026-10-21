import { useMemo, useState, type FormEvent } from "react";
import { createDashboardTask, updateDashboardTask } from "../api";
import type {
  DashboardEvent,
  DashboardSnapshot,
  DashboardTask,
  TaskStatus,
} from "../types";

type TaskPriority = DashboardTask["priority"];
type StatusFilter = "all" | TaskStatus | "overdue" | "blocked";

interface TeamTasksProps {
  snapshot: DashboardSnapshot | null;
  loading: boolean;
  error: string;
  onRefresh: () => Promise<boolean>;
}

interface TaskDraft {
  title: string;
  description: string;
  eventId: string;
  assignedTo: string;
  priority: TaskPriority;
  dueDate: string;
  completionCriteria: string;
  dependencies: string[];
}

const emptyDraft: TaskDraft = {
  title: "",
  description: "",
  eventId: "",
  assignedTo: "",
  priority: "medium",
  dueDate: "",
  completionCriteria: "",
  dependencies: [],
};

const statusLabels: Record<TaskStatus, string> = {
  pending: "Pending",
  in_progress: "In progress",
  completed: "Completed",
};

function eventName(events: DashboardEvent[], eventId: string | null): string {
  if (!eventId) return "Unlinked task";
  return events.find((event) => event.id === eventId)?.plan.event.event_name
    ?? "Saved event";
}

function formatDueDate(task: DashboardTask): string {
  if (!task.due_date) return "No deadline";
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${task.due_date}T00:00:00Z`));
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The task action could not be completed.";
}

export default function TeamTasks({
  snapshot,
  loading,
  error,
  onRefresh,
}: TeamTasksProps) {
  const tasks = snapshot?.tasks ?? [];
  const events = snapshot?.events ?? [];
  const [eventFilter, setEventFilter] = useState("all");
  const [personFilter, setPersonFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [priorityFilter, setPriorityFilter] = useState<"all" | TaskPriority>("all");
  const [draft, setDraft] = useState<TaskDraft>(emptyDraft);
  const [editingTaskId, setEditingTaskId] = useState("");
  const [busy, setBusy] = useState(false);
  const [busyTaskId, setBusyTaskId] = useState("");
  const [formError, setFormError] = useState("");
  const [actionError, setActionError] = useState("");
  const [success, setSuccess] = useState("");

  const members = useMemo(() => {
    const memberTasks = new Map<string, DashboardTask[]>();
    for (const task of tasks) {
      const name = task.assigned_to?.trim();
      if (!name) continue;
      const key = name.toLocaleLowerCase();
      const existing = memberTasks.get(key);
      if (existing) existing.push(task);
      else memberTasks.set(key, [task]);
    }
    return [...memberTasks.entries()]
      .map(([key, assignedTasks]) => ({
        key,
        name: assignedTasks[0].assigned_to?.trim() ?? "",
        tasks: assignedTasks,
        completed: assignedTasks.filter((task) => task.status === "completed").length,
      }))
      .sort((left, right) => left.name.localeCompare(right.name));
  }, [tasks]);

  const filteredTasks = useMemo(() => tasks.filter((task) => {
    if (eventFilter !== "all" && (task.event_id ?? "") !== eventFilter) return false;
    if (
      personFilter !== "all"
      && task.assigned_to?.trim().toLocaleLowerCase() !== personFilter
    ) return false;
    if (priorityFilter !== "all" && task.priority !== priorityFilter) return false;
    if (statusFilter === "overdue" && !task.overdue) return false;
    if (statusFilter === "blocked" && !task.blocked) return false;
    if (
      statusFilter !== "all"
      && statusFilter !== "overdue"
      && statusFilter !== "blocked"
      && task.status !== statusFilter
    ) return false;
    return true;
  }), [tasks, eventFilter, personFilter, priorityFilter, statusFilter]);

  const eligibleDependencies = tasks.filter((task) => {
    if (task.id === editingTaskId) return false;
    const sameEvent = editingTaskId
      ? tasks.find((item) => item.id === editingTaskId)?.event_id === task.event_id
      : (draft.eventId || null) === task.event_id;
    return sameEvent;
  });

  function startEditing(task: DashboardTask) {
    setEditingTaskId(task.id);
    setDraft({
      title: task.title,
      description: task.description,
      eventId: task.event_id ?? "",
      assignedTo: task.assigned_to ?? "",
      priority: task.priority,
      dueDate: task.due_date ?? "",
      completionCriteria: task.completion_criteria,
      dependencies: [...task.dependencies],
    });
    setFormError("");
    setSuccess("");
  }

  function resetDraft() {
    setEditingTaskId("");
    setDraft(emptyDraft);
    setFormError("");
  }

  async function saveTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setFormError("");
    setActionError("");
    setSuccess("");
    try {
      const fields = {
        title: draft.title.trim(),
        description: draft.description.trim(),
        due_date: draft.dueDate || null,
        priority: draft.priority,
        assigned_to: draft.assignedTo.trim() || null,
        completion_criteria: draft.completionCriteria.trim(),
        dependencies: draft.dependencies,
      };
      if (editingTaskId) {
        await updateDashboardTask(editingTaskId, fields);
      } else {
        await createDashboardTask({
          ...fields,
          ...(draft.eventId ? { event_id: draft.eventId } : {}),
        });
      }
      const refreshed = await onRefresh();
      if (!refreshed) {
        setSuccess("Task was saved. The list could not refresh; use Refresh data to reload.");
      } else {
        setSuccess(editingTaskId ? "Task changes saved." : "Task added.");
      }
      resetDraft();
    } catch (saveError) {
      setFormError(getErrorMessage(saveError));
    } finally {
      setBusy(false);
    }
  }

  async function changeStatus(task: DashboardTask, status: TaskStatus) {
    setBusyTaskId(task.id);
    setActionError("");
    setSuccess("");
    try {
      await updateDashboardTask(task.id, { status });
      if (await onRefresh()) setSuccess(`“${task.title}” updated to ${statusLabels[status]}.`);
      else setSuccess("Task status was saved. Refresh the data to see the latest list.");
    } catch (statusError) {
      setActionError(getErrorMessage(statusError));
    } finally {
      setBusyTaskId("");
    }
  }

  if (!snapshot && loading) {
    return <div className="team-task-load" role="status">Loading saved tasks and assignments…</div>;
  }

  return (
    <div className="page-wrap team-tasks-page">
      <div className="page-intro">
        <div>
          <div className="eyebrow">SHARED EVENT WORK</div>
          <h1>Team &amp; tasks</h1>
          <p>Assign responsibilities, track deadlines, and respect task dependencies across your saved events.</p>
        </div>
        <button className="button button-secondary" type="button" onClick={() => void onRefresh()} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh data"}
        </button>
      </div>

      <div className="session-notice">
        <span aria-hidden="true">i</span>
        Assignees are organizer-entered labels, not authenticated accounts. Tasks are stored in this backend&apos;s local database.
      </div>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {actionError && <div className="alert alert-error" role="alert">{actionError}</div>}
      {success && <div className="team-task-success" role="status">{success}</div>}

      <section className="team-member-section" aria-labelledby="team-members-heading">
        <div className="team-section-heading">
          <div>
            <div className="eyebrow">CURRENT ASSIGNMENTS</div>
            <h2 id="team-members-heading">People &amp; progress</h2>
          </div>
          <span>{members.length} {members.length === 1 ? "assigned person" : "assigned people"}</span>
        </div>
        {members.length ? (
          <div className="team-member-grid">
            {members.map((member) => {
              const percentage = member.tasks.length
                ? Math.round((member.completed / member.tasks.length) * 100)
                : 0;
              return (
                <button
                  className={`team-member-card${personFilter === member.key ? " team-member-card-active" : ""}`}
                  key={member.key}
                  type="button"
                  onClick={() => setPersonFilter(personFilter === member.key ? "all" : member.key)}
                  aria-pressed={personFilter === member.key}
                >
                  <span className="team-member-avatar" aria-hidden="true">
                    {member.name.slice(0, 1).toLocaleUpperCase()}
                  </span>
                  <span className="team-member-copy">
                    <strong>{member.name}</strong>
                    <small>{member.completed} of {member.tasks.length} tasks completed</small>
                    <span className="team-progress-track" aria-label={`${percentage}% complete`}>
                      <span style={{ width: `${percentage}%` }} />
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="team-empty-state">
            No task assignments are recorded yet. Add an assignee to a task to see responsibilities here.
          </div>
        )}
      </section>

      <div className="team-task-layout">
        <section className="team-task-panel" aria-labelledby="task-list-heading">
          <div className="team-section-heading">
            <div>
              <div className="eyebrow">SAVED WORK</div>
              <h2 id="task-list-heading">Task board</h2>
            </div>
            <span>{filteredTasks.length} shown</span>
          </div>
          <div className="team-task-filters" aria-label="Filter tasks">
            <label>
              <span>Event</span>
              <select value={eventFilter} onChange={(event) => setEventFilter(event.target.value)}>
                <option value="all">All events</option>
                <option value="">Unlinked tasks</option>
                {events.map((item) => (
                  <option key={item.id} value={item.id}>{item.plan.event.event_name}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Person</span>
              <select value={personFilter} onChange={(event) => setPersonFilter(event.target.value)}>
                <option value="all">Everyone</option>
                {members.map((member) => (
                  <option key={member.key} value={member.key}>{member.name}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Status</span>
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}>
                <option value="all">All statuses</option>
                <option value="pending">Pending</option>
                <option value="in_progress">In progress</option>
                <option value="completed">Completed</option>
                <option value="overdue">Overdue</option>
                <option value="blocked">Blocked</option>
              </select>
            </label>
            <label>
              <span>Priority</span>
              <select value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value as "all" | TaskPriority)}>
                <option value="all">All priorities</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </label>
          </div>

          {loading && snapshot && <div className="team-task-refreshing" role="status">Updating saved task data…</div>}
          {filteredTasks.length ? (
            <ul className="team-task-list">
              {filteredTasks.map((task) => (
                <li className="team-task-item" key={task.id}>
                  <div className="team-task-item-head">
                    <div>
                      <span className={`team-priority team-priority-${task.priority}`}>{task.priority} priority</span>
                      <h3>{task.title}</h3>
                    </div>
                    <button className="button button-small button-secondary" type="button" onClick={() => startEditing(task)}>
                      Edit
                    </button>
                  </div>
                  {task.description && <p>{task.description}</p>}
                  <div className="team-task-meta">
                    <span>{eventName(events, task.event_id)}</span>
                    <span>{task.assigned_to || "Unassigned"}</span>
                    <span className={task.overdue ? "team-overdue" : ""}>{task.overdue ? "Overdue · " : "Due · "}{formatDueDate(task)}</span>
                  </div>
                  {task.completion_criteria && (
                    <div className="team-task-criteria"><strong>Complete when:</strong> {task.completion_criteria}</div>
                  )}
                  {task.dependencies.length > 0 && (
                    <div className={`team-task-dependency${task.blocked ? " team-task-blocked" : ""}`}>
                      <strong>{task.blocked ? "Blocked by" : "Depends on"}:</strong>{" "}
                      {task.blockers.length
                        ? task.blockers.join(", ")
                        : task.dependencies.map((id) => tasks.find((item) => item.id === id)?.title ?? "Missing task").join(", ")}
                    </div>
                  )}
                  <div className="team-task-item-footer">
                    <label>
                      <span className="team-visually-hidden">Status for {task.title}</span>
                      <select
                        value={task.status}
                        disabled={busyTaskId === task.id}
                        onChange={(event) => void changeStatus(task, event.target.value as TaskStatus)}
                      >
                        {Object.entries(statusLabels).map(([value, label]) => (
                          <option key={value} value={value}>{label}</option>
                        ))}
                      </select>
                    </label>
                    {task.blocked && <span className="team-task-badge">Blocked</span>}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="team-empty-state">
              {tasks.length ? "No saved tasks match these filters." : "No tasks have been saved yet. Add a task to begin coordinating work."}
            </div>
          )}
        </section>

        <section className="team-task-panel team-task-editor" aria-labelledby="task-editor-heading">
          <div className="team-section-heading">
            <div>
              <div className="eyebrow">{editingTaskId ? "UPDATE SAVED WORK" : "ADD RESPONSIBILITY"}</div>
              <h2 id="task-editor-heading">{editingTaskId ? "Edit task" : "New task"}</h2>
            </div>
            {editingTaskId && <button className="button button-small button-secondary" type="button" onClick={resetDraft}>Cancel</button>}
          </div>
          {formError && <div className="alert alert-error" role="alert">{formError}</div>}
          <form className="team-task-form" onSubmit={(event) => void saveTask(event)}>
            <label>
              <span>Task title</span>
              <input required maxLength={160} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} />
            </label>
            <label>
              <span>Description</span>
              <textarea maxLength={1000} rows={3} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} />
            </label>
            <label>
              <span>Event</span>
              <select
                value={draft.eventId}
                disabled={Boolean(editingTaskId)}
                onChange={(event) => setDraft({ ...draft, eventId: event.target.value, dependencies: [] })}
              >
                <option value="">Unlinked task</option>
                {events.map((item) => <option key={item.id} value={item.id}>{item.plan.event.event_name}</option>)}
              </select>
              {editingTaskId && <small>Event linkage cannot be changed after creation.</small>}
            </label>
            <div className="team-task-form-row">
              <label>
                <span>Assign to</span>
                <input maxLength={120} value={draft.assignedTo} placeholder="Organizer-entered name" onChange={(event) => setDraft({ ...draft, assignedTo: event.target.value })} />
              </label>
              <label>
                <span>Priority</span>
                <select value={draft.priority} onChange={(event) => setDraft({ ...draft, priority: event.target.value as TaskPriority })}>
                  <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
                </select>
              </label>
            </div>
            <label>
              <span>Deadline</span>
              <input type="date" value={draft.dueDate} onChange={(event) => setDraft({ ...draft, dueDate: event.target.value })} />
            </label>
            <label>
              <span>Completion criteria</span>
              <textarea maxLength={500} rows={2} value={draft.completionCriteria} onChange={(event) => setDraft({ ...draft, completionCriteria: event.target.value })} />
            </label>
            <fieldset className="team-dependency-picker">
              <legend>Depends on</legend>
              {eligibleDependencies.length ? eligibleDependencies.map((task) => (
                <label key={task.id}>
                  <input
                    type="checkbox"
                    checked={draft.dependencies.includes(task.id)}
                    onChange={(event) => setDraft({
                      ...draft,
                      dependencies: event.target.checked
                        ? [...draft.dependencies, task.id]
                        : draft.dependencies.filter((id) => id !== task.id),
                    })}
                  />
                  <span>{task.title} <small>· {statusLabels[task.status]}</small></span>
                </label>
              )) : <p>No other tasks are available in this task group.</p>}
            </fieldset>
            <button className="button button-primary" type="submit" disabled={busy || !draft.title.trim()}>
              {busy ? "Saving…" : editingTaskId ? "Save task changes" : "Add task"}
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
