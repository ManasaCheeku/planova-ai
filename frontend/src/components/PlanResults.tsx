import type { EventPlan, Risk } from "../types";

interface PlanResultsProps {
  plan: EventPlan;
}

const money = (amount: number | null, currency: string) =>
  amount === null
    ? "Not available"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency,
        maximumFractionDigits: 2,
      }).format(amount);

const labels: Record<string, string> = {
  venue: "Venue",
  catering: "Catering",
  decoration: "Decoration",
  photography: "Photography",
  entertainment: "Entertainment",
  transport: "Transport",
  accommodation: "Accommodation",
  invitations: "Invitations",
  miscellaneous: "Miscellaneous",
  other: "Other",
  production: "Production",
  staffing: "Staffing",
  contingency: "Contingency",
  venue_capacity: "Venue capacity",
  venue_capacity_unconfirmed: "Capacity unconfirmed",
  insufficient_budget: "Budget overrun",
  missing_requirements: "Requirements missing",
  tight_timeline: "Tight timeline",
  unconfirmed_vendors: "Vendors unconfirmed",
  incomplete_cost_information: "Cost information",
};

function SeverityBadge({ severity }: { severity: Risk["severity"] }) {
  return <span className={`severity-badge severity-${severity}`}>{severity}</span>;
}

export default function PlanResults({ plan }: PlanResultsProps) {
  const { budget_analysis: budget } = plan;
  const currency = plan.event.currency ?? budget.currency ?? "INR";
  const barTotal = Math.max(budget.estimated_total ?? budget.budget, 1);

  return (
    <section className="results-stack" aria-label="Event plan results" aria-live="polite">
      <div className="results-heading">
        <div>
          <div className="eyebrow">YOUR PLAN AT A GLANCE</div>
          <h2>{plan.event.event_name}</h2>
          <p>{plan.event.event_type} <span>·</span> {plan.event.location}</p>
        </div>
        <span className={`readiness-pill readiness-${plan.readiness.status}`}>
          <span className="readiness-dot" />
          {plan.readiness.status.replace("_", " ")}
        </span>
      </div>

      <div className="metric-grid">
        <article className="metric-card">
          <span className="metric-label">Total budget</span>
          <strong>{money(budget.budget, currency)}</strong>
          <span className="metric-caption">Planning envelope</span>
        </article>
        <article className="metric-card metric-card-accent">
          <span className="metric-label">Estimated costs</span>
          <strong>{money(budget.estimated_total, currency)}</strong>
          <span className="metric-caption">
            {budget.estimated_total === null ? "No estimates provided" : "Supplied estimates only"}
          </span>
        </article>
        <article className="metric-card">
          <span className="metric-label">Readiness score</span>
          <strong>{plan.readiness.score}<small>/100</small></strong>
          <span className="metric-caption">Based on identified risks</span>
        </article>
      </div>

      <section className="result-card">
        <div className="result-card-heading">
          <div>
            <span className="eyebrow">BUDGET BREAKDOWN</span>
            <h3>Allocation &amp; estimates</h3>
          </div>
          <span className={`budget-status budget-${budget.status}`}>
            {budget.status.replace("_", " ")}
          </span>
        </div>
        <div
          className="budget-bar"
          role="img"
          aria-label="Planning budget allocations by category"
        >
          {Object.entries(budget.allocations).map(([category, amount], index) => (
            <span
              key={category}
              className={`budget-segment segment-${index + 1}`}
              style={{ width: `${(amount / budget.allocation_total) * 100}%` }}
              title={`${labels[category] ?? category}: ${money(amount, currency)}`}
            />
          ))}
        </div>
        <div className="budget-legend">
          {Object.entries(budget.allocations).map(([category, amount], index) => (
            <div className="legend-item" key={category}>
              <span className={`legend-dot segment-${index + 1}`} />
              <span>{labels[category] ?? category}</span>
              <strong>{money(amount, currency)}</strong>
            </div>
          ))}
        </div>
        <div className="estimate-list">
          <div className="estimate-row estimate-row-head">
            <span>Provided estimate</span>
            <span>Amount</span>
          </div>
          {Object.entries(budget.estimated_costs).map(([category, amount]) => (
            <div className="estimate-row" key={category}>
              <span>{labels[category] ?? category}</span>
              <span>{money(amount, currency)}</span>
            </div>
          ))}
          {budget.missing_cost_categories.map((category) => (
            <div className="estimate-row estimate-missing" key={category}>
              <span>{labels[category] ?? category} <em>Missing estimate</em></span>
              <span>—</span>
            </div>
          ))}
          <div className="estimate-row estimate-total">
            <span>Estimated total <small>Not a confirmed price</small></span>
            <strong>{money(budget.estimated_total, currency)}</strong>
          </div>
          {budget.remaining_budget !== null && (
            <div className="estimate-row estimate-remaining">
              <span>{budget.over_budget ? "Amount over budget" : "Unallocated from estimate"}</span>
              <strong>{money(Math.abs(budget.remaining_budget), currency)}</strong>
            </div>
          )}
        </div>
        <p className="fine-print">
          The bar shows planning allocations, not actual costs. Only amounts entered by you are included as estimates.
        </p>
      </section>

      <section className="result-card">
        <div className="result-card-heading">
          <div>
            <span className="eyebrow">PLANNING SIGNALS</span>
            <h3>Risk assessment <span className="risk-count">{plan.risks.length}</span></h3>
          </div>
        </div>
        {plan.risks.length === 0 ? (
          <div className="all-clear">
            <span aria-hidden="true">✓</span>
            <div><strong>No risks identified</strong><p>Based on the event details provided.</p></div>
          </div>
        ) : (
          <div className="risk-list">
            {plan.risks.map((risk) => (
              <article className="risk-item" key={risk.id}>
                <div className={`risk-icon risk-icon-${risk.severity}`} aria-hidden="true">
                  {risk.severity === "high" ? "!" : "·"}
                </div>
                <div className="risk-content">
                  <div className="risk-title-row">
                    <h4>{labels[risk.type] ?? risk.type.replaceAll("_", " ")}</h4>
                    <SeverityBadge severity={risk.severity} />
                  </div>
                  <p>{risk.reason}</p>
                  <div className="mitigation"><strong>Suggested next step</strong> {risk.mitigation}</div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <details className="assumption-card">
        <summary>How to read these numbers <span aria-hidden="true">+</span></summary>
        <ul>
          {budget.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}
        </ul>
        <div className="budget-meter" aria-hidden="true">
          <span style={{ width: `${Math.min(100, ((budget.estimated_total ?? 0) / barTotal) * 100)}%` }} />
        </div>
      </details>
    </section>
  );
}
