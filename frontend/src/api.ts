import type {
  DashboardCommandResult,
  BudgetAIGuidance,
  BudgetChangeRequest,
  BudgetProposal,
  BudgetSummary,
  DashboardSnapshot,
  DashboardTask,
  EventExpense,
  RecoveryAIGuidance,
  EventPlan,
  EventRequest,
  EventStatus,
  RecoveryCase,
  RecoveryDisruption,
  RecoveryProposal,
  CostCategory,
  ScenarioRequest,
  ScenarioResult,
  TaskStatus,
  WorkflowSnapshot,
  WorkflowAIGuidance,
  InvitationDeliveryBatch,
  InvitationDeliveryPreview,
  InvitationDuplicateSuggestion,
  InvitationDraft,
  InvitationGuest,
  InvitationGuestInput,
  InvitationOverview,
  InvitationReminderPreparation,
  InvitationTone,
} from "./types";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export interface ApiInfo {
  app: string;
  message: string;
  status: string;
}

export function getDashboard(): Promise<DashboardSnapshot> {
  return request<DashboardSnapshot>("/api/v1/dashboard");
}

export function getEventBudget(eventId: string): Promise<BudgetSummary> {
  return request<BudgetSummary>(
    `/api/v1/dashboard/events/${encodeURIComponent(eventId)}/budget`,
  );
}

export function createEventExpense(
  eventId: string,
  input: {
    category: CostCategory;
    amount: number;
    expense_date: string;
    description: string;
    payment_status: "committed" | "paid";
    vendor_name?: string;
    idempotency_key: string;
  },
): Promise<EventExpense> {
  return request<EventExpense>(
    `/api/v1/dashboard/events/${encodeURIComponent(eventId)}/expenses`,
    input,
  );
}

export function updateEventExpense(
  eventId: string,
  expenseId: string,
  input: Partial<Omit<EventExpense, "id" | "event_id" | "created_at" | "updated_at">>,
): Promise<EventExpense> {
  return request<EventExpense>(
    `/api/v1/dashboard/events/${encodeURIComponent(eventId)}/expenses/${encodeURIComponent(expenseId)}`,
    input,
    "PATCH",
  );
}

export function createBudgetProposal(
  eventId: string,
  input: {
    changes: BudgetChangeRequest;
    rationale: string;
    idempotency_key: string;
  },
): Promise<BudgetProposal> {
  return request<BudgetProposal>(
    `/api/v1/dashboard/events/${encodeURIComponent(eventId)}/budget/proposals`,
    input,
  );
}

export function decideBudgetProposal(
  proposalId: string,
  decision: "approve" | "reject",
): Promise<BudgetProposal> {
  return request<BudgetProposal>(
    `/api/v1/dashboard/budget-proposals/${encodeURIComponent(proposalId)}/${decision}`,
    undefined,
    "POST",
  );
}

export function getBudgetAIGuidance(eventId: string): Promise<BudgetAIGuidance> {
  return request<BudgetAIGuidance>(
    `/api/v1/dashboard/events/${encodeURIComponent(eventId)}/budget/ai-guidance`,
    {},
  );
}

export function getEventWorkflow(eventId: string): Promise<WorkflowSnapshot> {
  return request<WorkflowSnapshot>(
    `/api/v1/dashboard/events/${encodeURIComponent(eventId)}/workflow`,
  );
}

export function generateEventWorkflow(eventId: string): Promise<WorkflowSnapshot> {
  return request<WorkflowSnapshot>(
    `/api/v1/dashboard/events/${encodeURIComponent(eventId)}/workflow/generate`,
    undefined,
    "POST",
  );
}

export function getWorkflowAIGuidance(eventId: string): Promise<WorkflowAIGuidance> {
  return request<WorkflowAIGuidance>(
    `/api/v1/dashboard/events/${encodeURIComponent(eventId)}/workflow/ai-guidance`,
    undefined,
    "POST",
  );
}

export function getRecoveryAIGuidance(caseId: string): Promise<RecoveryAIGuidance> {
  return request<RecoveryAIGuidance>(
    `/api/v1/dashboard/recovery-cases/${encodeURIComponent(caseId)}/ai-guidance`,
    undefined,
    "POST",
  );
}

export function getRecoveryCases(eventId: string): Promise<RecoveryCase[]> {
  return request<RecoveryCase[]>(
    `/api/v1/dashboard/events/${encodeURIComponent(eventId)}/recovery-cases`,
  );
}

export function reportRecoveryCase(
  eventId: string,
  input: {
    disruption_type: RecoveryDisruption;
    description: string;
    task_id?: string;
    changes?: {
      budget?: number;
      guest_count?: number;
      event_date?: string;
      estimated_costs?: Partial<Record<CostCategory, number>>;
    };
  },
): Promise<RecoveryCase> {
  return request<RecoveryCase>(
    `/api/v1/dashboard/events/${encodeURIComponent(eventId)}/recovery-cases`,
    input,
  );
}

export function resolveRecoveryCase(
  caseId: string,
  summary: string,
): Promise<RecoveryCase> {
  return request<RecoveryCase>(
    `/api/v1/dashboard/recovery-cases/${encodeURIComponent(caseId)}/resolve`,
    { summary },
  );
}

export function proposeRecoveryOption(
  caseId: string,
  optionId: string,
): Promise<RecoveryCase> {
  return request<RecoveryCase>(
    `/api/v1/dashboard/recovery-cases/${encodeURIComponent(caseId)}/proposals`,
    { option_id: optionId },
  );
}

export function decideRecoveryProposal(
  proposalId: string,
  decision: "approve" | "reject",
): Promise<RecoveryProposal> {
  return request<RecoveryProposal>(
    `/api/v1/dashboard/recovery-proposals/${encodeURIComponent(proposalId)}/${decision}`,
    undefined,
    "POST",
  );
}

export function createDashboardTask(input: {
  title: string;
  due_date?: string | null;
  event_id?: string;
  description?: string;
  priority?: "low" | "medium" | "high";
  assigned_to?: string | null;
  estimated_cost?: number | null;
  completion_criteria?: string;
  dependencies?: string[];
}): Promise<DashboardTask> {
  return request<DashboardTask>("/api/v1/dashboard/tasks", input);
}

export function updateDashboardTask(
  taskId: string,
  changes: Partial<{
    title: string;
    due_date: string | null;
    status: TaskStatus;
    description: string;
    priority: "low" | "medium" | "high";
    assigned_to: string | null;
    estimated_cost: number | null;
    completion_criteria: string;
    dependencies: string[];
  }>,
): Promise<DashboardTask> {
  return request<DashboardTask>(
    `/api/v1/dashboard/tasks/${encodeURIComponent(taskId)}`,
    changes,
    "PATCH",
  );
}

export function updateDashboardEvent(
  eventId: string,
  status: EventStatus,
): Promise<DashboardSnapshot> {
  return request<DashboardSnapshot>(
    `/api/v1/dashboard/events/${encodeURIComponent(eventId)}`,
    { status },
    "PATCH",
  );
}

export function runDashboardCommand(
  message: string,
  conversationId?: string,
): Promise<DashboardCommandResult> {
  return request<DashboardCommandResult>("/api/v1/dashboard/command", {
    message,
    ...(conversationId ? { conversation_id: conversationId } : {}),
  });
}

export function getInvitationOverview(eventId: string): Promise<InvitationOverview> {
  return request<InvitationOverview>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}`,
  );
}

export function getInvitationDuplicates(eventId: string): Promise<InvitationDuplicateSuggestion[]> {
  return request<InvitationDuplicateSuggestion[]>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}/duplicates`,
  );
}

export function createInvitationGuest(
  eventId: string,
  input: InvitationGuestInput,
): Promise<InvitationGuest> {
  return request<InvitationGuest>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}/guests`,
    input,
  );
}

export function updateInvitationGuest(
  eventId: string,
  guestId: string,
  input: Partial<InvitationGuestInput> & { duplicate_of_id?: string | null; invitation_status?: "not_prepared" | "drafted" },
): Promise<InvitationGuest> {
  return request<InvitationGuest>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}/guests/${encodeURIComponent(guestId)}`,
    input,
    "PATCH",
  );
}

export function deleteInvitationGuest(eventId: string, guestId: string): Promise<void> {
  return request<void>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}/guests/${encodeURIComponent(guestId)}`,
    undefined,
    "DELETE",
  );
}

export function recordInvitationRsvp(
  eventId: string,
  guestId: string,
  input: {
    rsvp_status: "awaiting_response" | "attending" | "not_attending";
    party_size?: number;
    notes?: string | null;
    dietary_requirements?: string[];
    accessibility_requirements?: string[];
    accommodation_requirements?: string[];
    source: "manual";
  },
): Promise<InvitationGuest> {
  return request<InvitationGuest>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}/guests/${encodeURIComponent(guestId)}/rsvp`,
    input,
  );
}

export function generateInvitationDraft(
  eventId: string,
  input: {
    tone: InvitationTone;
    language: string;
    group_name?: string;
    rsvp_deadline?: string;
    instructions?: string;
  },
): Promise<InvitationDraft> {
  return request<InvitationDraft>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}/drafts/generate`,
    input,
  );
}

export function createInvitationDraft(
  eventId: string,
  input: {
    kind: "invitation" | "reminder";
    subject: string;
    body: string;
    tone: InvitationTone;
    language: string;
    group_name?: string | null;
    rsvp_deadline?: string | null;
  },
): Promise<InvitationDraft> {
  return request<InvitationDraft>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}/drafts`,
    input,
  );
}

export function updateInvitationDraft(
  eventId: string,
  draftId: string,
  input: Partial<{
    subject: string;
    body: string;
    tone: InvitationTone;
    language: string;
    group_name: string | null;
    rsvp_deadline: string | null;
  }>,
): Promise<InvitationDraft> {
  return request<InvitationDraft>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}/drafts/${encodeURIComponent(draftId)}`,
    input,
    "PATCH",
  );
}

export function previewInvitationDelivery(
  eventId: string,
  input: { draft_id: string; guest_ids: string[] },
): Promise<InvitationDeliveryPreview> {
  return request<InvitationDeliveryPreview>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}/delivery/preview`,
    input,
  );
}

export function sendInvitationDelivery(
  eventId: string,
  input: { draft_id: string; guest_ids: string[]; approved: true; idempotency_key: string },
): Promise<InvitationDeliveryBatch> {
  return request<InvitationDeliveryBatch>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}/delivery/send`,
    input,
  );
}

export function retryInvitationDelivery(
  eventId: string,
  attemptId: string,
  input: { approved: true; idempotency_key: string },
): Promise<InvitationDeliveryBatch> {
  return request<InvitationDeliveryBatch>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}/delivery-attempts/${encodeURIComponent(attemptId)}/retry`,
    input,
  );
}

export function prepareInvitationReminders(
  eventId: string,
  input: {
    guest_ids?: string[];
    tone: InvitationTone;
    language: string;
    rsvp_deadline?: string;
    instructions?: string;
  },
): Promise<InvitationReminderPreparation> {
  return request<InvitationReminderPreparation>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}/reminders/prepare`,
    input,
  );
}

export function sendInvitationReminder(
  eventId: string,
  preparationId: string,
  input: { approved: true; idempotency_key: string },
): Promise<InvitationReminderPreparation> {
  return request<InvitationReminderPreparation>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}/reminders/${encodeURIComponent(preparationId)}/send`,
    input,
  );
}

export function cancelInvitationReminder(
  eventId: string,
  preparationId: string,
): Promise<InvitationReminderPreparation> {
  return request<InvitationReminderPreparation>(
    `/api/v1/invitations/events/${encodeURIComponent(eventId)}/reminders/${encodeURIComponent(preparationId)}/cancel`,
    {},
  );
}

async function request<T>(
  path: string,
  body?: unknown,
  method?: "POST" | "PATCH" | "DELETE",
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: method ?? (body === undefined ? "GET" : "POST"),
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error(
      `Could not reach the Planova API at ${API_BASE_URL}. Check that the backend is running.`,
    );
  }

  if (!response.ok) {
    const errorBody: unknown = await response.json().catch(() => null);
    throw new Error(formatApiError(errorBody, response.status));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function formatApiError(body: unknown, status: number): string {
  if (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    Array.isArray(body.detail)
  ) {
    return body.detail
      .map((item: { loc?: unknown[]; msg?: string }) => {
        const field = item.loc?.slice(1).join(".") || "request";
        return `${field}: ${item.msg ?? "invalid value"}`;
      })
      .join(" · ");
  }
  if (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof body.detail === "string"
  ) {
    return body.detail;
  }
  return `The API returned an error (HTTP ${status}). Please try again.`;
}

export function createEvent(event: EventRequest): Promise<EventPlan> {
  return request<EventPlan>("/api/v1/events", event);
}

export function analyzeScenario(
  input: ScenarioRequest,
): Promise<ScenarioResult> {
  return request<ScenarioResult>("/api/v1/events/scenario-analysis", input);
}

export function getBackendHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/health");
}

export function getApiInfo(): Promise<ApiInfo> {
  return request<ApiInfo>("/");
}

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}
