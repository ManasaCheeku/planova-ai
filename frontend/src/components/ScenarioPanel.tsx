import { useRef, useState, type FormEvent } from "react";
import type { EventRequest, ScenarioChanges, ScenarioResult } from "../types";

interface ScenarioPanelProps {
  event: EventRequest;
  busy: boolean;
  result: ScenarioResult | null;
  error: string;
  onAnalyze: (changes: ScenarioChanges) => Promise<void>;
}

const money = (amount: number | null, currency: string) =>
  amount === null
    ? "Not available"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency,
        maximumFractionDigits: 2,
      }).format(amount);

const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000)
  .toISOString()
  .slice(0, 10);

export default function ScenarioPanel({
  event,
  busy,
  result,
  error,
  onAnalyze,
}: ScenarioPanelProps) {
  const [guestCount, setGuestCount] = useState("");
  const [budget, setBudget] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [lastSubmittedChanges, setLastSubmittedChanges] = useState<ScenarioChanges | null>(null);
  const submitting = useRef(false);

  function submit(formEvent: FormEvent<HTMLFormElement>) {
    formEvent.preventDefault();
    if (busy || submitting.current) return;
    const changes = {
      ...(guestCount ? { guest_count: Number(guestCount) } : {}),
      ...(budget ? { budget: Number(budget) } : {}),
      ...(eventDate ? { event_date: eventDate } : {}),
    };
    if (Object.keys(changes).length === 0) return;
    submitting.current = true;
    setSubmitError("");
    setLastSubmittedChanges(changes);
    void onAnalyze(changes).then(
      () => {
        submitting.current = false;
      },
      (error: unknown) => {
        submitting.current = false;
        setSubmitError(error instanceof Error ? error.message : "Scenario analysis failed.");
      },
    );
  }

  const currentChanges = {
    ...(guestCount ? { guest_count: Number(guestCount) } : {}),
    ...(budget ? { budget: Number(budget) } : {}),
    ...(eventDate ? { event_date: eventDate } : {}),
  };
  const resultMatchesForm =
    result !== null &&
    lastSubmittedChanges !== null &&
    JSON.stringify(currentChanges) === JSON.stringify(lastSubmittedChanges);

  return (
    <section className="scenario-card" aria-busy={busy}>
      <div className="scenario-header">
        <div className="scenario-symbol" aria-hidden="true">↗</div>
        <div>
          <span className="eyebrow">WHAT IF?</span>
          <h2>Explore a scenario</h2>
          <p>Adjust a few details and see how your plan responds.</p>
        </div>
      </div>
      <form className="scenario-form" onSubmit={submit} aria-busy={busy}>
        <label className="field">
          <span>Guest count <small>Current: {event.guest_count}</small></span>
          <input
            type="number"
            min="1"
            max="1000000"
            value={guestCount}
            onChange={(input) => setGuestCount(input.target.value)}
            placeholder="Try a new count"
          />
        </label>
        <label className="field">
          <span>Budget <small>Current: {money(event.budget, event.currency ?? "INR")}</small></span>
          <div className="input-prefix">
            <span>{event.currency ?? "INR"}</span>
            <input
              type="number"
              min="0.01"
              max="9999999999.99"
              step="0.01"
              value={budget}
              onChange={(input) => setBudget(input.target.value)}
              placeholder="Try a new budget"
            />
          </div>
        </label>
        <label className="field">
          <span>Event date <small>Current: {event.event_date}</small></span>
          <input
            type="date"
            min={today}
            value={eventDate}
            onChange={(input) => setEventDate(input.target.value)}
          />
        </label>
        <button className="button button-secondary" type="submit" disabled={busy || (!guestCount && !budget && !eventDate)}>
          {busy ? <><span className="spinner" aria-hidden="true" /> Evaluating…</> : "Compare scenario"}
        </button>
      </form>
      {(error || submitError) && <div className="alert alert-error scenario-error" role="alert">{error || submitError}</div>}
      {resultMatchesForm && result ? (
        <div className="scenario-result" aria-live="polite" aria-atomic="true">
          <div className="scenario-result-heading">
            <strong>Scenario impact</strong>
            <span>Recalculated by the Planova API</span>
          </div>
          <div className="impact-grid">
            <div className="impact-item">
              <span>Budget</span>
              <div className="impact-comparison">
                <span><small>Before</small><strong>{money(result.budget_impact.original_budget, event.currency ?? "INR")}</strong></span>
                <span aria-hidden="true">→</span>
                <span><small>After</small><strong>{money(result.budget_impact.scenario_budget, result.scenario_event.currency ?? event.currency ?? "INR")}</strong></span>
              </div>
              <small>Status: {result.budget_impact.original_status.replaceAll("_", " ")} → {result.budget_impact.scenario_status.replaceAll("_", " ")}</small>
            </div>
            <div className="impact-item">
              <span>Capacity</span>
              <div className="impact-comparison">
                <span><small>Before</small><strong>{result.capacity_impact.original_status.replaceAll("_", " ")}</strong></span>
                <span aria-hidden="true">→</span>
                <span><small>After</small><strong>{result.capacity_impact.scenario_status.replaceAll("_", " ")}</strong></span>
              </div>
              <small>{result.capacity_impact.original_guest_count} → {result.capacity_impact.scenario_guest_count} guests{result.capacity_impact.venue_capacity !== null ? ` / ${result.capacity_impact.venue_capacity} capacity` : " / capacity unknown"}</small>
            </div>
            <div className="impact-item">
              <span>Readiness</span>
              <div className="impact-comparison">
                <span><small>Before</small><strong>{result.readiness_impact.original_score}<small>/100</small></strong></span>
                <span aria-hidden="true">→</span>
                <span><small>After</small><strong>{result.readiness_impact.scenario_score}<small>/100</small></strong></span>
              </div>
              <small>Status: {result.readiness_impact.original_status.replaceAll("_", " ")} → {result.readiness_impact.scenario_status.replaceAll("_", " ")}</small>
            </div>
          </div>
          <details className="scenario-assumptions">
            <summary>Scenario assumptions</summary>
            <ul>{result.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>
          </details>
        </div>
      ) : (
        <p className="scenario-hint">
          {busy
            ? "The backend is recalculating this scenario…"
            : result
              ? "Your inputs changed. Compare again to update these results."
              : "Choose at least one change to ask the backend to recalculate the plan."}
        </p>
      )}
    </section>
  );
}
