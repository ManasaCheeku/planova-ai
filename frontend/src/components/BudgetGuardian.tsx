import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  createBudgetProposal,
  createEventExpense,
  decideBudgetProposal,
  getBudgetAIGuidance,
  getEventBudget,
  updateEventExpense,
} from "../api";
import type {
  BudgetChangeRequest,
  BudgetSummary,
  CostCategory,
  EventExpense,
} from "../types";

interface BudgetGuardianProps {
  eventId: string;
  onEventChanged: () => Promise<boolean>;
}

const categories: CostCategory[] = [
  "venue",
  "catering",
  "decoration",
  "photography",
  "entertainment",
  "equipment",
  "transport",
  "accommodation",
  "invitations",
  "production",
  "staffing",
  "activities",
  "contingency",
  "miscellaneous",
  "other",
];

const labels: Record<CostCategory, string> = {
  venue: "Venue",
  catering: "Catering",
  production: "Production",
  staffing: "Staffing",
  equipment: "Equipment",
  activities: "Activities",
  decoration: "Decoration",
  photography: "Photography",
  entertainment: "Entertainment",
  transport: "Transport",
  accommodation: "Accommodation",
  invitations: "Invitations",
  contingency: "Contingency",
  miscellaneous: "Miscellaneous",
  other: "Other",
};

function newIdempotencyKey() {
  return crypto.randomUUID();
}

function localDate() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
}

function formatMoney(amount: number | null, currency: string) {
  if (amount === null) return "Not available";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(amount);
}

function messageFrom(error: unknown) {
  return error instanceof Error ? error.message : "The budget request failed. Please try again.";
}

export default function BudgetGuardian({
  eventId,
  onEventChanged,
}: BudgetGuardianProps) {
  const [summary, setSummary] = useState<BudgetSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [expenseCategory, setExpenseCategory] = useState<CostCategory>("venue");
  const [expenseAmount, setExpenseAmount] = useState("");
  const [expenseDate, setExpenseDate] = useState(localDate);
  const [expenseDescription, setExpenseDescription] = useState("");
  const [expenseVendor, setExpenseVendor] = useState("");
  const [paymentStatus, setPaymentStatus] = useState<"committed" | "paid">("committed");
  const [editingExpense, setEditingExpense] = useState<EventExpense | null>(null);
  const [expenseKey, setExpenseKey] = useState(newIdempotencyKey);
  const [proposalKind, setProposalKind] = useState<"budget" | "allocation">("budget");
  const [proposalCategory, setProposalCategory] = useState<CostCategory>("venue");
  const [proposalAmount, setProposalAmount] = useState("");
  const [proposalRationale, setProposalRationale] = useState("");
  const [proposalKey, setProposalKey] = useState(newIdempotencyKey);
  const [guidanceBusy, setGuidanceBusy] = useState(false);
  const [guidance, setGuidance] = useState<{
    notice: string;
    explanation: string | null;
    suggestions: string[];
    evidenceGaps: string[];
  } | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setSummary(await getEventBudget(eventId));
    } catch (loadError) {
      setError(messageFrom(loadError));
    } finally {
      setLoading(false);
    }
  }, [eventId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  function resetExpenseForm() {
    setEditingExpense(null);
    setExpenseCategory("venue");
    setExpenseAmount("");
    setExpenseDate(localDate());
    setExpenseDescription("");
    setExpenseVendor("");
    setPaymentStatus("committed");
  }

  function beginEdit(expense: EventExpense) {
    setEditingExpense(expense);
    setExpenseCategory(expense.category);
    setExpenseAmount(String(expense.amount));
    setExpenseDate(expense.expense_date);
    setExpenseDescription(expense.description);
    setExpenseVendor(expense.vendor_name ?? "");
    setPaymentStatus(expense.payment_status);
    setSuccess("");
    setError("");
  }

  async function submitExpense(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const amount = Number(expenseAmount);
      if (!Number.isFinite(amount) || amount <= 0) {
        throw new Error("Enter a positive amount.");
      }
      if (editingExpense) {
        await updateEventExpense(eventId, editingExpense.id, {
          category: expenseCategory,
          amount,
          expense_date: expenseDate,
          description: expenseDescription.trim(),
          payment_status: paymentStatus,
          vendor_name: expenseVendor.trim() || null,
        });
        setSuccess("Recorded expense updated.");
      } else {
        await createEventExpense(eventId, {
          category: expenseCategory,
          amount,
          expense_date: expenseDate,
          description: expenseDescription.trim(),
          payment_status: paymentStatus,
          ...(expenseVendor.trim() ? { vendor_name: expenseVendor.trim() } : {}),
          idempotency_key: expenseKey,
        });
        setExpenseKey(newIdempotencyKey());
        setSuccess("Expense recorded from your input.");
      }
      resetExpenseForm();
      await reload();
    } catch (submitError) {
      setError(messageFrom(submitError));
    } finally {
      setBusy(false);
    }
  }

  async function submitProposal(changes: BudgetChangeRequest, rationale: string) {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await createBudgetProposal(eventId, {
        changes,
        rationale,
        idempotency_key: proposalKey,
      });
      setProposalKey(newIdempotencyKey());
      setProposalAmount("");
      setProposalRationale("");
      setSuccess("Change proposed. The saved plan is unchanged until you approve it below.");
      await reload();
    } catch (proposalError) {
      setError(messageFrom(proposalError));
    } finally {
      setBusy(false);
    }
  }

  async function submitManualProposal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const amount = Number(proposalAmount);
    if (!Number.isFinite(amount) || amount < 0) {
      setError("Enter a valid non-negative amount.");
      return;
    }
    const changes: BudgetChangeRequest =
      proposalKind === "budget"
        ? { budget: amount }
        : { category_allocations: { [proposalCategory]: amount } };
    await submitProposal(changes, proposalRationale.trim());
  }

  async function approveRecommendation(
    category: CostCategory,
    estimated: number,
    rationale: string,
  ) {
    await submitProposal(
      { estimated_costs: { [category]: estimated } },
      rationale,
    );
  }

  async function decideProposal(
    proposalId: string,
    decision: "approve" | "reject",
  ) {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await decideBudgetProposal(proposalId, decision);
      setSuccess(
        decision === "approve"
          ? "Proposal approved and applied to the saved event plan."
          : "Proposal rejected. The saved event plan was not changed.",
      );
      await Promise.all([reload(), onEventChanged()]);
    } catch (decisionError) {
      setError(messageFrom(decisionError));
    } finally {
      setBusy(false);
    }
  }

  async function requestGuidance() {
    setGuidanceBusy(true);
    setError("");
    setGuidance(null);
    try {
      const result = await getBudgetAIGuidance(eventId);
      setGuidance({
        notice: result.notice,
        explanation: result.guidance?.explanation ?? null,
        suggestions: result.guidance?.suggestions ?? [],
        evidenceGaps: result.guidance?.evidence_gaps ?? [],
      });
    } catch (guidanceError) {
      setError(messageFrom(guidanceError));
    } finally {
      setGuidanceBusy(false);
    }
  }

  return (
    <section className="budget-guardian" aria-labelledby="budget-guardian-title">
      <div className="budget-guardian-heading">
        <div>
          <span className="eyebrow">SMART BUDGET GUARDIAN</span>
          <h2 id="budget-guardian-title">Track planned and recorded costs</h2>
          <p>Estimates are not actual spending. Recorded amounts come from expense entries you provide.</p>
        </div>
        <button className="button button-secondary" type="button" onClick={() => void reload()} disabled={loading || busy}>
          Refresh figures
        </button>
      </div>

      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {success && <div className="budget-success" role="status">{success}</div>}
      {loading && !summary ? (
        <div className="budget-loading" role="status"><span className="spinner" /> Loading saved budget data…</div>
      ) : summary ? (
        <>
          <div className="budget-metrics">
            <article><span>Approved budget</span><strong>{formatMoney(summary.approved_budget, summary.currency)}</strong><small>{summary.currency} · saved plan</small></article>
            <article><span>Estimated costs</span><strong>{formatMoney(summary.estimated_total, summary.currency)}</strong><small>Forecast only, not paid</small></article>
            <article><span>Committed</span><strong>{formatMoney(summary.committed_total, summary.currency)}</strong><small>Recorded commitments</small></article>
            <article><span>Paid</span><strong>{formatMoney(summary.paid_total, summary.currency)}</strong><small>Manually recorded payments</small></article>
            <article><span>Remaining available</span><strong>{formatMoney(summary.remaining_available, summary.currency)}</strong><small>Budget less committed and paid</small></article>
            <article className={summary.projected_overrun && summary.projected_overrun > 0 ? "budget-metric-warning" : ""}>
              <span>Known projected total</span>
              <strong>{formatMoney(summary.projected_total, summary.currency)}</strong>
              <small>
                {summary.projected_overrun === null
                  ? "Insufficient cost information"
                  : summary.projected_overrun > 0
                    ? `${formatMoney(summary.projected_overrun, summary.currency)} projected over${summary.overrun_percent === null ? "" : ` · ${summary.overrun_percent}% of budget`}`
                    : "No projected overrun in known costs"}
              </small>
            </article>
          </div>
          <div className="budget-data-note">
            {summary.assessment === "partial"
              ? `Partial assessment. No estimate or expense record is available for: ${summary.missing_cost_categories.map((item) => labels[item]).join(", ")}.`
              : "Cost information is present for all categories in the saved event plan."}
            {" "}Projections use the greater of each category estimate or its recorded committed-plus-paid total to avoid double counting.
          </div>

          <div className="budget-columns">
            <section className="budget-panel" aria-labelledby="budget-categories-title">
              <div className="budget-panel-heading"><div><span className="eyebrow">ALLOCATION MONITOR</span><h3 id="budget-categories-title">Category utilization</h3></div></div>
              <div className="budget-category-list">
                {summary.categories.map((item) => (
                  <article className="budget-category" key={item.category}>
                    <div className="budget-category-heading">
                      <strong>{labels[item.category]}</strong>
                      <span>{formatMoney(item.projected, summary.currency)} / {formatMoney(item.allocation, summary.currency)}</span>
                    </div>
                    <div className="budget-utilization-track" role="img" aria-label={`${labels[item.category]}: ${item.utilization_percent === null ? "no projected utilization" : `${item.utilization_percent}% of allocation`}`}>
                      <span className={item.utilization_percent !== null && item.utilization_percent > 100 ? "over-limit" : ""} style={{ width: `${Math.min(100, Math.max(0, item.utilization_percent ?? 0))}%` }} />
                    </div>
                    <small>
                      {item.missing_estimate
                        ? "No estimate or expense recorded"
                        : `Estimated ${formatMoney(item.estimated, summary.currency)} · committed ${formatMoney(item.committed, summary.currency)} · paid ${formatMoney(item.paid, summary.currency)}`}
                    </small>
                  </article>
                ))}
                {summary.categories.length === 0 && <p className="muted-copy">No category allocations are available in this saved plan.</p>}
              </div>
            </section>

            <section className="budget-panel" aria-labelledby="budget-alerts-title">
              <div className="budget-panel-heading"><div><span className="eyebrow">MONITORING</span><h3 id="budget-alerts-title">Warnings &amp; evidence</h3></div></div>
              {summary.alerts.length ? (
                <div className="budget-alert-list">
                  {summary.alerts.map((alert) => (
                    <article className={`budget-alert budget-alert-${alert.severity}`} key={alert.id}>
                      <strong>{alert.title}</strong><p>{alert.explanation}</p>
                    </article>
                  ))}
                </div>
              ) : <p className="muted-copy">No budget warnings from the current saved figures.</p>}
              {summary.assumptions.map((assumption) => <p className="budget-assumption" key={assumption}>{assumption}</p>)}
              <a className="text-link budget-autopilot-link" href="#event-autopilot">Report a budget disruption in Event Autopilot <span aria-hidden="true">↓</span></a>
            </section>
          </div>

          <div className="budget-columns">
            <section className="budget-panel" aria-labelledby="expense-list-title">
              <div className="budget-panel-heading"><div><span className="eyebrow">USER-RECORDED LEDGER</span><h3 id="expense-list-title">Expenses &amp; commitments</h3></div></div>
              {summary.expenses.length ? (
                <div className="budget-expense-list">
                  {summary.expenses.map((expense) => (
                    <article className="budget-expense" key={expense.id}>
                      <div><strong>{expense.description}</strong><small>{labels[expense.category]} · {expense.expense_date}{expense.vendor_name ? ` · ${expense.vendor_name}` : ""}</small></div>
                      <div className="budget-expense-value"><strong>{formatMoney(expense.amount, summary.currency)}</strong><small>{expense.payment_status}</small></div>
                      <button type="button" className="text-link" onClick={() => beginEdit(expense)} disabled={busy}>Edit</button>
                    </article>
                  ))}
                </div>
              ) : <p className="muted-copy">No expense or commitment entries have been recorded for this event.</p>}
              <form className="budget-form" onSubmit={(event) => void submitExpense(event)}>
                <h4>{editingExpense ? "Edit recorded item" : "Record an expense or commitment"}</h4>
                <p className="budget-form-note">Enter reliable amounts you know. Marking an item paid updates that same record; it does not add a second expense.</p>
                <div className="budget-form-grid">
                  <label className="field"><span>Category</span><select value={expenseCategory} onChange={(event) => setExpenseCategory(event.target.value as CostCategory)}>{categories.map((category) => <option key={category} value={category}>{labels[category]}</option>)}</select></label>
                  <label className="field"><span>Amount ({summary.currency})</span><input type="number" min="0.01" step="0.01" value={expenseAmount} onChange={(event) => setExpenseAmount(event.target.value)} required /></label>
                  <label className="field"><span>Date</span><input type="date" value={expenseDate} max={localDate()} onChange={(event) => setExpenseDate(event.target.value)} required /></label>
                  <label className="field"><span>Status</span><select value={paymentStatus} onChange={(event) => setPaymentStatus(event.target.value as "committed" | "paid")}><option value="committed">Committed, not paid</option><option value="paid">Paid</option></select></label>
                  <label className="field"><span>Description</span><input value={expenseDescription} onChange={(event) => setExpenseDescription(event.target.value)} maxLength={500} required /></label>
                  <label className="field"><span>Vendor (optional)</span><input value={expenseVendor} onChange={(event) => setExpenseVendor(event.target.value)} maxLength={160} /></label>
                </div>
                <div className="budget-form-actions">
                  <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : editingExpense ? "Save expense changes" : "Record item"}</button>
                  {editingExpense && <button className="button button-secondary" type="button" onClick={resetExpenseForm} disabled={busy}>Cancel edit</button>}
                </div>
              </form>
            </section>

            <section className="budget-panel" aria-labelledby="budget-recommendations-title">
              <div className="budget-panel-heading">
                <div><span className="eyebrow">COST CONTROL</span><h3 id="budget-recommendations-title">Review possible changes</h3></div>
                <button className="text-link" type="button" onClick={() => void requestGuidance()} disabled={guidanceBusy}>{guidanceBusy ? "Thinking…" : "Ask GenAI to explain"}</button>
              </div>
              {summary.recommendations.length ? (
                <div className="budget-recommendation-list">
                  {summary.recommendations.map((recommendation) => {
                    const change = recommendation.proposed_changes?.estimated_costs;
                    const category = change ? Object.keys(change)[0] as CostCategory : null;
                    const estimate = category && change ? change[category] : undefined;
                    return (
                      <article className="budget-recommendation" key={recommendation.id}>
                        <strong>{recommendation.issue}</strong>
                        <p>{recommendation.proposed_change}</p>
                        <p>{recommendation.savings_basis}</p>
                        <p><b>Trade-off:</b> {recommendation.tradeoffs.join(" ")}</p>
                        {recommendation.uncertainty.map((item) => <small key={item}>{item}</small>)}
                        <div className="budget-recommendation-footer">
                          <span>Potential scenario savings: {formatMoney(recommendation.estimated_savings, summary.currency)}</span>
                          {category && estimate !== undefined && (
                            <button className="button button-secondary" type="button" disabled={busy} onClick={() => void approveRecommendation(category, estimate, `Review estimate for ${labels[category]}; generated from recorded budget figures.`)}>Propose estimate change</button>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : <p className="muted-copy">No deterministic estimate-review recommendation is supported by the current data.</p>}
              {guidance && (
                <div className="budget-ai-guidance" role="status">
                  <strong>{guidance.explanation ? "GenAI explanation" : "GenAI unavailable"}</strong>
                  {guidance.explanation && <p>{guidance.explanation}</p>}
                  {guidance.suggestions.map((suggestion) => <p key={suggestion}>{suggestion}</p>)}
                  {guidance.evidenceGaps.map((gap) => <small key={gap}>Evidence gap: {gap}</small>)}
                  <small>{guidance.notice}</small>
                </div>
              )}
              <form className="budget-form budget-proposal-form" onSubmit={(event) => void submitManualProposal(event)}>
                <h4>Propose a budget plan change</h4>
                <div className="budget-form-grid">
                  <label className="field"><span>Change type</span><select value={proposalKind} onChange={(event) => setProposalKind(event.target.value as "budget" | "allocation")}><option value="budget">Approved budget</option><option value="allocation">Category allocation</option></select></label>
                  {proposalKind === "allocation" && <label className="field"><span>Category</span><select value={proposalCategory} onChange={(event) => setProposalCategory(event.target.value as CostCategory)}>{categories.map((category) => <option key={category} value={category}>{labels[category]}</option>)}</select></label>}
                  <label className="field"><span>{proposalKind === "budget" ? `New budget (${summary.currency})` : `New allocation (${summary.currency})`}</span><input type="number" min="0" step="0.01" value={proposalAmount} onChange={(event) => setProposalAmount(event.target.value)} required /></label>
                  <label className="field"><span>Reason for proposal</span><input value={proposalRationale} onChange={(event) => setProposalRationale(event.target.value)} maxLength={500} required /></label>
                </div>
                <p className="budget-form-note">Proposals do not change the event until explicitly approved. Essential requirements remain part of the event plan.</p>
                <button className="button button-secondary" type="submit" disabled={busy}>{busy ? "Saving…" : "Create proposal for review"}</button>
              </form>
            </section>
          </div>

          <section className="budget-panel" aria-labelledby="budget-proposals-title">
            <div className="budget-panel-heading"><div><span className="eyebrow">APPROVAL REQUIRED</span><h3 id="budget-proposals-title">Proposed changes</h3></div></div>
            {summary.proposals.length ? (
              <div className="budget-proposal-list">
                {summary.proposals.map((proposal) => (
                  <article className="budget-proposal" key={proposal.id}>
                    <div>
                      <strong>{proposal.rationale}</strong>
                      <small>Status: {proposal.status}</small>
                      <div className="budget-proposal-preview">
                        <span>Current projected: {formatMoney(proposal.preview.current.projected_total, proposal.preview.currency)}</span>
                        <span>Proposed projected: {formatMoney(proposal.preview.proposed.projected_total, proposal.preview.currency)}</span>
                        <span>Budget change: {formatMoney(proposal.preview.budget_change, proposal.preview.currency)}</span>
                        <span>Projected cost change: {formatMoney(proposal.preview.projected_cost_change, proposal.preview.currency)}</span>
                        <span>Affected categories: {proposal.preview.affected_categories.map((category) => labels[category]).join(", ") || "None specified"}</span>
                      </div>
                      {proposal.preview.tradeoffs.map((tradeoff) => <small key={tradeoff}>{tradeoff}</small>)}
                      <pre>{JSON.stringify(proposal.proposed_changes, null, 2)}</pre>
                    </div>
                    {proposal.status === "proposed" && (
                      <div className="budget-form-actions">
                        <button className="button button-primary" type="button" onClick={() => void decideProposal(proposal.id, "approve")} disabled={busy}>Approve and apply</button>
                        <button className="button button-secondary" type="button" onClick={() => void decideProposal(proposal.id, "reject")} disabled={busy}>Reject</button>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            ) : <p className="muted-copy">There are no pending or past budget-change proposals.</p>}
          </section>
        </>
      ) : (
        <div className="empty-card"><h3>Budget data could not be loaded</h3><p>Check the backend connection and refresh the saved budget.</p><button className="button button-secondary" type="button" onClick={() => void reload()}>Retry</button></div>
      )}
    </section>
  );
}
