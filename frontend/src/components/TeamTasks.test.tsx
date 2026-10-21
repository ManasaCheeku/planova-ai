import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createDashboardTask, updateDashboardTask } from "../api";
import type { DashboardSnapshot, DashboardTask } from "../types";
import TeamTasks from "./TeamTasks";

vi.mock("../api", () => ({
  createDashboardTask: vi.fn(),
  updateDashboardTask: vi.fn(),
}));

function makeTask(overrides: Partial<DashboardTask> = {}): DashboardTask {
  return {
    id: "task-1",
    created_at: "2026-01-01T00:00:00+00:00",
    title: "Prepare run sheet",
    due_date: "2026-06-01",
    status: "pending",
    overdue: false,
    blocked: false,
    blockers: [],
    event_id: null,
    description: "Prepare the event-day sequence.",
    priority: "high",
    assigned_to: "Asha",
    estimated_cost: null,
    completion_criteria: "Organizer approves the sequence.",
    dependencies: [],
    generated: false,
    ...overrides,
  };
}

function makeSnapshot(tasks: DashboardTask[]): DashboardSnapshot {
  return {
    updated_at: "2026-01-01T00:00:00+00:00",
    events: [],
    tasks,
    risk_alerts: [],
    summary: {
      total_events: 0,
      upcoming_events: 0,
      completed_events: 0,
      cancelled_events: 0,
      planned_budget_total: null,
      known_estimated_costs: null,
      remaining_known_estimate_budget: null,
      estimated_costs_by_category: {},
      budget_totals_by_currency: [],
      estimated_costs_by_currency: [],
      expenditure_tracking_available: true,
      task_counts: {
        pending: tasks.filter((task) => task.status === "pending").length,
        in_progress: tasks.filter((task) => task.status === "in_progress").length,
        overdue: tasks.filter((task) => task.overdue).length,
        blocked: tasks.filter((task) => task.blocked).length,
        completed: tasks.filter((task) => task.status === "completed").length,
      },
      risk_counts: { low: 0, medium: 0, high: 0 },
    },
    capabilities: {
      tasks: true,
      event_status_updates: true,
      approvals: false,
      notifications: false,
      calendar_integrations: false,
      email_or_sms_delivery: false,
      ai_model_configured: false,
    },
  };
}

describe("Team & Tasks coordination", () => {
  const onRefresh = vi.fn<() => Promise<boolean>>();

  beforeEach(() => {
    onRefresh.mockResolvedValue(true);
    vi.mocked(createDashboardTask).mockResolvedValue(makeTask());
    vi.mocked(updateDashboardTask).mockResolvedValue(makeTask());
  });

  it("shows real assignment progress and filters saved tasks by person, status, priority, and event group", () => {
    const pending = makeTask({ id: "pending-1", overdue: true });
    const completed = makeTask({
      id: "completed-1",
      title: "Confirm supplier arrival",
      status: "completed",
      priority: "medium",
      overdue: false,
    });
    render(
      <TeamTasks
        snapshot={makeSnapshot([pending, completed])}
        loading={false}
        error=""
        onRefresh={onRefresh}
      />,
    );

    expect(screen.getByText("1 of 2 tasks completed")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Person"), { target: { value: "asha" } });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "pending" } });
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "high" } });
    fireEvent.change(screen.getByLabelText("Event"), { target: { value: "" } });

    expect(screen.getByRole("heading", { name: "Prepare run sheet" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Confirm supplier arrival" })).toBeNull();
    expect(screen.getByText(/Overdue/)).toBeTruthy();
  });

  it("creates assigned work with a dependency and reports the persisted result", async () => {
    const prerequisite = makeTask({
      id: "task-prerequisite",
      title: "Confirm floor plan",
      priority: "medium",
    });
    vi.mocked(createDashboardTask).mockResolvedValue(
      makeTask({ title: "Prepare seating chart", dependencies: [prerequisite.id] }),
    );
    render(
      <TeamTasks
        snapshot={makeSnapshot([prerequisite])}
        loading={false}
        error=""
        onRefresh={onRefresh}
      />,
    );
    fireEvent.change(screen.getByLabelText("Task title"), {
      target: { value: "Prepare seating chart" },
    });
    fireEvent.change(screen.getByLabelText("Assign to"), {
      target: { value: "Meera" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Confirm floor plan/ }));
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));

    await waitFor(() => expect(createDashboardTask).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Prepare seating chart",
        assigned_to: "Meera",
        dependencies: [prerequisite.id],
      }),
    ));
    expect(await screen.findByRole("status")).toBeTruthy();
  });

  it("edits saved task details and sends explicit status updates", async () => {
    const task = makeTask({ id: "editable-task" });
    render(
      <TeamTasks
        snapshot={makeSnapshot([task])}
        loading={false}
        error=""
        onRefresh={onRefresh}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Task title"), {
      target: { value: "Finalize event run sheet" },
    });
    fireEvent.change(screen.getByLabelText("Assign to"), {
      target: { value: "Nisha" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save task changes" }));

    await waitFor(() => expect(updateDashboardTask).toHaveBeenCalledWith(
      "editable-task",
      expect.objectContaining({
        title: "Finalize event run sheet",
        assigned_to: "Nisha",
      }),
    ));
    fireEvent.change(screen.getByLabelText("Status for Prepare run sheet"), {
      target: { value: "in_progress" },
    });
    await waitFor(() => expect(updateDashboardTask).toHaveBeenCalledWith(
      "editable-task",
      { status: "in_progress" },
    ));
  });

  it("renders blocked task state and empty, loading, and error feedback", () => {
    const blocked = makeTask({
      id: "blocked-task",
      title: "Confirm final layout",
      blocked: true,
      blockers: ["Confirm floor plan"],
      dependencies: ["parent-task"],
    });
    const { rerender } = render(
      <TeamTasks
        snapshot={makeSnapshot([blocked])}
        loading={false}
        error=""
        onRefresh={onRefresh}
      />,
    );
    expect(screen.getByText("Blocked")).toBeTruthy();
    expect(screen.getByText(/Confirm floor plan/)).toBeTruthy();

    rerender(
      <TeamTasks snapshot={null} loading error="Backend unavailable" onRefresh={onRefresh} />,
    );
    expect(screen.getByRole("status").textContent).toContain("Loading");
    rerender(
      <TeamTasks snapshot={makeSnapshot([])} loading={false} error="" onRefresh={onRefresh} />,
    );
    expect(screen.getByText(/No tasks have been saved yet/)).toBeTruthy();
    rerender(
      <TeamTasks snapshot={makeSnapshot([])} loading={false} error="Could not load tasks" onRefresh={onRefresh} />,
    );
    expect(screen.getByRole("alert").textContent).toContain("Could not load tasks");
  });
});
