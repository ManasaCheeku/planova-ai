export type CostCategory =
  | "venue"
  | "catering"
  | "production"
  | "staffing"
  | "equipment"
  | "activities"
  | "decoration"
  | "photography"
  | "entertainment"
  | "transport"
  | "accommodation"
  | "invitations"
  | "contingency"
  | "miscellaneous"
  | "other";

export type EventStatus = "scheduled" | "completed" | "cancelled";
export type TaskStatus = "pending" | "in_progress" | "completed";

export interface EventRequest {
  event_name: string;
  event_type: string;
  purpose?: string | null;
  event_date: string;
  event_time?: string | null;
  location: string;
  guest_count: number;
  budget: number;
  currency?: string;
  category_allocations?: Partial<Record<CostCategory, number>>;
  venue_name?: string | null;
  requirements: string[];
  constraints?: string[];
  requirement_status?: Record<string, "satisfied" | "unsatisfied" | "unverified">;
  constraint_status?: Record<string, "satisfied" | "unsatisfied" | "unverified">;
  venue_capacity: number | null;
  activities?: string[];
  preferences?: string[];
  planning_suggestions?: AIPlanningDetails;
  estimated_costs: Partial<Record<CostCategory, number>>;
  planned_expenses?: CostCategory[];
  confirmed_vendors: string[];
  unconfirmed_vendors?: string[];
}

export interface EventPlan {
  event_id?: string | null;
  created_at?: string | null;
  event: EventRequest;
  budget_analysis: {
    currency: string;
    budget: number;
    allocations: Record<CostCategory, number>;
    allocation_total: number;
    estimated_costs: Partial<Record<CostCategory, number>>;
    estimated_total: number | null;
    known_expenses_total: number;
    remaining_budget: number;
    status: "incomplete" | "within_budget" | "over_budget";
    over_budget: boolean;
    overrun_amount: number;
    overrun_categories: CostCategory[];
    overrun_breakdown: Partial<Record<CostCategory, number>>;
    missing_cost_categories: CostCategory[];
    contingency_recommendation: {
      amount: number | null;
      rate: number | null;
      basis: string;
      included_in_known_costs: boolean;
    };
    assumptions: string[];
  };
  risks: Risk[];
  readiness: {
    status: "ready" | "needs_attention" | "at_risk";
    score: number;
    basis: string;
  };
}

export interface Risk {
  id: string;
  type: string;
  title: string;
  severity: "low" | "medium" | "high";
  reason: string;
  evidence: Record<string, unknown>;
  mitigation: string;
}

export interface ScenarioRequest {
  event: EventRequest;
  changes: ScenarioChanges;
}

export interface ScenarioChanges {
  guest_count?: number;
  budget?: number;
  event_date?: string;
  estimated_costs?: Partial<Record<CostCategory, number>>;
}

export interface ScenarioResult {
  original_plan: EventPlan;
  scenario_event: EventRequest;
  scenario_plan: EventPlan;
  budget_impact: {
    original_budget: number;
    scenario_budget: number;
    budget_change: number;
    original_estimated_total: number | null;
    scenario_estimated_total: number | null;
    original_known_expenses_total: number;
    scenario_known_expenses_total: number;
    known_expenses_change: number;
    original_remaining_budget: number;
    scenario_remaining_budget: number;
    original_overrun_amount: number;
    scenario_overrun_amount: number;
    original_status: string;
    scenario_status: string;
  };
  capacity_impact: {
    original_status: string;
    scenario_status: string;
    original_guest_count: number;
    scenario_guest_count: number;
    venue_capacity: number | null;
  };
  readiness_impact: {
    original_status: string;
    scenario_status: string;
    original_score: number;
    scenario_score: number;
    score_change: number;
  };
  risk_changes: {
    newly_introduced: Risk[];
    resolved: Risk[];
    remaining: Risk[];
  };
  recommendations: string[];
  assumptions: string[];
}

export interface DashboardEvent {
  id: string;
  created_at: string;
  resolved_at: string | null;
  resolution: string | null;
  status: EventStatus;
  plan: EventPlan;
}

export interface DashboardTask {
  id: string;
  created_at: string;
  title: string;
  due_date: string | null;
  status: TaskStatus;
  overdue: boolean;
  blocked: boolean;
  blockers: string[];
  event_id: string | null;
  description: string;
  priority: "low" | "medium" | "high";
  assigned_to: string | null;
  estimated_cost: number | null;
  completion_criteria: string;
  dependencies: string[];
  generated: boolean;
}

export interface WorkflowTask extends DashboardTask {
  event_id: string;
  blockers: string[];
  information_needed: string[];
  blocks: string[];
  overdue: boolean;
}

export interface WorkflowSnapshot {
  event_id: string;
  event_name: string;
  generated: boolean;
  tasks: WorkflowTask[];
  overdue_count: number;
  blocked_count: number;
  missing_information: string[];
  next_action: string | null;
  unresolved_event_risks: string[];
  ai_model_configured: boolean;
  notice: string;
}

export interface AIPlanningDetails {
  objectives: string[];
  agenda: { title: string; time: string | null; duration_minutes: number | null; basis: string }[];
  checklist: string[];
  personalized_ideas: string[];
  assumptions: string[];
  uncertainties: string[];
}

export interface WorkflowAIGuidance {
  notice: string;
  ai_model_configured: boolean;
  guidance: {
    explanation: string;
    next_action: string | null;
    action_source: "genai" | "deterministic";
    reasons: string[];
    evidence_gaps: string[];
  } | null;
}

export interface RecoveryAIGuidance {
  notice: string;
  ai_model_configured: boolean;
  guidance: {
    summary: string;
    suggestions: {
      title: string;
      suggestion: string;
      tradeoffs: string[];
      assumptions: string[];
      evidence_to_verify: string[];
    }[];
  } | null;
}

export type RecoveryDisruption =
  | "venue_cancellation"
  | "vendor_cancellation"
  | "budget_change"
  | "guest_count_change"
  | "date_change"
  | "delayed_task"
  | "equipment_availability"
  | "catering_availability"
  | "other";

export interface RecoveryOption {
  id: string;
  title: string;
  description: string;
  readiness: "requires_verification" | "ready_for_review";
  cost_change: number | null;
  cost_basis: string;
  projected_known_cost_inr: number;
  projected_overrun_inr: number;
  approved_budget_inr: number;
  timing_change_days: number | null;
  affected_tasks: string[];
  unresolved_risks: string[];
  uncertainties: string[];
  proposed_changes: Record<string, unknown>;
}

export interface RecoveryProposal {
  id: string;
  case_id: string;
  event_id: string;
  option_id: string;
  status: "proposed" | "approved" | "rejected" | "applied" | "failed";
  proposed_change: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  result: {
    event_id: string;
    applied_changes: Record<string, unknown>;
    remaining_blockers: { title: string; reason: string; severity: string }[];
    external_actions_executed: string[];
    message: string;
  } | null;
}

export interface RecoveryCase {
  id: string;
  event_id: string;
  created_at: string;
  resolved_at: string | null;
  resolution: string | null;
  source: "user_report";
  disruption_type: RecoveryDisruption;
  description: string;
  status: "open" | "resolved";
  impact: {
    known_budget_inr: number;
    known_expenses_inr: number;
    known_remaining_budget_inr: number;
    estimated_overrun_inr: number;
    estimated_overrun_percent: number | null;
    overrun_categories: string[];
    overrun_breakdown_inr: Record<string, number>;
    scenario_estimated_overrun_inr: number | null;
    scenario_budget_inr: number | null;
    budget_assessment: "partial" | "based_on_supplied_estimates";
    missing_cost_categories: string[];
    affected_tasks: string[];
    user_reported_facts: string[];
    confirmed_facts: string[];
    uncertain_facts: string[];
    scenario_comparison: ScenarioResult | null;
  };
  options: RecoveryOption[];
  proposals: RecoveryProposal[];
  activity: {
    id: string;
    proposal_id: string | null;
    action: string;
    status: string;
    details: string;
    created_at: string;
  }[];
}

export interface DashboardSnapshot {
  updated_at: string;
  events: DashboardEvent[];
  tasks: DashboardTask[];
  risk_alerts: {
    event_id: string;
    event_name: string;
    risk: Risk;
  }[];
  summary: {
    total_events: number;
    upcoming_events: number;
    completed_events: number;
    cancelled_events: number;
    planned_budget_total: number | null;
    known_estimated_costs: number | null;
    remaining_known_estimate_budget: number | null;
    estimated_costs_by_category: Partial<Record<CostCategory, number>>;
    budget_totals_by_currency: {
      currency: string;
      planned_budget_total: number;
      known_estimated_costs: number;
      remaining_known_estimate_budget: number;
    }[];
    estimated_costs_by_currency: {
      currency: string;
      categories: Partial<Record<CostCategory, number>>;
    }[];
    expenditure_tracking_available: true;
    task_counts: {
      pending: number;
      in_progress: number;
      overdue: number;
      blocked: number;
      completed: number;
    };
    risk_counts: { low: number; medium: number; high: number };
  };
  capabilities: {
    tasks: boolean;
    event_status_updates: boolean;
    approvals: boolean;
    notifications: boolean;
    calendar_integrations: boolean;
    email_or_sms_delivery: boolean;
    ai_model_configured: boolean;
  };
}

export interface DashboardCommandResult {
  mode: "deterministic_fallback" | "genai";
  ai_model_configured: boolean;
  conversation_id: string | null;
  status: "needs_input" | "draft_ready";
  extracted: Record<string, unknown>;
  missing_information: string[];
  questions: string[];
  unsupported_actions: string[];
  notice: string;
  planning: AIPlanningDetails | null;
  draft: (Omit<EventRequest, "budget"> & { budget: number | string }) | null;
  plan: EventPlan | null;
}

export type ExpenseStatus = "committed" | "paid";

export interface EventExpense {
  id: string;
  event_id: string;
  created_at: string;
  updated_at: string;
  category: CostCategory;
  amount: number;
  expense_date: string;
  description: string;
  payment_status: ExpenseStatus;
  vendor_name: string | null;
}

export interface BudgetCategorySummary {
  category: CostCategory;
  allocation: number;
  estimated: number | null;
  committed: number;
  paid: number;
  recorded_total: number;
  projected: number | null;
  utilization_percent: number | null;
  missing_estimate: boolean;
}

export interface BudgetRecommendation {
  id: string;
  issue: string;
  supporting_figures: Record<string, number | string | null>;
  proposed_change: string;
  estimated_savings: number | null;
  savings_basis: string;
  tradeoffs: string[];
  uncertainty: string[];
  requires_approval: true;
  proposed_changes: { estimated_costs?: Partial<Record<CostCategory, number>> } | null;
}

export interface BudgetProposal {
  id: string;
  event_id: string;
  status: "proposed" | "applied" | "rejected";
  rationale: string;
  proposed_changes: Record<string, unknown>;
  preview: {
    currency: string;
    current: {
      approved_budget: number;
      projected_total: number | null;
      projected_overrun: number | null;
    };
    proposed: {
      approved_budget: number;
      projected_total: number | null;
      projected_overrun: number | null;
    };
    budget_change: number;
    projected_cost_change: number | null;
    affected_categories: CostCategory[];
    tradeoffs: string[];
  };
  created_at: string;
  updated_at: string;
  result: Record<string, unknown> | null;
}

export interface BudgetChangeRequest {
  budget?: number;
  estimated_costs?: Partial<Record<CostCategory, number>>;
  category_allocations?: Partial<Record<CostCategory, number>>;
}

export interface BudgetSummary {
  event_id: string;
  event_name: string;
  currency: string;
  approved_budget: number;
  planned_allocations: number;
  estimated_total: number | null;
  committed_total: number;
  paid_total: number;
  recorded_total: number;
  remaining_available: number;
  projected_total: number | null;
  projected_overrun: number | null;
  overrun_percent: number | null;
  assessment: "complete" | "partial";
  missing_cost_categories: CostCategory[];
  categories: BudgetCategorySummary[];
  expenses: EventExpense[];
  proposals: BudgetProposal[];
  alerts: {
    id: string;
    severity: "info" | "warning" | "high";
    category: CostCategory | null;
    title: string;
    explanation: string;
    supporting_figures: Record<string, number | string | null>;
  }[];
  recommendations: BudgetRecommendation[];
  assumptions: string[];
}

export interface BudgetAIGuidance {
  ai_model_configured: boolean;
  guidance: {
    explanation: string;
    suggestions: string[];
    evidence_gaps: string[];
  } | null;
  notice: string;
}

// Smart Invitations & RSVP Management. These are persisted API facts; the UI never
// infers an external send or delivery from a button press alone.
export type RSVPStatus = "awaiting_response" | "attending" | "not_attending";
export type InvitationStatus = "not_prepared" | "drafted" | "queued" | "sent" | "delivered" | "failed";
export type InvitationDraftKind = "invitation" | "reminder";
export type InvitationTone = "formal" | "friendly" | "celebratory" | "professional";
export type InvitationDeliveryStatus = "draft_only" | "queued" | "sent" | "delivered" | "failed" | "unknown" | "cancelled";

export interface InvitationGuest {
  id: string;
  event_id: string;
  created_at: string;
  updated_at: string;
  name: string;
  email: string | null;
  phone: string | null;
  group_name: string | null;
  party_size: number;
  notes: string | null;
  dietary_requirements: string[];
  accessibility_requirements: string[];
  accommodation_requirements: string[];
  invitation_status: InvitationStatus;
  rsvp_status: RSVPStatus;
  rsvp_party_size: number | null;
  duplicate_of_id: string | null;
}

export interface InvitationDuplicateSuggestion {
  guest_id: string;
  possible_duplicate_id: string;
  match_reasons: ("email" | "phone" | "name_and_contact")[];
}

export interface InvitationDraft {
  id: string;
  event_id: string;
  kind: InvitationDraftKind;
  subject: string;
  body: string;
  tone: InvitationTone;
  language: string;
  group_name: string | null;
  rsvp_deadline: string | null;
  generated_by: "manual" | "genai" | "deterministic";
  missing_information: string[];
  created_at: string;
  updated_at: string;
}

export interface InvitationDeliveryAttempt {
  id: string;
  batch_id: string | null;
  event_id: string;
  guest_id: string;
  draft_id: string;
  channel: "email";
  status: InvitationDeliveryStatus;
  recipient_address: string;
  provider_message_id: string | null;
  transport_message_id: string | null;
  error_message: string | null;
  retry_of_id: string | null;
  created_at: string;
  updated_at: string;
  sent_at: string | null;
  delivered_at: string | null;
}

export interface InvitationActivity {
  id: string;
  guest_id: string;
  action: string;
  source: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface InvitationSummary {
  total_guests: number;
  invitation_counts: Record<InvitationStatus, number>;
  rsvp_counts: Record<RSVPStatus, number>;
  confirmed_party_size: number;
  pending_guest_ids: string[];
  pending_count: number;
  declined_count: number;
  response_rate_percent: number;
}

export interface InvitationDeliveryConfiguration {
  mode: "smtp" | "draft_only";
  configured: boolean;
  sender: string | null;
  notice: string;
}

export interface InvitationPreviewRecipient {
  guest_id: string;
  guest_name: string;
  email: string | null;
  eligible: boolean;
  reason: string | null;
  subject: string | null;
  body: string | null;
}

export interface InvitationDeliveryPreview {
  event_id: string;
  draft_id: string;
  delivery_mode: "smtp" | "draft_only";
  recipients: InvitationPreviewRecipient[];
  approved: false;
  notice: string;
}

export interface InvitationDeliveryBatch {
  id: string;
  event_id: string;
  draft_id: string;
  kind: InvitationDraftKind;
  idempotency_key: string;
  status: "draft_only" | "completed" | "partial_failed" | "failed" | "unknown" | "cancelled";
  delivery_mode: "smtp" | "draft_only";
  approved_at: string;
  created_at: string;
  updated_at: string;
  attempts: InvitationDeliveryAttempt[];
  notice: string;
}

export interface InvitationReminderPreparation {
  id: string;
  event_id: string;
  draft: InvitationDraft;
  guest_ids: string[];
  status: "prepared" | "sent" | "cancelled";
  created_at: string;
  updated_at: string;
  delivery_batch_id: string | null;
  notice: string;
}

export interface InvitationOverview {
  event_id: string;
  guests: InvitationGuest[];
  drafts: InvitationDraft[];
  summary: InvitationSummary;
  rsvp_activity: InvitationActivity[];
  delivery_attempts: InvitationDeliveryAttempt[];
  reminder_preparations: InvitationReminderPreparation[];
  delivery: InvitationDeliveryConfiguration;
  coordination: {
    planned_guest_count: number | null;
    confirmed_party_size: number;
    difference_from_planned_guest_count: number | null;
    pending_response_count: number;
    workflow_review: string;
    automatic_changes: unknown[];
    notice: string;
  };
}

export interface InvitationGuestInput {
  name: string;
  email?: string | null;
  phone?: string | null;
  group_name?: string | null;
  party_size?: number;
  notes?: string | null;
  dietary_requirements?: string[];
  accessibility_requirements?: string[];
  accommodation_requirements?: string[];
}
