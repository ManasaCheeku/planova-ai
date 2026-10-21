import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  decideRecoveryProposal,
  generateEventWorkflow,
  getEventWorkflow,
  getRecoveryAIGuidance,
  getRecoveryCases,
  getWorkflowAIGuidance,
  proposeRecoveryOption,
  reportRecoveryCase,
  resolveRecoveryCase,
  updateDashboardTask,
} from "../api";
import type {
  CostCategory,
  RecoveryCase,
  RecoveryAIGuidance,
  RecoveryDisruption,
  WorkflowAIGuidance,
  WorkflowSnapshot,
  WorkflowTask,
} from "../types";

const disruptionLabels: Record<RecoveryDisruption, string> = {
  venue_cancellation: "Venue cancellation",
  vendor_cancellation: "Vendor cancellation",
  budget_change: "Budget change",
  guest_count_change: "Guest-count change",
  date_change: "Date or schedule change",
  delayed_task: "Delayed task",
  equipment_availability: "Equipment availability problem",
  catering_availability: "Catering availability problem",
  other: "Other disruption",
};

const money = (amount: number, currency: string) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(amount);

function displayDate(value: string | null) {
  if (!value) return "No due date";
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "The request could not be completed.";
}

interface EventAutopilotProps {
  eventId: string;
  eventName: string;
  guestCount: number | null | undefined;
  budget: number;
  currency: string;
  onEventChanged: () => Promise<boolean>;
}

export default function EventAutopilot({
  eventId,
  eventName,
  guestCount,
  budget,
  currency,
  onEventChanged,
}: EventAutopilotProps) {
  const [workflow, setWorkflow] = useState<WorkflowSnapshot | null>(null);
  const [cases, setCases] = useState<RecoveryCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [disruption, setDisruption] = useState<RecoveryDisruption>("venue_cancellation");
  const [description, setDescription] = useState("");
  const [changedBudget, setChangedBudget] = useState("");
  const [changedGuests, setChangedGuests] = useState("");
  const [changedDate, setChangedDate] = useState("");
  const [changedCostCategory, setChangedCostCategory] = useState<CostCategory>("catering");
  const [changedCostEstimate, setChangedCostEstimate] = useState("");
  const [delayedTaskId, setDelayedTaskId] = useState("");
  const [resolutionSummary, setResolutionSummary] = useState("");
  const [workflowGuidance, setWorkflowGuidance] = useState<WorkflowAIGuidance | null>(null);
  const [recoveryGuidance, setRecoveryGuidance] = useState<Record<string, RecoveryAIGuidance>>({});

  const reload = useCallback(async () => {
    setError("");
    try {
      const [nextWorkflow, nextCases] = await Promise.all([
        getEventWorkflow(eventId),
        getRecoveryCases(eventId),
      ]);
      setWorkflow(nextWorkflow);
      setCases(nextCases);
      return true;
    } catch (requestError) {
      setError(errorMessage(requestError));
      return false;
    } finally {
      setLoading(false);
    }
  }, [eventId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function generate() {
    setBusy("generate");
    setError("");
    setMessage("");
    try {
      setWorkflow(await generateEventWorkflow(eventId));
      await onEventChanged();
      setMessage("Workflow tasks are saved for this event.");
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy("");
    }
  }

  async function toggleTask(task: WorkflowTask) {
    setBusy(task.id);
    setError("");
    setMessage("");
    try {
      await updateDashboardTask(task.id, {
        status: task.status === "completed" ? "pending" : "completed",
      });
      await reload();
      await onEventChanged();
      setMessage(task.status === "completed" ? "Task reopened." : "Task marked complete.");
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy("");
    }
  }

  async function reportDisruption(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !description.trim()) return;
    setBusy("report");
    setError("");
    setMessage("");
    const changes: {
      budget?: number;
      guest_count?: number;
      event_date?: string;
      estimated_costs?: Partial<Record<CostCategory, number>>;
    } = {};
    if (changedBudget) changes.budget = Number(changedBudget);
    if (changedGuests) changes.guest_count = Number(changedGuests);
    if (changedDate) changes.event_date = changedDate;
    if (changedCostEstimate) {
      changes.estimated_costs = { [changedCostCategory]: Number(changedCostEstimate) };
    }
    try {
      const created = await reportRecoveryCase(eventId, {
        disruption_type: disruption,
        description: description.trim(),
        ...(disruption === "delayed_task" && delayedTaskId ? { task_id: delayedTaskId } : {}),
        ...(Object.keys(changes).length ? { changes } : {}),
      });
      setCases((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setDescription("");
      setChangedBudget("");
      setChangedGuests("");
      setChangedDate("");
      setDelayedTaskId("");
      setChangedCostEstimate("");
      setMessage("Disruption recorded. Review the evidence and recovery suggestions below.");
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy("");
    }

  }

  async function resolveCase(caseId: string) {
    if (!resolutionSummary.trim()) return;
    setBusy(`resolve:${caseId}`);
    setError("");
    setMessage("");
    try {
      const updated = await resolveRecoveryCase(caseId, resolutionSummary.trim());
      setCases((current) => current.map((item) => item.id === caseId ? updated : item));
      setResolutionSummary("");
      setMessage("Recovery case resolved and added to its activity history.");
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy("");
    }
  }

  async function selectOption(caseId: string, optionId: string) {
    setBusy(`${caseId}:${optionId}`);
    setError("");
    setMessage("");
    try {
      const updated = await proposeRecoveryOption(caseId, optionId);
      setCases((current) => current.map((item) => item.id === updated.id ? updated : item));
      setMessage("Proposal saved and is awaiting your review.");
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy("");
    }
  }

  async function decide(proposalId: string, decision: "approve" | "reject") {
    setBusy(proposalId);
    setError("");
    setMessage("");
    try {
      const proposal = await decideRecoveryProposal(proposalId, decision);
      await reload();
      if (decision === "approve") await onEventChanged();
      setMessage(
        proposal.result?.message ??
          (decision === "reject" ? "Proposal rejected; no plan change was applied." : "Proposal approved."),
      );
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy("");
    }
  }

  async function requestWorkflowGuidance() {
    setBusy("workflow-ai");
    setError("");
    try {
      setWorkflowGuidance(await getWorkflowAIGuidance(eventId));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy("");
    }
  }

  async function requestRecoveryGuidance(caseId: string) {
    setBusy(`recovery-ai:${caseId}`);
    setError("");
    try {
      const response = await getRecoveryAIGuidance(caseId);
      setRecoveryGuidance((current) => ({ ...current, [caseId]: response }));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy("");
    }
  }

  const taskNames = new Map(workflow?.tasks.map((task) => [task.id, task.title]) ?? []);

  return (
    <section id="event-autopilot" className="autopilot-card" aria-labelledby="autopilot-heading">
      <div className="autopilot-heading-row">
        <div>
          <span className="eyebrow">EVENT AUTOPILOT & RECOVERY</span>
          <h2 id="autopilot-heading">Plan the work. Recover with clarity.</h2>
          <p>Workflow tasks are suggestions based on this saved event plan; assignments and external actions are never assumed.</p>
        </div>
        <button className="button button-secondary" type="button" onClick={() => void reload()} disabled={loading || !!busy}>
          Refresh
        </button>
      </div>

      {error && <p className="autopilot-feedback autopilot-error" role="alert">{error}</p>}
      {message && <p className="autopilot-feedback" role="status">{message}</p>}
      {loading ? (
        <p className="autopilot-empty" role="status">Loading workflow and recovery history…</p>
      ) : (
        <>
          <div className="autopilot-disclosure">
            <strong>{workflow?.ai_model_configured ? "Deterministic workflow · optional GenAI guidance" : "Deterministic assistance only"}</strong>
            <span>{workflow?.notice ?? "No GenAI provider is configured. No external integration is connected."}</span>
          </div>

          <div className="autopilot-progress">
            <div><span>Workflow progress</span><strong>{workflow?.tasks.filter((task) => task.status === "completed").length ?? 0} / {workflow?.tasks.length ?? 0} complete</strong></div>
            <div><span>Overdue</span><strong>{workflow?.overdue_count ?? 0}</strong></div>
            <div><span>Blocked / missing information</span><strong>{workflow?.blocked_count ?? 0}</strong></div>
          </div>

          <div className="autopilot-next-action">
            <span className="eyebrow">RECOMMENDED NEXT ACTION</span>
            <strong>{workflow?.next_action ?? "No unblocked pending task is available."}</strong>
            <small>Recommendation is derived from current task status, dependencies, dates, and saved event inputs.</small>
            <button
              className="button button-secondary autopilot-ai-button"
              type="button"
              disabled={!!busy || !workflow?.ai_model_configured}
              title={workflow?.ai_model_configured ? undefined : "Configure OPENAI_API_KEY on the backend to enable GenAI guidance."}
              onClick={() => void requestWorkflowGuidance()}
            >
              {busy === "workflow-ai" ? "Generating explanation…" : "Explain blockers with GenAI"}
            </button>
            {!workflow?.ai_model_configured && <small>Unavailable until a backend GenAI key is configured.</small>}
            {workflowGuidance?.guidance && (
              <div className="autopilot-ai-guidance" aria-live="polite">
                <p>{workflowGuidance.guidance.explanation}</p>
                {workflowGuidance.guidance.next_action && <small>Allowed next task: {workflowGuidance.guidance.next_action}</small>}
                {workflowGuidance.guidance.reasons.length > 0 && <ul>{workflowGuidance.guidance.reasons.map((reason, index) => <li key={`${reason}-${index}`}>{reason}</li>)}</ul>}
                {workflowGuidance.guidance.evidence_gaps.length > 0 && <small>Evidence gaps: {workflowGuidance.guidance.evidence_gaps.join(" · ")}</small>}
                <small>{workflowGuidance.notice}</small>
              </div>
            )}
          </div>

          {workflow?.tasks.length ? (
            <ol className="autopilot-task-list">
              {workflow.tasks.map((task) => (
                <li key={task.id} className={`autopilot-task${task.blockers.length ? " autopilot-task-blocked" : ""}${task.overdue ? " autopilot-task-overdue" : ""}`}>
                  <div className="autopilot-task-main">
                    <span className={`autopilot-priority priority-${task.priority}`}>{task.priority}</span>
                    <div>
                      <strong>{task.title}</strong>
                      <p>{task.description}</p>
                      <small>{task.completion_criteria}</small>
                    </div>
                    <span className="autopilot-task-date">{task.overdue ? "Overdue · " : ""}{displayDate(task.due_date)}</span>
                    <button
                      type="button"
                      className="dashboard-small-action"
                      disabled={!!busy || (task.status === "pending" && task.blockers.length > 0)}
                      title={task.blockers.length ? task.blockers.join(" ") : undefined}
                      onClick={() => void toggleTask(task)}
                      aria-label={`${task.status === "completed" ? "Reopen" : "Mark complete"} ${task.title}`}
                    >
                      {busy === task.id ? "Saving…" : task.status === "completed" ? "Reopen" : "Complete"}
                    </button>
                  </div>
                  <div className="autopilot-task-meta">
                    <span>{task.assigned_to ? `Assigned to ${task.assigned_to}` : "Unassigned"}</span>
                    {task.estimated_cost !== null && <span>Supplied estimate: {money(task.estimated_cost, currency)}</span>}
                    {task.dependencies.length > 0 && <span>Depends on: {task.dependencies.map((id) => taskNames.get(id) ?? "Missing dependency").join(", ")}</span>}
                    {task.blocks.length > 0 && <span>Blocks: {task.blocks.join(", ")}</span>}
                    {task.information_needed.length > 0 && <span>Information to confirm: {task.information_needed.join(" ")}</span>}
                  </div>
                  {task.blockers.length > 0 && (
                    <ul className="autopilot-blockers">
                      {task.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
                    </ul>
                  )}
                </li>
              ))}
            </ol>
          ) : (
            <div className="autopilot-empty">
              <p>No execution tasks have been generated for {eventName}.</p>
              <button className="button button-primary" type="button" onClick={() => void generate()} disabled={!!busy}>
                {busy === "generate" ? "Generating…" : "Generate workflow"}
              </button>
            </div>
          )}

          {!!workflow?.unresolved_event_risks.length && (
            <div className="autopilot-risks">
              <strong>Current plan risks to review</strong>
              <ul>{workflow.unresolved_event_risks.map((risk) => <li key={risk}>{risk}</li>)}</ul>
            </div>
          )}

          <div className="autopilot-recovery">
            <div>
              <span className="eyebrow">RESCUE MODE</span>
              <h3>Report a disruption</h3>
              <p>Record user-reported facts. Suggested alternatives need verification and are not bookings.</p>
            </div>
            <form className="autopilot-recovery-form" onSubmit={(event) => void reportDisruption(event)}>
              <label>
                <span>Disruption type</span>
                <select value={disruption} onChange={(event) => setDisruption(event.target.value as RecoveryDisruption)}>
                  {Object.entries(disruptionLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                </select>
              </label>
              {disruption === "delayed_task" && (
                <label>
                  <span>Delayed task</span>
                  <select value={delayedTaskId} onChange={(event) => setDelayedTaskId(event.target.value)}>
                    <option value="">Match reported delay to overdue tasks</option>
                    {workflow?.tasks.filter((task) => task.status === "pending").map((task) => (
                      <option value={task.id} key={task.id}>{task.title}</option>
                    ))}
                  </select>
                </label>
              )}
              <label className="autopilot-description-field">
                <span>What changed? Include only confirmed details.</span>
                <textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={1000} required placeholder="Describe the reported disruption and what is confirmed so far." />
              </label>
              <div className="autopilot-change-inputs">
                <label><span>Proposed total budget (₹)</span><input type="number" min="0.01" step="0.01" value={changedBudget} onChange={(event) => setChangedBudget(event.target.value)} placeholder={String(budget)} /></label>
                <label><span>Proposed guest count</span><input type="number" min="1" step="1" value={changedGuests} onChange={(event) => setChangedGuests(event.target.value)} placeholder={guestCount ? String(guestCount) : "Not supplied"} /></label>
                <label><span>Proposed event date</span><input type="date" value={changedDate} onChange={(event) => setChangedDate(event.target.value)} /></label>
              </div>
              <div className="autopilot-change-inputs">
                <label><span>Revised estimate category</span><select value={changedCostCategory} onChange={(event) => setChangedCostCategory(event.target.value as CostCategory)}>
                  {(["venue", "catering", "production", "staffing", "equipment", "activities", "contingency", "other"] as const).map((category) => <option value={category} key={category}>{category}</option>)}
                </select></label>
                <label><span>Revised known estimate (₹)</span><input type="number" min="0" step="0.01" value={changedCostEstimate} onChange={(event) => setChangedCostEstimate(event.target.value)} placeholder="Optional" /></label>
              </div>
              <p className="autopilot-form-note">Optional changes are compared with this saved plan. Only supplied amounts are used; unknown costs remain unknown.</p>
              <button className="button button-primary" type="submit" disabled={!!busy || !description.trim()}>
                {busy === "report" ? "Analyzing…" : "Record disruption & compare"}
              </button>
            </form>
          </div>

          <div className="autopilot-cases">
            <div className="section-title-row"><div><span className="eyebrow">PERSISTED RECOVERY CASES</span><h3>Case history</h3></div></div>
            {cases.length === 0 ? (
              <p className="autopilot-empty">No disruptions have been reported for this event.</p>
            ) : cases.map((item) => (
              <article className="recovery-case" key={item.id}>
                <div className="recovery-case-heading">
                  <div><span className="eyebrow">{disruptionLabels[item.disruption_type]} · USER REPORTED</span><h4>{item.description}</h4></div>
                  <span className="recovery-case-status">{item.status}</span>
                </div>
                <div className="recovery-impact-grid">
                  <span>Known budget <strong>{money(item.impact.known_budget_inr, currency)}</strong></span>
                  <span>Known estimates <strong>{money(item.impact.known_expenses_inr, currency)}</strong></span>
                  <span>Remaining vs known estimates <strong>{money(item.impact.known_remaining_budget_inr, currency)}</strong></span>
                  {item.impact.scenario_comparison && <span>Known estimate change <strong>{money(item.impact.scenario_comparison.budget_impact.known_expenses_change, currency)}</strong></span>}
                  <span>Estimated overrun <strong>{money(item.impact.estimated_overrun_inr, currency)}{item.impact.estimated_overrun_percent === null ? "" : ` · ${item.impact.estimated_overrun_percent}%`}</strong></span>
                  {item.impact.scenario_estimated_overrun_inr !== null && <span>Scenario overrun <strong>{money(item.impact.scenario_estimated_overrun_inr, currency)}</strong></span>}
                </div>
                <p className="autopilot-form-note">
                  <strong>Budget basis:</strong> {item.impact.budget_assessment === "partial" ? `Partial; unestimated categories remain unknown (${item.impact.missing_cost_categories.join(", ")}).` : "Calculated from supplied estimates."}
                  Actual expenditure is not tracked.
                </p>
                <button
                  className="button button-secondary autopilot-ai-button"
                  type="button"
                  disabled={!!busy || !workflow?.ai_model_configured}
                  title={workflow?.ai_model_configured ? undefined : "Configure OPENAI_API_KEY on the backend to enable GenAI recovery guidance."}
                  onClick={() => void requestRecoveryGuidance(item.id)}
                >
                  {busy === `recovery-ai:${item.id}` ? "Reviewing case…" : recoveryGuidance[item.id]?.guidance ? "Refresh AI recovery suggestions" : "Get AI recovery suggestions"}
                </button>
                {recoveryGuidance[item.id]?.guidance && (
                  <div className="autopilot-ai-guidance" aria-live="polite">
                    <strong>Advisory only · not a proposal or confirmed alternative</strong>
                    <p>{recoveryGuidance[item.id].guidance!.summary}</p>
                    {recoveryGuidance[item.id].guidance!.suggestions.map((suggestion, index) => (
                      <div key={`${suggestion.title}-${index}`}>
                        <strong>{suggestion.title}</strong>
                        <p>{suggestion.suggestion}</p>
                        {[...suggestion.tradeoffs, ...suggestion.assumptions, ...suggestion.evidence_to_verify].map((note, noteIndex) => <small key={`${note}-${noteIndex}`}>{note}</small>)}
                      </div>
                    ))}
                    <small>{recoveryGuidance[item.id].notice} Use only the supported options below to create a persisted proposal for approval.</small>
                  </div>
                )}
                {item.impact.overrun_categories.length > 0 && (
                  <div className="autopilot-risks">
                    <strong>Known estimate categories contributing to overrun</strong>
                    <ul>{item.impact.overrun_categories.map((category) => <li key={category}>{category}: {money(item.impact.overrun_breakdown_inr[category] ?? 0, currency)} known estimate</li>)}</ul>
                  </div>
                )}
                {item.impact.scenario_comparison && (
                  <div className="recovery-scenario-details">
                    <strong>Scenario comparison and trade-offs</strong>
                    <ul>
                      {item.impact.scenario_comparison.recommendations.map((recommendation) => <li key={recommendation}>{recommendation}</li>)}
                      {item.impact.scenario_comparison.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}
                    </ul>
                    <div className="recovery-impact-grid">
                      {Object.keys(item.impact.scenario_comparison.scenario_plan.budget_analysis.estimated_costs)
                        .filter((category) => {
                          const original = item.impact.scenario_comparison?.original_plan.budget_analysis.estimated_costs[category as CostCategory];
                          const revised = item.impact.scenario_comparison?.scenario_plan.budget_analysis.estimated_costs[category as CostCategory];
                          return original !== revised;
                        })
                        .map((category) => {
                          const original = item.impact.scenario_comparison?.original_plan.budget_analysis.estimated_costs[category as CostCategory];
                          const revised = item.impact.scenario_comparison?.scenario_plan.budget_analysis.estimated_costs[category as CostCategory];
                          return <span key={category}>{category}: {original === undefined ? "Unknown" : money(original, currency)} → {revised === undefined ? "Unknown" : money(revised, currency)}</span>;
                        })}
                    </div>
                  </div>
                )}
                <p className="autopilot-form-note"><strong>User-reported, not independently verified:</strong> {item.impact.user_reported_facts.join(" ")}</p>
                <p className="autopilot-form-note"><strong>Independently confirmed facts:</strong> {item.impact.confirmed_facts.length ? item.impact.confirmed_facts.join(" ") : "None; no trusted integration is configured."}</p>
                {!!item.impact.affected_tasks.length && <p className="autopilot-form-note"><strong>Affected pending tasks:</strong> {item.impact.affected_tasks.join(", ")}</p>}
                <div className="recovery-options">
                  {item.options.map((option) => (
                    <article className="recovery-option" key={option.id}>
                      <div className="recovery-option-heading">
                        <h5>{option.title}</h5>
                        <span>{option.readiness === "ready_for_review" ? "Calculated · approval required" : "Suggestion · verify first"}</span>
                      </div>
                      <p>{option.description}</p>
                      <div className="recovery-option-metrics">
                        <span>Known cost change: {option.cost_change === null ? "Unknown" : money(option.cost_change, currency)}</span>
                        <span>Projected known cost: {money(option.projected_known_cost_inr, currency)}</span>
                        <span>Projected overrun vs {money(option.approved_budget_inr, currency)} budget: {money(option.projected_overrun_inr, currency)}</span>
                        <span>Timing change: {option.timing_change_days === null ? "Unknown" : `${option.timing_change_days} days`}</span>
                      </div>
                      {!!option.affected_tasks.length && <small><strong>Affected tasks:</strong> {option.affected_tasks.join(", ")}</small>}
                      {!!option.unresolved_risks.length && <small><strong>Outstanding risks:</strong> {option.unresolved_risks.join(", ")}</small>}
                      <small>{option.cost_basis}</small>
                      {option.uncertainties.map((uncertainty) => <small className="recovery-uncertainty" key={uncertainty}>{uncertainty}</small>)}
                      <button
                        className="button button-secondary"
                        type="button"
                        disabled={!!busy || item.status === "resolved" || item.proposals.some((proposal) => proposal.option_id === option.id && proposal.status !== "rejected")}
                        onClick={() => void selectOption(item.id, option.id)}
                      >
                        {busy === `${item.id}:${option.id}` ? "Saving…" : "Propose this option"}
                      </button>
                    </article>
                  ))}
                </div>
                {!!item.proposals.length && (
                  <div className="recovery-review">
                    <strong>Review and approval</strong>
                    {item.proposals.map((proposal) => {
                      const option = item.options.find((candidate) => candidate.id === proposal.option_id);
                      return (
                        <div className="recovery-proposal" key={proposal.id}>
                          <span>{option?.title ?? "Recovery option"} · <strong>{proposal.status}</strong></span>
                          {proposal.status === "proposed" ? (
                            <div className="recovery-review-actions">
                              <button type="button" className="button button-primary" disabled={!!busy} onClick={() => void decide(proposal.id, "approve")}>
                                {busy === proposal.id ? "Applying…" : Object.keys(proposal.proposed_change).length ? "Approve & apply local change" : "Approve recommendation"}
                              </button>
                              <button type="button" className="button button-secondary" disabled={!!busy} onClick={() => void decide(proposal.id, "reject")}>Reject</button>
                            </div>
                          ) : (
                            <>
                              <p>{proposal.result?.message ?? "No external action was executed."}</p>
                              {!!proposal.result?.remaining_blockers.length && <ul className="autopilot-blockers">{proposal.result.remaining_blockers.map((blocker) => <li key={`${blocker.title}-${blocker.reason}`}>{blocker.title}: {blocker.reason}</li>)}</ul>}
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
                <details className="recovery-activity">
                  <summary>Activity history ({item.activity.length})</summary>
                  <ol>{item.activity.map((entry) => <li key={entry.id}><time>{new Date(entry.created_at).toLocaleString()}</time> · {entry.action.replaceAll("_", " ")} · {entry.details}</li>)}</ol>
                </details>
                {item.status === "open" && (
                  <div className="recovery-resolve">
                    <label>
                      <span>Resolution summary (include remaining blockers)</span>
                      <input value={resolutionSummary} onChange={(event) => setResolutionSummary(event.target.value)} maxLength={1000} placeholder="What was verified or changed? What remains open?" />
                    </label>
                    <button type="button" className="button button-secondary" disabled={!!busy || !resolutionSummary.trim() || item.proposals.some((proposal) => proposal.status === "proposed")} title={item.proposals.some((proposal) => proposal.status === "proposed") ? "Decide all pending proposals before resolving." : undefined} onClick={() => void resolveCase(item.id)}>
                      {busy === `resolve:${item.id}` ? "Saving…" : "Mark recovery case resolved"}
                    </button>
                  </div>
                )}
                {item.resolution && <p className="autopilot-form-note"><strong>Resolution:</strong> {item.resolution}</p>}
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
