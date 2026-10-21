import { useEffect, useRef, useState, type FormEvent } from "react";
import type {
  AIPlanningDetails,
  CostCategory,
  DashboardCommandResult,
  EventRequest,
} from "../types";

interface EventFormProps {
  busy: boolean;
  onSubmit: (event: EventRequest) => Promise<void>;
  onUnderstand: (message: string, conversationId?: string) => Promise<DashboardCommandResult>;
  initialDraft: EventRequest | null;
  onInitialDraftApplied: () => void;
}

const COST_CATEGORIES: { key: CostCategory; label: string }[] = [
  { key: "venue", label: "Venue" },
  { key: "catering", label: "Catering" },
  { key: "decoration", label: "Decoration" },
  { key: "photography", label: "Photography" },
  { key: "entertainment", label: "Entertainment" },
  { key: "transport", label: "Transport" },
  { key: "accommodation", label: "Accommodation" },
  { key: "invitations", label: "Invitations" },
  { key: "production", label: "Production" },
  { key: "staffing", label: "Staffing" },
  { key: "equipment", label: "Equipment" },
  { key: "activities", label: "Activities" },
  { key: "contingency", label: "Contingency" },
  { key: "miscellaneous", label: "Miscellaneous" },
  { key: "other", label: "Other" },
];
const SUPPORTED_CURRENCIES = ["INR", "USD", "EUR", "GBP", "CAD", "AUD", "SGD", "AED", "JPY"];

const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000)
  .toISOString()
  .slice(0, 10);
const MAX_MONEY = "9999999999.99";
const EVENT_TYPES = [
  "Corporate conference",
  "Product launch",
  "Company celebration",
  "Networking reception",
  "Workshop or seminar",
  "Other corporate event",
];
const EMPTY_PLANNING: AIPlanningDetails = {
  objectives: [],
  agenda: [],
  checklist: [],
  personalized_ideas: [],
  assumptions: [],
  uncertainties: [],
};

export default function EventForm({
  busy,
  onSubmit,
  onUnderstand,
  initialDraft,
  onInitialDraftApplied,
}: EventFormProps) {
  const formRef = useRef<HTMLFormElement>(null);
  const [requirements, setRequirements] = useState("");
  const [constraints, setConstraints] = useState("");
  const [activities, setActivities] = useState("");
  const [preferences, setPreferences] = useState("");
  const [vendorNames, setVendorNames] = useState("");
  const [costs, setCosts] = useState<Partial<Record<CostCategory, string>>>({});
  const [eventType, setEventType] = useState(EVENT_TYPES[0]);
  const [currency, setCurrency] = useState("INR");
  const [validationError, setValidationError] = useState("");
  const [aiRequest, setAiRequest] = useState("");
  const [aiConversationId, setAiConversationId] = useState<string>();
  const [aiResult, setAiResult] = useState<DashboardCommandResult | null>(null);
  const [planningSuggestions, setPlanningSuggestions] = useState<AIPlanningDetails>(EMPTY_PLANNING);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState("");
  const submitting = useRef(false);

  function setFormValue(name: string, value: unknown) {
    if (typeof value !== "string" && typeof value !== "number") return;
    const input = formRef.current?.elements.namedItem(name);
    if (input instanceof HTMLInputElement) input.value = String(value);
  }

  function applyFields(fields: Record<string, unknown>) {
    setFormValue("event_name", fields.event_name);
    setFormValue("purpose", fields.purpose);
    setFormValue("event_date", fields.event_date);
    setFormValue("event_time", fields.event_time);
    setFormValue("location", fields.location);
    setFormValue("guest_count", fields.guest_count);
    setFormValue("budget", fields.budget ?? fields.budget_inr);
    setFormValue("venue_capacity", fields.venue_capacity);
    if (typeof fields.currency === "string" && SUPPORTED_CURRENCIES.includes(fields.currency.toUpperCase())) {
      setCurrency(fields.currency.toUpperCase());
    }
    if (typeof fields.event_type === "string" && fields.event_type.trim()) {
      setEventType(fields.event_type);
    }
    if (Array.isArray(fields.requirements)) {
      setRequirements(fields.requirements.filter((item): item is string => typeof item === "string").join("\n"));
    }
    if (Array.isArray(fields.activities)) {
      setActivities(fields.activities.filter((item): item is string => typeof item === "string").join("\n"));
    }
    if (Array.isArray(fields.preferences)) {
      setPreferences(fields.preferences.filter((item): item is string => typeof item === "string").join("\n"));
    }
    if (fields.planning_suggestions && typeof fields.planning_suggestions === "object") {
      setPlanningSuggestions(fields.planning_suggestions as AIPlanningDetails);
    }
    if (Array.isArray(fields.constraints)) {
      setConstraints(fields.constraints.filter((item): item is string => typeof item === "string").join("\n"));
    }
    if (fields.estimated_costs && typeof fields.estimated_costs === "object") {
      const nextCosts: Partial<Record<CostCategory, string>> = {};
      for (const [key, value] of Object.entries(fields.estimated_costs)) {
        if (COST_CATEGORIES.some((category) => category.key === key) && typeof value === "number") {
          nextCosts[key as CostCategory] = String(value);
        }
      }
      setCosts(nextCosts);
    }
  }

  useEffect(() => {
    if (!initialDraft) return;
    applyFields(initialDraft as unknown as Record<string, unknown>);
    onInitialDraftApplied();
  }, [initialDraft, onInitialDraftApplied]);

  async function requestAI() {
    if (!aiRequest.trim() || aiBusy) return;
    setAiBusy(true);
    setAiError("");
    try {
      const result = await onUnderstand(aiRequest.trim(), aiConversationId);
      setAiResult(result);
      setAiConversationId(result.conversation_id ?? undefined);
      if (result.planning) setPlanningSuggestions(result.planning);
      const extracted = result.extracted.event;
      if (extracted && typeof extracted === "object") {
        applyFields(extracted as Record<string, unknown>);
      } else {
        applyFields(result.draft
          ? result.draft as unknown as Record<string, unknown>
          : result.extracted);
      }
    } catch (error) {
      setAiError(error instanceof Error ? error.message : "GenAI could not process this request.");
    } finally {
      setAiBusy(false);
    }
  }

  async function handleSubmit(formData: FormData) {
    const requirementList = requirements
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
    const constraintList = constraints
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
    const activityList = activities
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
    const preferenceList = preferences
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
    const confirmedVendors = vendorNames
      .split(/\r?\n/)
      .map((vendor) => vendor.trim())
      .filter(Boolean);

    if (requirementList.length > 50 || constraintList.length > 50 || confirmedVendors.length > 50 || activityList.length > 20 || preferenceList.length > 30) {
      setValidationError("Requirements, constraints, vendors, activities, or preferences exceed their entry limits.");
      return;
    }
    if (
      planningSuggestions.objectives.length > 8 ||
      planningSuggestions.agenda.length > 20 ||
      planningSuggestions.checklist.length > 20 ||
      planningSuggestions.personalized_ideas.length > 12 ||
      planningSuggestions.assumptions.length > 12 ||
      planningSuggestions.uncertainties.length > 12 ||
      planningSuggestions.agenda.some((item) => !item.title.trim() || !item.basis.trim())
    ) {
      setValidationError("Review the planning suggestions: agenda items need a title and basis, and each section has a documented item limit.");
      return;
    }
    setValidationError("");
    const costEntries = COST_CATEGORIES.flatMap(({ key }) => {
      const value = costs[key]?.trim();
      return value ? [[key, Number(value)] as const] : [];
    });
    const event: EventRequest = {
      event_name: String(formData.get("event_name")).trim(),
      event_type: String(formData.get("event_type")),
      purpose: String(formData.get("purpose") || "").trim() || null,
      event_date: String(formData.get("event_date")),
      event_time: String(formData.get("event_time") || "") || null,
      location: String(formData.get("location")).trim(),
      guest_count: Number(formData.get("guest_count")),
      budget: Number(formData.get("budget")),
      currency,
      requirements: requirementList,
      constraints: constraintList,
      activities: activityList,
      preferences: preferenceList,
      planning_suggestions: planningSuggestions,
      venue_capacity: formData.get("venue_capacity")
        ? Number(formData.get("venue_capacity"))
        : null,
      estimated_costs: Object.fromEntries(costEntries) as Partial<
        Record<CostCategory, number>
      >,
      confirmed_vendors: confirmedVendors,
    };
    await onSubmit(event);
  }

  function updatePlanningList(
    key: Exclude<keyof AIPlanningDetails, "agenda">,
    value: string,
  ) {
    setValidationError("");
    setPlanningSuggestions((current) => ({
      ...current,
      [key]: value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
    }));
  }

  function updateAgendaItem(
    index: number,
    field: "title" | "time" | "duration_minutes" | "basis",
    value: string,
  ) {
    setValidationError("");
    setPlanningSuggestions((current) => ({
      ...current,
      agenda: current.agenda.map((item, itemIndex) =>
        itemIndex === index
          ? {
              ...item,
              [field]:
                field === "duration_minutes"
                  ? value
                    ? Number(value)
                    : null
                  : field === "time"
                    ? value || null
                    : value,
            }
          : item,
      ),
    }));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || submitting.current) return;
    submitting.current = true;
    void handleSubmit(new FormData(event.currentTarget))
      .catch((error: unknown) => {
        setValidationError(
          error instanceof Error ? error.message : "The event plan could not be submitted.",
        );
      })
      .finally(() => {
        submitting.current = false;
      });
  }

  const hasPlanningSuggestions = Object.values(planningSuggestions).some(
    (items) => items.length > 0,
  );

  return (
    <form ref={formRef} className="event-form" onSubmit={submit} aria-busy={busy}>
      {validationError && <div className="alert alert-error form-validation-error" role="alert">{validationError}</div>}
      <section className="event-ai-assist" aria-labelledby="event-ai-heading">
        <div>
          <span className="eyebrow">OPTIONAL GENAI ASSIST</span>
          <h2 id="event-ai-heading">Start with a description</h2>
          <p>Extracted details prefill editable fields below. When a provider is configured, follow-up turns are retained locally for up to 30 days. The provider receives your request only when configured.</p>
        </div>
        <label className="field">
          <span>Describe your event</span>
          <textarea
            rows={3}
            maxLength={1000}
            value={aiRequest}
            onChange={(event) => setAiRequest(event.target.value)}
            placeholder="A community gathering in Pune for about 80 people this December…"
          />
        </label>
        <button className="button button-secondary" type="button" onClick={() => void requestAI()} disabled={aiBusy || !aiRequest.trim()}>
          {aiBusy ? "Understanding event…" : aiResult ? "Send follow-up" : "Extract details"}
        </button>
        {aiError && <p className="alert alert-error" role="alert">{aiError}</p>}
        {(aiResult || hasPlanningSuggestions) && (
          <div className="event-ai-result" aria-live="polite">
            {aiResult && <p>{aiResult.notice}</p>}
            {aiResult && aiResult.questions.length > 0 && <ul>{aiResult.questions.map((question, index) => <li key={`${question}-${index}`}>{question}</li>)}</ul>}
            {(aiResult?.planning || hasPlanningSuggestions) && (
              <>
                <strong>Editable plan suggestions · unconfirmed</strong>
                <label className="field"><span>Objectives</span><textarea rows={2} value={planningSuggestions.objectives.join("\n")} onChange={(event) => updatePlanningList("objectives", event.target.value)} /></label>
                <div className="event-ai-agenda">
                  <strong>Agenda</strong>
                  {planningSuggestions.agenda.map((item, index) => (
                    <div className="event-ai-agenda-item" key={`${index}-${item.title}`}>
                      <label className="field"><span>Activity</span><input value={item.title} maxLength={120} onChange={(event) => updateAgendaItem(index, "title", event.target.value)} /></label>
                      <label className="field"><span>Time suggestion</span><input value={item.time ?? ""} maxLength={40} onChange={(event) => updateAgendaItem(index, "time", event.target.value)} /></label>
                      <label className="field"><span>Duration (minutes)</span><input type="number" min="1" max="1440" value={item.duration_minutes ?? ""} onChange={(event) => updateAgendaItem(index, "duration_minutes", event.target.value)} /></label>
                      <label className="field"><span>Basis / uncertainty</span><input value={item.basis} maxLength={300} onChange={(event) => updateAgendaItem(index, "basis", event.target.value)} /></label>
                      <button className="text-link" type="button" onClick={() => { setValidationError(""); setPlanningSuggestions((current) => ({ ...current, agenda: current.agenda.filter((_, itemIndex) => itemIndex !== index) })); }}>Remove agenda item</button>
                    </div>
                  ))}
                  <button className="button button-secondary" type="button" disabled={planningSuggestions.agenda.length >= 20} onClick={() => { setValidationError(""); setPlanningSuggestions((current) => ({ ...current, agenda: [...current.agenda, { title: "", time: null, duration_minutes: null, basis: "User-added suggestion; unconfirmed." }] })); }}>Add agenda item</button>
                </div>
                <label className="field"><span>Checklist suggestions</span><textarea rows={3} value={planningSuggestions.checklist.join("\n")} onChange={(event) => updatePlanningList("checklist", event.target.value)} /></label>
                <label className="field"><span>Personalized ideas</span><textarea rows={3} value={planningSuggestions.personalized_ideas.join("\n")} onChange={(event) => updatePlanningList("personalized_ideas", event.target.value)} /></label>
                <label className="field"><span>Assumptions</span><textarea rows={2} value={planningSuggestions.assumptions.join("\n")} onChange={(event) => updatePlanningList("assumptions", event.target.value)} /></label>
                <label className="field"><span>Uncertainties</span><textarea rows={2} value={planningSuggestions.uncertainties.join("\n")} onChange={(event) => updatePlanningList("uncertainties", event.target.value)} /></label>
              </>
            )}
            {aiResult?.plan && <div><strong>Deterministic budget allocations · not quotes</strong><ul>{Object.entries(aiResult.plan.budget_analysis.allocations).map(([category, amount]) => <li key={category}>{category}: ₹{amount.toLocaleString("en-IN")}</li>)}</ul></div>}
            {aiResult?.plan && <div><strong>Deterministic risk review · {aiResult.plan.readiness.status.replaceAll("_", " ")}</strong>{aiResult.plan.risks.length ? <ul>{aiResult.plan.risks.map((risk) => <li key={risk.id}>{risk.title}: {risk.reason} Mitigation: {risk.mitigation}</li>)}</ul> : <p>No deterministic risks were identified from the supplied details.</p>}</div>}
            <p className="event-ai-edit-note">Review and edit the prefilled fields before creating the event. Nothing has been saved.</p>
          </div>
        )}
      </section>
      <div className="form-section">
        <div className="section-heading">
          <span className="section-number">01</span>
          <div>
            <h2>Event essentials</h2>
            <p>Start with the details that shape your plan.</p>
          </div>
        </div>
        <div className="form-grid">
          <label className="field field-wide">
            <span>Event name <i>*</i></span>
            <input name="event_name" placeholder="e.g. Annual leadership summit" maxLength={120} required />
          </label>
          <label className="field field-wide">
            <span>Purpose <small>Optional</small></span>
            <input name="purpose" placeholder="What should this event accomplish?" maxLength={500} />
          </label>
          <label className="field">
            <span>Event type <i>*</i></span>
            <select name="event_type" value={eventType} onChange={(event) => setEventType(event.target.value)} required>
              {!EVENT_TYPES.includes(eventType) && <option>{eventType}</option>}
              {EVENT_TYPES.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Event date <i>*</i></span>
            <input name="event_date" type="date" min={today} required />
          </label>
          <label className="field">
            <span>Event time <small>Optional</small></span>
            <input name="event_time" type="time" />
          </label>
          <label className="field field-wide">
            <span>Location <i>*</i></span>
            <input name="location" placeholder="City, region, or preferred venue" maxLength={200} required />
          </label>
          <label className="field field-wide">
            <span>Venue name <small>Optional</small></span>
            <input name="venue_name" placeholder="Leave blank if not selected" maxLength={200} />
          </label>
          <label className="field">
            <span>Guest count <i>*</i></span>
            <div className="input-suffix">
              <input name="guest_count" type="number" min="1" max="1000000" placeholder="250" required />
              <span>guests</span>
            </div>
          </label>
          <label className="field">
            <span>Currency <i>*</i></span>
            <select value={currency} onChange={(event) => setCurrency(event.target.value)} required>
              {SUPPORTED_CURRENCIES.map((code) => <option key={code} value={code}>{code}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Total budget <i>*</i></span>
            <div className="input-prefix">
              <span>{currency}</span>
              <input name="budget" type="number" min="0.01" max={MAX_MONEY} step="0.01" placeholder="25,000" required />
            </div>
          </label>
          <label className="field field-wide">
            <span>Venue capacity <small>Optional</small></span>
            <div className="input-suffix">
              <input name="venue_capacity" type="number" min="1" max="1000000" placeholder="Leave blank if unknown" />
              <span>people</span>
            </div>
          </label>
        </div>
      </div>

      <div className="form-section">
        <div className="section-heading">
          <span className="section-number">02</span>
          <div>
            <h2>Planning details</h2>
            <p>Share priorities and any estimates you already have.</p>
          </div>
        </div>
        <div className="form-grid">
          <label className="field field-wide">
            <span>Activities <small>One per line · up to 20 · optional</small></span>
            <textarea
              value={activities}
              onChange={(event) => setActivities(event.target.value)}
              rows={2}
              placeholder={"Welcome reception\nCommunity performances"}
            />
          </label>
          <label className="field field-wide">
            <span>Preferences <small>One per line · up to 30 · optional</small></span>
            <textarea
              value={preferences}
              onChange={(event) => setPreferences(event.target.value)}
              rows={2}
              placeholder={"Plant-forward catering\nQuiet seating area"}
            />
          </label>
          <label className="field field-wide">
            <span>Requirements <small>One per line · up to 50 · optional</small></span>
            <textarea
              value={requirements}
              onChange={(event) => {
                setRequirements(event.target.value);
                setValidationError("");
              }}
              rows={3}
              placeholder={"Accessible venue\nPlant-forward catering\nHybrid presentation setup"}
            />
          </label>
          <label className="field field-wide">
            <span>Constraints <small>One per line · up to 50 · optional</small></span>
            <textarea
              value={constraints}
              onChange={(event) => setConstraints(event.target.value)}
              rows={2}
              placeholder={"Keep within the venue's sound limits\nAvoid scheduling during a local holiday"}
            />
          </label>
          <div className="field field-wide">
            <span>Cost estimates <small>Optional · estimates only, not quotes</small></span>
            <div className="cost-grid">
              {COST_CATEGORIES.map(({ key, label }) => (
                <label className="field cost-field" key={key}>
                  <span>{label}</span>
                  <div className="input-prefix">
                    <span>₹</span>
                    <input
                      type="number"
                      min="0"
                      max={MAX_MONEY}
                      step="0.01"
                      aria-label={`${label} estimated cost`}
                      placeholder="Not estimated"
                      value={costs[key] ?? ""}
                      onChange={(event) =>
                        setCosts((current) => ({
                          ...current,
                          [key]: event.target.value,
                        }))
                      }
                    />
                  </div>
                </label>
              ))}
            </div>
          </div>
          <label className="field field-wide">
            <span>Confirmed vendors <small>One per line · up to 50 · optional</small></span>
            <textarea
              rows={2}
              value={vendorNames}
              onChange={(event) => {
                setVendorNames(event.target.value);
                setValidationError("");
              }}
              placeholder={"Venue partner\nCatering team"}
            />
          </label>
        </div>
      </div>

      <div className="form-footer">
        <p><span className="required-star">*</span> Required fields</p>
        <button className="button button-primary" type="submit" disabled={busy}>
          {busy ? (
            <>
              <span className="spinner" aria-hidden="true" />
              Building your plan…
            </>
          ) : (
            <>
              Build event plan
              <span aria-hidden="true">↗</span>
            </>
          )}
        </button>
      </div>
    </form>
  );
}
