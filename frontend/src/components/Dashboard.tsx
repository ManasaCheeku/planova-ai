import { useState, type FormEvent } from "react";
import {
  createDashboardTask,
  createEvent,
  runDashboardCommand,
  updateDashboardEvent,
  updateDashboardTask,
} from "../api";
import type {
  DashboardCommandResult,
  DashboardSnapshot,
  DashboardTask,
  EventStatus,
  EventRequest,
} from "../types";

interface DashboardProps {
  snapshot: DashboardSnapshot | null;
  loading: boolean;
  error: string;
  onRefresh: () => Promise<boolean>;
  onSnapshotChange: (snapshot: DashboardSnapshot) => void;
  onNavigate: (path: string) => void;
  onEditDraft: (draft: EventRequest) => void;
}

const money = (amount: number, currency = "INR") =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(amount);

function formatDate(value: string | null | undefined): string {
  if (!value) return "Date not provided";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return "Date not provided";
  return new Intl.DateTimeFormat("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(parsed);
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "Time not provided";
  const [hour, minute] = value.split(":");
  if (hour === undefined || minute === undefined) return "Time not provided";
  return `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`;
}

function getDueLabel(task: DashboardTask): string {
  if (!task.due_date) return "No due date";
  const overdue = task.status !== "completed" && task.due_date < new Date().toISOString().slice(0, 10);
  return `${overdue ? "Overdue · " : "Due · "}${formatDate(task.due_date)}`;
}

function taskMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The task update could not be completed.";
}

function riskTone(severity: "low" | "medium" | "high"): string {
  return `dashboard-risk-${severity}`;
}

export default function Dashboard({
  snapshot,
  loading,
  error,
  onRefresh,
  onSnapshotChange,
  onNavigate,
  onEditDraft,
}: DashboardProps) {
  const [command, setCommand] = useState("");
  const [commandBusy, setCommandBusy] = useState(false);
  const [commandResult, setCommandResult] = useState<DashboardCommandResult | null>(null);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [commandError, setCommandError] = useState("");
  const [savedMessage, setSavedMessage] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDueDate, setTaskDueDate] = useState("");
  const [taskEventId, setTaskEventId] = useState("");
  const [taskBusy, setTaskBusy] = useState(false);
  const [taskError, setTaskError] = useState("");
  const [taskSuccess, setTaskSuccess] = useState("");
  const [eventBusyId, setEventBusyId] = useState("");
  const [taskBusyId, setTaskBusyId] = useState("");
  const [actionError, setActionError] = useState("");

  async function submitCommand(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (commandBusy || !command.trim()) return;
    setCommandBusy(true);
    setCommandError("");
    setSavedMessage("");
    setCommandResult(null);
    try {
      const result = await runDashboardCommand(command.trim(), conversationId);
      setConversationId(result.conversation_id ?? undefined);
      setCommandResult(result);
    } catch (requestError) {
      setCommandError(taskMessage(requestError));
    } finally {
      setCommandBusy(false);
    }
  }

  async function saveDraft() {
    if (!commandResult?.draft || !commandResult.plan || commandBusy) return;
    setCommandBusy(true);
    setCommandError("");
    setSavedMessage("");
    try {
      const draft = commandResult.draft;
      const input: EventRequest = {
        ...draft,
        budget: Number(draft.budget),
      };
      const savedPlan = await createEvent(input);
      if (!savedPlan.event_id) {
        throw new Error("The API response did not include a saved event ID.");
      }
      const refreshed = await onRefresh();
      setSavedMessage(
        refreshed
          ? "Plan saved to this application's local event history."
          : "Plan was saved, but the Dashboard could not refresh. Use Refresh data to reload it.",
      );
      if (refreshed) onNavigate(`/events/${encodeURIComponent(savedPlan.event_id)}`);
    } catch (requestError) {
      setCommandError(taskMessage(requestError));
    } finally {
      setCommandBusy(false);
    }
  }

  async function addTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (taskBusy || !taskTitle.trim()) return;
    setTaskBusy(true);
    setTaskError("");
    setTaskSuccess("");
    try {
      await createDashboardTask({
        title: taskTitle.trim(),
        ...(taskDueDate ? { due_date: taskDueDate } : {}),
        ...(taskEventId ? { event_id: taskEventId } : {}),
      });
      setTaskTitle("");
      setTaskDueDate("");
      setTaskEventId("");
      setTaskSuccess("Task saved.");
      await onRefresh();
    } catch (requestError) {
      setTaskError(taskMessage(requestError));
    } finally {
      setTaskBusy(false);
    }
  }

  async function toggleTask(task: DashboardTask) {
    const nextStatus = task.status === "completed" ? "pending" : "completed";
    setTaskBusyId(task.id);
    setTaskError("");
    setTaskSuccess("");
    try {
      await updateDashboardTask(task.id, { status: nextStatus });
      setTaskSuccess(nextStatus === "completed" ? "Task marked complete." : "Task reopened.");
      await onRefresh();
    } catch (requestError) {
      setTaskError(taskMessage(requestError));
    } finally {
      setTaskBusyId("");
    }
  }

  async function changeEventStatus(eventId: string, status: EventStatus) {
    if (status === "cancelled" && !window.confirm("Cancel this event plan in Planova? This will only update its local plan status; it will not notify anyone or cancel external bookings.")) {
      return;
    }
    setEventBusyId(eventId);
    setActionError("");
    try {
      const updated = await updateDashboardEvent(eventId, status);
      onSnapshotChange(updated);
    } catch (requestError) {
      setActionError(taskMessage(requestError));
    } finally {
      setEventBusyId("");
    }
  }

  if (!snapshot && loading) {
    return <div className="dashboard-load-state" role="status">Loading your saved dashboard data…</div>;
  }

  const summary = snapshot?.summary;
  const activeEvents = snapshot?.events.filter((item) => item.status === "scheduled") ?? [];
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = activeEvents
    .filter((item) => item.plan.event.event_date && item.plan.event.event_date >= today)
    .sort((left, right) =>
      `${left.plan.event.event_date ?? ""}T${left.plan.event.event_time ?? "23:59"}`
        .localeCompare(`${right.plan.event.event_date ?? ""}T${right.plan.event.event_time ?? "23:59"}`),
    );
  const pastUnmarked = activeEvents.filter(
    (item) => item.plan.event.event_date && item.plan.event.event_date < today,
  );
  const latestEvents = snapshot?.events.slice(0, 5) ?? [];
  const riskAlerts = snapshot?.risk_alerts.slice(0, 5) ?? [];
  const costGroups = summary?.estimated_costs_by_currency ?? [];

  return (
    <div className="page-wrap dashboard-page">
      <div className="dashboard-welcome">
        <div className="welcome-copy">
          <div className="eyebrow">YOUR EVENT WORKSPACE</div>
          <h1>Make room for <em>what matters.</em></h1>
          <p>See saved event plans, upcoming dates, budget estimates, tasks and risk signals in one place.</p>
          <div className="dashboard-actions">
            <button className="button button-primary" type="button" onClick={() => onNavigate("/create")}>
              Create an event plan <span aria-hidden="true">↗</span>
            </button>
            <button className="button button-secondary" type="button" onClick={() => void onRefresh()} disabled={loading}>
              {loading ? "Refreshing…" : "Refresh data"}
            </button>
          </div>
        </div>
        <div className="welcome-visual" aria-hidden="true">
          <div className="visual-ring visual-ring-outer" />
          <div className="visual-ring visual-ring-inner" />
          <span className="visual-spark spark-one">✳</span>
          <span className="visual-spark spark-two">✧</span>
          <span className="visual-center">P</span>
          <div className="visual-caption">PLAN WITH<br />PERSPECTIVE</div>
        </div>
      </div>

      {error && (
        <div className="alert alert-error dashboard-api-error" role="alert">
          <span>{error}</span>
          <button className="text-link" type="button" onClick={() => void onRefresh()}>Retry</button>
        </div>
      )}
      {actionError && <div className="alert alert-error" role="alert">{actionError}</div>}

      {summary ? (
        <>
          <div className="section-title-row dashboard-section-heading">
            <div><span className="eyebrow">AT A GLANCE</span><h2>Event overview</h2></div>
            <span className="dashboard-updated">Data from the backend · refreshed {new Date(snapshot.updated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
          </div>
          <div className="dashboard-overview-grid">
            <article className="overview-card">
              <span className="overview-icon icon-lilac" aria-hidden="true">◇</span>
              <span className="metric-label">Total events</span>
              <strong>{summary.total_events}</strong>
              <span className="metric-caption">Persisted event plans</span>
            </article>
            <article className="overview-card">
              <span className="overview-icon icon-sage" aria-hidden="true">↗</span>
              <span className="metric-label">Upcoming</span>
              <strong>{summary.upcoming_events}</strong>
              <span className="metric-caption">Scheduled with a future date</span>
            </article>
            <article className="overview-card">
              <span className="overview-icon icon-peach" aria-hidden="true">✓</span>
              <span className="metric-label">Completed</span>
              <strong>{summary.completed_events}</strong>
              <span className="metric-caption">Marked complete in Planova</span>
            </article>
            <article className="overview-card">
              <span className="overview-icon icon-lilac" aria-hidden="true">×</span>
              <span className="metric-label">Cancelled</span>
              <strong>{summary.cancelled_events}</strong>
              <span className="metric-caption">Local status only; no external notices</span>
            </article>
          </div>

          <div className="dashboard-main-grid">
            <section className="dashboard-panel dashboard-budget-panel">
              <div className="section-title-row">
                <div><span className="eyebrow">PLANNING NUMBERS</span><h2>Budget overview</h2></div>
                <span className="dashboard-panel-icon" aria-hidden="true">¤</span>
              </div>
              {summary.budget_totals_by_currency.length ? (
                <div className="dashboard-currency-groups">
                  {summary.budget_totals_by_currency.map((group) => (
                    <div className="dashboard-currency-group" key={group.currency}>
                      <strong className="dashboard-currency-label">{group.currency}</strong>
                      <div className="dashboard-budget-totals">
                        <div><span>Planned budgets</span><strong>{money(group.planned_budget_total, group.currency)}</strong></div>
                        <div><span>Known estimates</span><strong>{money(group.known_estimated_costs, group.currency)}</strong></div>
                        <div><span>Budget less estimates</span><strong>{money(group.remaining_known_estimate_budget, group.currency)}</strong></div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <div className="dashboard-inline-empty">No saved budget totals are available.</div>}
              <p className="dashboard-disclaimer">Amounts are grouped by event currency and reflect estimates, not actual expenditure. Event details contain manually recorded expenses.</p>
              {costGroups.some((group) => Object.values(group.categories).some((amount) => typeof amount === "number" && amount > 0)) ? (
                <div className="dashboard-currency-groups" aria-label="Known cost estimates by category and currency">
                  {costGroups.map(({ currency, categories }) => {
                    const costs = Object.entries(categories)
                      .filter((entry): entry is [string, number] => typeof entry[1] === "number" && entry[1] > 0)
                      .sort((left, right) => right[1] - left[1]);
                    const largestCost = Math.max(...costs.map(([, amount]) => amount), 1);
                    return costs.length ? (
                      <div className="dashboard-currency-group" key={currency}>
                        <strong className="dashboard-currency-label">{currency} estimates</strong>
                        <div className="dashboard-cost-breakdown">
                          {costs.map(([category, amount]) => (
                            <div className="dashboard-cost-row" key={category}>
                              <div><span>{category.replaceAll("_", " ")}</span><strong>{money(amount, currency)}</strong></div>
                              <span className="dashboard-cost-track"><span style={{ width: `${(amount / largestCost) * 100}%` }} /></span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null;
                  })}
                </div>
              ) : (
                <div className="dashboard-inline-empty">No cost estimates have been supplied for active plans.</div>
              )}
            </section>

            <section className="dashboard-panel dashboard-risk-panel">
              <div className="section-title-row">
                <div><span className="eyebrow">EVENT RISK INTELLIGENCE</span><h2>Risk alerts</h2></div>
                <button className="text-link" type="button" onClick={() => onNavigate("/risks")}>Analyze scenarios <span aria-hidden="true">→</span></button>
              </div>
              <div className="dashboard-risk-counts">
                <span className="dashboard-risk-high">High <strong>{summary.risk_counts.high}</strong></span>
                <span className="dashboard-risk-medium">Medium <strong>{summary.risk_counts.medium}</strong></span>
                <span className="dashboard-risk-low">Low <strong>{summary.risk_counts.low}</strong></span>
              </div>
              {riskAlerts.length ? (
                <ul className="dashboard-risk-list">
                  {riskAlerts.map(({ event_id, event_name, risk }) => (
                    <li className={`dashboard-risk-alert ${riskTone(risk.severity)}`} key={`${event_id}-${risk.id}`}>
                      <span className="dashboard-risk-severity">{risk.severity}</span>
                      <div><strong>{risk.title}</strong><p>{event_name} · {risk.reason}</p><small>Next step: {risk.mitigation}</small></div>
                      <button type="button" className="dashboard-icon-button" aria-label={`Open ${event_name} plan`} onClick={() => onNavigate(`/events/${encodeURIComponent(event_id)}`)}>↗</button>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="dashboard-inline-empty">
                  {summary.total_events ? "No risk alerts were returned for scheduled event plans." : "Create an event plan to see API-generated risk alerts."}
                </div>
              )}
            </section>
          </div>

          <section className="dashboard-panel dashboard-schedule-panel">
            <div className="section-title-row">
              <div><span className="eyebrow">WHAT’S NEXT</span><h2>Upcoming schedule</h2></div>
              <button className="text-link" type="button" onClick={() => onNavigate("/events")}>All event plans <span aria-hidden="true">→</span></button>
            </div>
            {upcoming.length ? (
              <div className="dashboard-schedule-list">
                {upcoming.map(({ id, plan }) => (
                  <article className="dashboard-schedule-item" key={id}>
                    <div className="dashboard-date-block"><strong>{new Date(`${plan.event.event_date}T00:00:00`).getDate()}</strong><span>{new Intl.DateTimeFormat("en-IN", { month: "short" }).format(new Date(`${plan.event.event_date}T00:00:00`))}</span></div>
                    <div className="dashboard-schedule-copy">
                      <button type="button" className="dashboard-event-title" onClick={() => onNavigate(`/events/${encodeURIComponent(id)}`)}>{plan.event.event_name}</button>
                      <span>{formatDate(plan.event.event_date)} · {formatTime(plan.event.event_time)} · {plan.event.guest_count?.toLocaleString() ?? "Guest count not supplied"} guests</span>
                    </div>
                    <span className={`dashboard-event-status status-${snapshot.events.find((event) => event.id === id)?.status ?? "scheduled"}`}>Scheduled</span>
                    <div className="dashboard-event-actions">
                      <button type="button" className="dashboard-small-action" disabled={eventBusyId === id} onClick={() => void changeEventStatus(id, "completed")}>{eventBusyId === id ? "Saving…" : "Mark complete"}</button>
                      <button type="button" className="dashboard-small-action dashboard-cancel-action" disabled={eventBusyId === id} onClick={() => void changeEventStatus(id, "cancelled")}>Cancel plan</button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="dashboard-inline-empty">
                <strong>No upcoming events yet.</strong>
                <span>{summary.total_events ? "Saved plans with past dates are not automatically marked complete." : "Create an event plan to add its date to your schedule."}</span>
                <button className="button button-secondary" type="button" onClick={() => onNavigate("/create")}>Create event <span aria-hidden="true">→</span></button>
              </div>
            )}
            {pastUnmarked.length > 0 && (
              <div className="dashboard-past-events">
                <strong>Past plans needing a status</strong>
                {pastUnmarked.map(({ id, plan }) => (
                  <div className="dashboard-past-row" key={id}>
                    <span>{plan.event.event_name} · {formatDate(plan.event.event_date)}</span>
                    <button type="button" className="dashboard-small-action" disabled={eventBusyId === id} onClick={() => void changeEventStatus(id, "completed")}>Mark complete</button>
                  </div>
                ))}
              </div>
            )}
          </section>

          <div className="dashboard-main-grid dashboard-lower-grid">
            <section className="dashboard-panel dashboard-task-panel">
              <div className="section-title-row">
                <div><span className="eyebrow">COORDINATION</span><h2>Tasks</h2></div>
                <div className="dashboard-task-counts"><span>{summary.task_counts.pending} pending</span><span>{summary.task_counts.in_progress} in progress</span><span className="overdue">{summary.task_counts.overdue} overdue</span><span>{summary.task_counts.blocked} blocked</span><span>{summary.task_counts.completed} done</span></div>
              </div>
              <button className="dashboard-small-action" type="button" onClick={() => onNavigate("/tasks")}>Open team &amp; task board ↗</button>
              <form className="dashboard-task-form" onSubmit={(event) => void addTask(event)}>
                <label className="dashboard-visually-hidden" htmlFor="dashboard-task-title">New task</label>
                <input id="dashboard-task-title" value={taskTitle} maxLength={160} onChange={(event) => setTaskTitle(event.target.value)} placeholder="Add a coordination task…" required />
                <label className="dashboard-visually-hidden" htmlFor="dashboard-task-due">Task due date</label>
                <input id="dashboard-task-due" type="date" value={taskDueDate} onChange={(event) => setTaskDueDate(event.target.value)} />
                <label className="dashboard-visually-hidden" htmlFor="dashboard-task-event">Link task to event (optional)</label>
                <select id="dashboard-task-event" value={taskEventId} onChange={(event) => setTaskEventId(event.target.value)}>
                  <option value="">No linked event</option>
                  {snapshot.events.filter((item) => item.status === "scheduled").map(({ id, plan }) => <option value={id} key={id}>{plan.event.event_name}</option>)}
                </select>
                <button className="button button-primary" type="submit" disabled={taskBusy || !taskTitle.trim()}>{taskBusy ? "Saving…" : "Add task"}</button>
              </form>
              {taskError && <p className="dashboard-feedback dashboard-feedback-error" role="alert">{taskError}</p>}
              {taskSuccess && <p className="dashboard-feedback" role="status">{taskSuccess}</p>}
              {snapshot.tasks.length ? (
                <ul className="dashboard-task-list">
                  {snapshot.tasks.slice(0, 8).map((task) => (
                    <li className={task.status === "completed" ? "dashboard-task-complete" : task.overdue ? "dashboard-task-overdue" : ""} key={task.id}>
                      <button type="button" className="dashboard-task-toggle" aria-label={task.status === "completed" ? `Reopen ${task.title}` : `Complete ${task.title}`} disabled={taskBusyId === task.id} onClick={() => void toggleTask(task)}>{task.status === "completed" ? "✓" : ""}</button>
                      <span className="dashboard-task-copy"><strong>{task.title}</strong><small>{task.event_id ? snapshot.events.find((event) => event.id === task.event_id)?.plan.event.event_name ?? "Linked event" : "General"} · {getDueLabel(task)}</small></span>
                      <span className="dashboard-task-state">{task.status}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="dashboard-inline-empty">No tasks have been added. Create a task above to begin coordinating.</div>
              )}
            </section>

            <section className="dashboard-panel dashboard-command-panel">
              <div className="section-title-row">
                <div><span className="eyebrow">COMMAND CENTRE</span><h2>Describe an event</h2></div>
                <span className="dashboard-fallback-badge">{snapshot?.capabilities.ai_model_configured ? "GenAI enabled" : "Deterministic fallback"}</span>
              </div>
              <p className="dashboard-command-intro">Describe an event in natural language. Missing essentials become follow-up questions; the existing deterministic planner validates the draft and calculates budget, risks, and readiness.</p>
              <form className="dashboard-command-form" onSubmit={(event) => void submitCommand(event)}>
                <label htmlFor="dashboard-command">Event request</label>
                <textarea id="dashboard-command" rows={4} maxLength={1000} value={command} onChange={(event) => setCommand(event.target.value)} placeholder="Plan a birthday named Maya’s celebration for 40 guests in Pune on 2026-12-05 at 18:00 with a budget of ₹80000" />
                <button className="button button-primary" type="submit" disabled={commandBusy || !command.trim()}>{commandBusy ? "Checking details…" : "Build a draft"}</button>
              </form>
              <p className="dashboard-command-disclosure">{snapshot?.capabilities.ai_model_configured ? "Your request and recent follow-up turns are sent to the configured backend GenAI provider. Suggestions are not confirmed arrangements; nothing is saved until you choose to save, and no external actions are supported." : "No GenAI provider is configured. This uses deterministic parsing and the existing risk planner; it does not send invitations, book vendors, access calendars, or contact anyone."}</p>
              {commandError && <p className="dashboard-feedback dashboard-feedback-error" role="alert">{commandError}</p>}
              {savedMessage && <p className="dashboard-feedback" role="status">{savedMessage}</p>}
              {commandResult && (
                <div className="dashboard-command-result" aria-live="polite">
                  <p>{commandResult.notice}</p>
                  {commandResult.questions.length > 0 && (
                    <ul>{commandResult.questions.map((question) => <li key={question}>{question}</li>)}</ul>
                  )}
                  {commandResult.unsupported_actions.length > 0 && (
                    <p className="dashboard-feedback-error">Not supported and not attempted: {commandResult.unsupported_actions.join(", ")}.</p>
                  )}
                  {commandResult.plan && commandResult.draft && (
                    <>
                      <div className="dashboard-draft-summary">
                        <strong>{commandResult.draft.event_name}</strong>
                        <span>{commandResult.draft.event_type} · {formatDate(commandResult.draft.event_date)} · {formatTime(commandResult.draft.event_time)}</span>
                        <span>{commandResult.draft.guest_count} guests · {money(Number(commandResult.draft.budget), commandResult.draft.currency ?? "INR")} budget</span>
                        <span>{commandResult.plan.risks.length} risk(s) · {commandResult.plan.readiness.status.replaceAll("_", " ")}</span>
                      </div>
                      <button
                        type="button"
                        className="button button-secondary"
                        disabled={commandBusy}
                        onClick={() => onEditDraft({
                          ...commandResult.draft!,
                          budget: Number(commandResult.draft!.budget),
                        })}
                      >
                        Review and edit in Create Event
                      </button>
                      {commandResult.planning && (
                        <div className="dashboard-ai-plan-notes">
                          <strong>Suggested planning details · unconfirmed</strong>
                          {commandResult.planning.agenda.length > 0 && (
                            <ul>{commandResult.planning.agenda.map((item, index) => <li key={`${item.title}-${index}`}>{item.time ? `${item.time} · ` : ""}{item.title}{item.duration_minutes ? ` · ${item.duration_minutes} min` : ""} <small>({item.basis})</small></li>)}</ul>
                          )}
                          {[...commandResult.planning.assumptions, ...commandResult.planning.uncertainties].map((item, index) => <small key={`${item}-${index}`}>{item}</small>)}
                        </div>
                      )}
                      <button type="button" className="button button-secondary" disabled={commandBusy || Boolean(savedMessage)} onClick={() => void saveDraft()}>{commandBusy ? "Saving…" : "Save this proposed plan"}</button>
                    </>
                  )}
                </div>
              )}
            </section>
          </div>

          <section className="dashboard-support-grid">
            <article className="dashboard-support-card">
              <span className="eyebrow">WORKFLOW</span><h2>Pending approvals</h2>
              <strong className="dashboard-unavailable">{snapshot.capabilities.approvals ? "Available" : "Not available"}</strong>
              <p>{snapshot.capabilities.approvals ? "Approval records are available from the backend." : "There is no dashboard-wide approval queue. Recovery proposals are reviewed within each event’s Event Autopilot panel."}</p>
            </article>
            <article className="dashboard-support-card">
              <span className="eyebrow">MESSAGES</span><h2>Notifications</h2>
              <strong className="dashboard-unavailable">{snapshot.capabilities.notifications ? "Connected" : "Not connected"}</strong>
              <p>{snapshot.capabilities.notifications ? "Notifications are available from the backend." : "Invitations, reminders, cancellation notices, email, SMS and integration alerts are not sent or tracked."}</p>
            </article>
            <article className="dashboard-support-card dashboard-quick-card">
              <span className="eyebrow">SHORTCUTS</span><h2>Quick actions</h2>
              <button type="button" onClick={() => onNavigate("/create")}>Create event plan <span aria-hidden="true">→</span></button>
              <button type="button" onClick={() => onNavigate("/events")}>View saved events <span aria-hidden="true">→</span></button>
              <button type="button" onClick={() => onNavigate("/risks")}>Run scenario analysis <span aria-hidden="true">→</span></button>
            </article>
          </section>

          {latestEvents.length > 0 && (
            <section className="dashboard-recent">
              <div className="section-title-row"><div><span className="eyebrow">RECENT PLANS</span><h2>Latest activity</h2></div></div>
              <div className="dashboard-recent-list">
                {latestEvents.map(({ id, plan, created_at, status }) => (
                  <button type="button" className="dashboard-recent-row" key={id} onClick={() => onNavigate(`/events/${encodeURIComponent(id)}`)}>
                    <span className="activity-mark" aria-hidden="true">✳</span>
                    <span><strong>{plan.event.event_name}</strong><small>Created {new Date(created_at).toLocaleString()} · {formatDate(plan.event.event_date)}</small></span>
                    <span className={`dashboard-event-status status-${status}`}>{status.replaceAll("_", " ")}</span>
                    <span className="dashboard-recent-budget">{money(plan.budget_analysis.budget, plan.event.currency ?? "INR")}</span>
                  </button>
                ))}
              </div>
            </section>
          )}
        </>
      ) : (
        <div className="empty-card dashboard-empty" role={error ? "status" : undefined}>
          <span className="empty-art" aria-hidden="true">✳</span>
          <div><h3>{error ? "Dashboard data is unavailable" : "Your workspace starts here"}</h3><p>{error ? "The Dashboard could not load persisted plans and tasks. Retry to reconnect; no placeholder metrics are shown." : "No event plans or tasks have been saved yet. Create an event plan to see real budget, schedule and risk data here."}</p></div>
          {error ? <button className="button button-secondary" type="button" onClick={() => void onRefresh()}>Retry</button> : <button className="button button-primary" type="button" onClick={() => onNavigate("/create")}>Create your first plan <span aria-hidden="true">→</span></button>}
        </div>
      )}
    </div>
  );
}
