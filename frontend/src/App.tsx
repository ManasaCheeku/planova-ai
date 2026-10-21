import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";
import BrandMark from "./components/BrandMark";
import Dashboard from "./components/Dashboard";
import BudgetGuardian from "./components/BudgetGuardian";
import EventAutopilot from "./components/EventAutopilot";
import EventForm from "./components/EventForm";
import Invitations from "./components/Invitations";
import TeamTasks from "./components/TeamTasks";
import PlanResults from "./components/PlanResults";
import ScenarioPanel from "./components/ScenarioPanel";
import {
  analyzeScenario,
  createEvent,
  getDashboard,
  getApiBaseUrl,
  getApiInfo,
  getBackendHealth,
  runDashboardCommand,
  type ApiInfo,
} from "./api";
import type {
  DashboardSnapshot,
  EventPlan,
  EventRequest,
  EventStatus,
  ScenarioResult,
} from "./types";

interface SessionEvent {
  id: string;
  plan: EventPlan;
  createdAt: number;
  status: EventStatus;
}

const primaryNavigation = [
  { path: "/", label: "Dashboard", icon: "dashboard" },
  { path: "/create", label: "Create event", icon: "create" },
  { path: "/events", label: "My events", icon: "events" },
  { path: "/invitations", label: "Invitations & RSVP", icon: "invitations" },
  { path: "/tasks", label: "Team & tasks", icon: "tasks" },
  { path: "/risks", label: "Risk intelligence", icon: "risk" },
] as const;
type NavigationIcon = (typeof primaryNavigation)[number]["icon"] | "settings";

function NavigationGlyph({ name }: { name: NavigationIcon }) {
  const paths: Record<NavigationIcon, string> = {
    dashboard: "M3.5 3.5h5v5h-5zM10.5 3.5h5v5h-5zM3.5 10.5h5v5h-5zM10.5 10.5h5v5h-5z",
    create: "M9 2.5v13M2.5 9h13",
    events: "M4 3.5v2M14 3.5v2M3 5.5h12v10H3zM3 8h12",
    invitations: "M2.5 4h13v10h-13zM2.5 4 9 9l6.5-5M5 12.5h8",
    tasks: "M3 4.5h2l1 1 2-2M9 4.5h6M3 9h2l1 1 2-2M9 9h6M3 13.5h2l1 1 2-2M9 13.5h6",
    risk: "M2.5 9h3l2-4 3.2 8 2-4h3.8",
    settings: "M9 2.8v1.4M9 13.8v1.4M15.2 9h-1.4M4.2 9H2.8M13.4 4.6l-1 1M5.6 12.4l-1 1M13.4 13.4l-1-1M5.6 5.6l-1-1M12.4 9A3.4 3.4 0 1 1 5.6 9a3.4 3.4 0 0 1 6.8 0Z",
  };
  return (
    <svg viewBox="0 0 18 18" aria-hidden="true" focusable="false">
      <path d={paths[name]} />
    </svg>
  );
}

function AppLink({
  href,
  navigate,
  onNavigate,
  className,
  children,
  ...props
}: {
  href: string;
  navigate: (path: string) => void;
  onNavigate?: () => void;
  className?: string;
  children: ReactNode;
  "aria-current"?: "page" | undefined;
}) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    navigate(href);
    onNavigate?.();
  }

  return (
    <a href={href} onClick={handleClick} className={className} {...props}>
      {children}
    </a>
  );
}

function formatMoney(amount: number, currency = "INR") {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(amount);
}

function formatDate(value: string | null | undefined) {
  if (!value) return "Date not provided";
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function readinessLabel(status: EventPlan["readiness"]["status"]) {
  return status.replaceAll("_", " ");
}

function eventIdFromPath(path: string) {
  if (!path.startsWith("/events/")) return "";
  try {
    return decodeURIComponent(path.slice("/events/".length));
  } catch {
    return "";
  }
}

function App() {
  const [path, setPath] = useState(window.location.pathname);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [dashboard, setDashboard] = useState<DashboardSnapshot | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const [activeEventId, setActiveEventId] = useState("");
  const [scenario, setScenario] = useState<ScenarioResult | null>(null);
  const [scenarioBusy, setScenarioBusy] = useState(false);
  const [scenarioError, setScenarioError] = useState("");
  const [backendStatus, setBackendStatus] = useState<
    "checking" | "connected" | "disconnected"
  >("checking");
  const [backendError, setBackendError] = useState("");
  const [apiInfo, setApiInfo] = useState<ApiInfo | null>(null);
  const [apiInfoError, setApiInfoError] = useState("");
  const [draftForCreate, setDraftForCreate] = useState<EventRequest | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const mobileMenuButtonRef = useRef<HTMLButtonElement>(null);
  const mainRef = useRef<HTMLElement>(null);

  function navigate(nextPath: string) {
    if (nextPath !== window.location.pathname) {
      window.history.pushState({}, "", nextPath);
    }
    setPath(nextPath);
    setFormError("");
    setScenarioError("");
    if (nextPath !== path) setScenario(null);
    if (nextPath.startsWith("/events/")) setActiveEventId(eventIdFromPath(nextPath));
  }

  function editProposedDraft(draft: EventRequest) {
    setDraftForCreate(draft);
    navigate("/create");
  }

  async function refreshConnection() {
    setBackendStatus("checking");
    setBackendError("");
    setApiInfoError("");
    const [health, info] = await Promise.allSettled([getBackendHealth(), getApiInfo()]);

    if (health.status === "fulfilled" && health.value.status === "healthy") {
      setBackendStatus("connected");
    } else {
      setBackendStatus("disconnected");
      setBackendError(
        health.status === "rejected"
          ? health.reason instanceof Error
            ? health.reason.message
            : "Could not check the backend connection."
          : "The backend reported an unhealthy status.",
      );
    }

    if (info.status === "fulfilled") {
      setApiInfo(info.value);
    } else {
      setApiInfo(null);
      setApiInfoError(
        info.reason instanceof Error
          ? info.reason.message
          : "Could not load product information from the backend.",
      );
    }
  }

  async function refreshDashboard(): Promise<boolean> {
    setDashboardLoading(true);
    setDashboardError("");
    try {
      const snapshot = await getDashboard();
      setDashboard(snapshot);
      setEvents(
        snapshot.events.map(({ id, created_at, status, plan }) => ({
          id,
          plan,
          createdAt: Date.parse(created_at),
          status,
        })),
      );
      setBackendStatus("connected");
      return true;
    } catch (error) {
      setDashboardError(
        error instanceof Error ? error.message : "Could not load dashboard data.",
      );
      return false;
    } finally {
      setDashboardLoading(false);
    }
  }

  function acceptDashboardSnapshot(snapshot: DashboardSnapshot) {
    setDashboard(snapshot);
    setEvents(
      snapshot.events.map(({ id, created_at, status, plan }) => ({
        id,
        plan,
        createdAt: Date.parse(created_at),
        status,
      })),
    );
  }

  useEffect(() => {
    void refreshConnection();
    void refreshDashboard();
  }, []);

  useEffect(() => {
    const onPopState = () => {
      const currentPath = window.location.pathname;
      setPath(currentPath);
      setActiveEventId(eventIdFromPath(currentPath));
      setMobileNavOpen(false);
      setFormError("");
      setScenarioError("");
      setScenario(null);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
    mainRef.current?.focus({ preventScroll: true });
  }, [path]);

  useEffect(() => {
    if (!mobileNavOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMobileNavOpen(false);
        mobileMenuButtonRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileNavOpen]);

  const currentEventId = eventIdFromPath(path);
  const selectedEvent = events.find((item) => item.id === currentEventId);
  const activeRiskEvent =
    events.find((item) => item.id === activeEventId) ?? events[0];
  async function handleCreate(event: EventRequest) {
    setBusy(true);
    setFormError("");
    try {
      const plan = await createEvent(event);
      const id = plan.event_id;
      if (!id) {
        throw new Error("The backend response did not include the saved event ID.");
      }
      const created: SessionEvent = {
        id,
        plan,
        createdAt: plan.created_at ? Date.parse(plan.created_at) : Date.now(),
        status: "scheduled",
      };
      setEvents((current) => [created, ...current]);
      setActiveEventId(id);
      setScenario(null);
      setBackendStatus("connected");
      void refreshDashboard();
      navigate(`/events/${encodeURIComponent(id)}`);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "The event plan could not be created.");
    } finally {
      setBusy(false);
    }
  }

  async function handleScenario(changes: {
    guest_count?: number;
    budget?: number;
    event_date?: string;
  }) {
    if (!activeRiskEvent) return;
    setScenarioBusy(true);
    setScenarioError("");
    setScenario(null);
    try {
      const result = await analyzeScenario({
        event: activeRiskEvent.plan.event,
        changes,
      });
      setScenario(result);
      setBackendStatus("connected");
    } catch (error) {
      setScenarioError(error instanceof Error ? error.message : "Scenario analysis failed.");
    } finally {
      setScenarioBusy(false);
    }
  }

  function selectRiskEvent(id: string) {
    setActiveEventId(id);
    setScenario(null);
    setScenarioError("");
  }

  const isKnownPage =
    path === "/" ||
    path === "/create" ||
    path === "/events" ||
    path === "/invitations" ||
    path === "/tasks" ||
    path === "/risks" ||
    path === "/settings" ||
    path.startsWith("/events/");
  const pageTitle = path === "/"
    ? "Dashboard"
    : path === "/create"
      ? "Create event"
      : path === "/events"
        ? "My events"
        : path === "/invitations"
          ? "Invitations & RSVP"
        : path === "/tasks"
          ? "Team & tasks"
        : path.startsWith("/events/")
          ? "Event details"
          : path === "/risks"
            ? "Risk intelligence"
            : "Settings";

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className={`sidebar${mobileNavOpen ? " sidebar-open" : ""}`} aria-label="Main navigation">
        <div className="sidebar-brand">
          <BrandMark />
          <span className="brand-caption">EVENT INTELLIGENCE</span>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav id="primary-navigation" className="primary-nav" aria-label="Workspace">
          {primaryNavigation.map((item) => {
            const active = item.path === "/"
              ? path === "/"
              : item.path === "/events"
                ? path === "/events" || path.startsWith("/events/")
                : path === item.path;
            return (
              <AppLink
                key={item.path}
                href={item.path}
                navigate={navigate}
                onNavigate={() => setMobileNavOpen(false)}
                className={`nav-link${active ? " nav-link-active" : ""}`}
                aria-current={active ? "page" : undefined}
              >
                <span className="nav-icon"><NavigationGlyph name={item.icon} /></span>
                <span>{item.label}</span>
              </AppLink>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <span className="note-orb" aria-hidden="true">✳</span>
            <p>Every detail aligned.<br /><strong>Every moment extraordinary.</strong></p>
          </div>
          <AppLink
            href="/settings"
            navigate={navigate}
            onNavigate={() => setMobileNavOpen(false)}
            className={`nav-link settings-link${path === "/settings" ? " nav-link-active" : ""}`}
            aria-current={path === "/settings" ? "page" : undefined}
          >
            <span className="nav-icon"><NavigationGlyph name="settings" /></span>
            <span>Settings</span>
          </AppLink>
          <div className="sidebar-footer">PLANOVA AI <span>·</span> EVENT PLANNING</div>
        </div>
      </aside>

      {mobileNavOpen && (
        <button
          className="nav-scrim"
          type="button"
          aria-label="Close navigation"
          onClick={() => {
            setMobileNavOpen(false);
            mobileMenuButtonRef.current?.focus();
          }}
        />
      )}

      <div className="workspace">
        <header className="topbar">
          <button
            ref={mobileMenuButtonRef}
            className="mobile-menu-button"
            type="button"
            aria-label={mobileNavOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={mobileNavOpen}
            aria-controls="primary-navigation"
            onClick={() => setMobileNavOpen((open) => !open)}
          >
            <span />
            <span />
          </button>
          <div className="breadcrumb"><span>WORKSPACE</span><span aria-hidden="true">/</span><strong>{pageTitle}</strong></div>
          <button
            className={`topbar-status connection-top connection-${backendStatus}`}
            type="button"
            onClick={() => navigate("/settings")}
            aria-label={`Backend ${backendStatus}. Open settings to review connection.`}
          >
            <span className="status-dot" />
            <span>{backendStatus === "checking" ? "Checking API" : backendStatus === "connected" ? "API connected" : "API unavailable"}</span>
          </button>
        </header>

        <main ref={mainRef} id="main-content" className="main-content" tabIndex={-1}>
          {path === "/" && (
            <Dashboard
              snapshot={dashboard}
              loading={dashboardLoading}
              error={dashboardError}
              onRefresh={refreshDashboard}
              onSnapshotChange={acceptDashboardSnapshot}
              onNavigate={navigate}
              onEditDraft={editProposedDraft}
            />
          )}

          {path === "/create" && (
            <div className="page-wrap">
              <PageIntro
                eyebrow="START WITH THE DETAILS"
                title="Create an event plan"
                description="Share what you know. Planova will organize your budget, surface planning risks, and show what needs attention."
              />
              <div className="session-notice"><span aria-hidden="true">i</span> Event plans are saved in the local backend SQLite database. They are not synced between installations or backed up externally.</div>
              {formError && <div className="alert alert-error" role="alert">{formError}</div>}
              <div className="form-card">
                <EventForm
                  busy={busy}
                  onSubmit={handleCreate}
                  onUnderstand={runDashboardCommand}
                  initialDraft={draftForCreate}
                  onInitialDraftApplied={() => setDraftForCreate(null)}
                />
              </div>
            </div>
          )}

          {path === "/events" && (
            <EventsPage events={events} navigate={navigate} />
          )}

          {path === "/invitations" && (
            <Invitations
              events={events.map(({ id, plan }) => ({
                id,
                name: plan.event.event_name,
                eventType: plan.event.event_type,
                eventDate: plan.event.event_date,
              }))}
              onNavigateToEvent={(id) => navigate(`/events/${encodeURIComponent(id)}`)}
              onNavigate={navigate}
            />
          )}

          {path === "/tasks" && (
            <TeamTasks
              snapshot={dashboard}
              loading={dashboardLoading}
              error={dashboardError}
              onRefresh={refreshDashboard}
            />
          )}

          {path.startsWith("/events/") && (
            selectedEvent ? (
              <EventDetails
                item={selectedEvent}
                navigate={navigate}
                onEventChanged={refreshDashboard}
              />
            ) : (
              <MissingEvent navigate={navigate} />
            )
          )}

          {path === "/risks" && (
            <RiskPage
              events={events}
              activeEvent={activeRiskEvent}
              activeEventId={activeRiskEvent?.id ?? ""}
              onSelectEvent={selectRiskEvent}
              scenario={scenario}
              scenarioBusy={scenarioBusy}
              scenarioError={scenarioError}
              onAnalyze={handleScenario}
              navigate={navigate}
            />
          )}

          {path === "/settings" && (
            <SettingsPage
              backendStatus={backendStatus}
              backendError={backendError}
              apiInfo={apiInfo}
              apiInfoError={apiInfoError}
              aiConfigured={dashboard?.capabilities.ai_model_configured ?? null}
              onCheck={refreshConnection}
            />
          )}

          {!isKnownPage && <MissingPage navigate={navigate} />}
        </main>
      </div>
    </div>
  );
}

function PageIntro({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-intro">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}

function EventsPage({
  events,
  navigate,
}: {
  events: SessionEvent[];
  navigate: (path: string) => void;
}) {
  return (
    <div className="page-wrap">
      <PageIntro
        eyebrow="YOUR WORKSPACE"
        title="My events"
        description="Event plans persisted by this local Planova backend."
        action={<button className="button button-primary" type="button" onClick={() => navigate("/create")}>Create event <span aria-hidden="true">↗</span></button>}
      />
      <div className="session-notice"><span aria-hidden="true">i</span> Plans are saved in the local backend SQLite database. They are not synced to other installations or backed up externally.</div>
      {events.length ? (
        <div className="event-list">
          {events.map(({ id, plan }) => (
            <button className="event-list-card" type="button" key={id} onClick={() => navigate(`/events/${encodeURIComponent(id)}`)}>
              <span className="event-card-mark" aria-hidden="true">✳</span>
              <span className="event-list-main">
                <span className="eyebrow">{plan.event.event_type ?? "Event type not supplied"}</span>
                <strong>{plan.event.event_name}</strong>
                <span>{plan.event.location ?? "Location not supplied"} <i>·</i> {formatDate(plan.event.event_date)}</span>
              </span>
              <span className="event-list-budget"><small>PLANNING BUDGET</small><strong>{formatMoney(plan.budget_analysis.budget, plan.event.currency)}</strong></span>
              <span className={`readiness-pill readiness-${plan.readiness.status}`}><span className="readiness-dot" />{readinessLabel(plan.readiness.status)}</span>
              <span className="row-chevron" aria-hidden="true">→</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="empty-card empty-page">
          <span className="empty-art" aria-hidden="true">◇</span>
          <div><h2>No saved event plans</h2><p>Create a plan to see its returned budget, requirements, and readiness here.</p></div>
          <button className="button button-primary" type="button" onClick={() => navigate("/create")}>Create an event plan <span aria-hidden="true">↗</span></button>
        </div>
      )}
    </div>
  );
}

function EventDetails({
  item,
  navigate,
  onEventChanged,
}: {
  item: SessionEvent;
  navigate: (path: string) => void;
  onEventChanged: () => Promise<boolean>;
}) {
  const { plan } = item;
  return (
    <div className="page-wrap">
      <div className="back-row"><button className="text-link" type="button" onClick={() => navigate("/events")}>← Back to my events</button><span className="session-tag">SAVED PLAN</span></div>
      <PageIntro
        eyebrow={`${plan.event.event_type ?? "Event type not supplied"} · ${formatDate(plan.event.event_date)}${plan.event.event_time ? ` · ${plan.event.event_time.slice(0, 5)}` : ""}`}
        title={plan.event.event_name}
        description={`${plan.event.purpose ? `${plan.event.purpose} · ` : ""}${plan.event.location ?? "Location not supplied"} · ${plan.event.guest_count?.toLocaleString() ?? "Guest count not supplied"} guests`}
        action={<span className={`readiness-pill readiness-${plan.readiness.status}`}><span className="readiness-dot" />{readinessLabel(plan.readiness.status)} · {plan.readiness.score}/100</span>}
      />
      <section className="detail-summary">
        <div><span className="metric-label">Planning budget</span><strong>{formatMoney(plan.budget_analysis.budget, plan.event.currency)}</strong></div>
        <div><span className="metric-label">Cost estimates</span><strong>{plan.budget_analysis.estimated_total === null ? "Not available" : formatMoney(plan.budget_analysis.estimated_total, plan.event.currency)}</strong><small>{plan.budget_analysis.estimated_total === null ? "No estimates provided" : "User-provided estimates"}</small></div>
        <div><span className="metric-label">Requirements</span><strong>{plan.event.requirements.length}</strong><small>{plan.event.requirements.length === 1 ? "Planning priority" : "Planning priorities"}</small></div>
        <div><span className="metric-label">Risks identified</span><strong>{plan.risks.length}</strong><small>With suggested mitigations</small></div>
      </section>
      <section className="requirements-card">
        <div><span className="eyebrow">EVENT REQUIREMENTS</span><h2>What matters for this event</h2></div>
        {plan.event.requirements.length ? (
          <ul className="requirement-list">{plan.event.requirements.map((requirement, index) => <li key={`${index}-${requirement}`}><span aria-hidden="true">✓</span>{requirement}</li>)}</ul>
        ) : <p className="muted-copy">No specific requirements were provided for this plan.</p>}
      </section>
      {(plan.event.activities?.length || plan.event.preferences?.length || (plan.event.constraints?.length ?? 0) > 0) && (
        <section className="requirements-card">
          <div><span className="eyebrow">ACTIVITIES & PREFERENCES</span><h2>Planning details</h2></div>
          {plan.event.activities?.length ? <div><strong>Activities</strong><ul className="requirement-list">{plan.event.activities.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></div> : null}
          {plan.event.preferences?.length ? <div><strong>Preferences</strong><ul className="requirement-list">{plan.event.preferences.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></div> : null}
          {(plan.event.constraints?.length ?? 0) > 0 && <div><strong>Constraints</strong><ul className="requirement-list">{plan.event.constraints?.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></div>}
        </section>
      )}
      {plan.event.planning_suggestions && Object.values(plan.event.planning_suggestions).some((items) => items.length > 0) && (
        <section className="requirements-card">
          <div><span className="eyebrow">PROPOSED PLAN</span><h2>Editable suggestions · unconfirmed</h2></div>
          <p className="muted-copy">These saved planning ideas are not confirmed arrangements, vendor commitments, or bookings.</p>
          {plan.event.planning_suggestions.objectives.length > 0 && <div><strong>Objectives</strong><ul className="requirement-list">{plan.event.planning_suggestions.objectives.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></div>}
          {plan.event.planning_suggestions.agenda.length > 0 && <div><strong>Agenda</strong><ul className="requirement-list">{plan.event.planning_suggestions.agenda.map((item, index) => <li key={`${item.title}-${index}`}>{item.time ? `${item.time} · ` : ""}{item.title}{item.duration_minutes ? ` · ${item.duration_minutes} minutes` : ""} <small>— {item.basis}</small></li>)}</ul></div>}
          {plan.event.planning_suggestions.checklist.length > 0 && <div><strong>Checklist</strong><ul className="requirement-list">{plan.event.planning_suggestions.checklist.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></div>}
          {plan.event.planning_suggestions.personalized_ideas.length > 0 && <div><strong>Personalized ideas</strong><ul className="requirement-list">{plan.event.planning_suggestions.personalized_ideas.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></div>}
          {[...plan.event.planning_suggestions.assumptions, ...plan.event.planning_suggestions.uncertainties].map((item, index) => <p className="muted-copy" key={`${item}-${index}`}>{item}</p>)}
        </section>
      )}
      <section className="requirements-card vendor-card">
        <div><span className="eyebrow">VENDOR CONFIRMATIONS</span><h2>Confirmed vendors</h2></div>
        {plan.event.confirmed_vendors.length ? (
          <ul className="requirement-list">
            {plan.event.confirmed_vendors.map((vendor, index) => (
              <li key={`${index}-${vendor}`}><span aria-hidden="true">✓</span>{vendor}</li>
            ))}
          </ul>
        ) : <p className="muted-copy">No vendors were marked as confirmed for this plan.</p>}
      </section>
      <PlanResults plan={plan} />
      <div className="detail-actions"><button className="button button-secondary" type="button" onClick={() => navigate("/risks")}>Explore risk scenarios <span aria-hidden="true">→</span></button></div>
      <BudgetGuardian eventId={item.id} onEventChanged={onEventChanged} />
      <EventAutopilot
        eventId={item.id}
        eventName={plan.event.event_name}
        guestCount={plan.event.guest_count}
        budget={plan.budget_analysis.budget}
        currency={plan.event.currency ?? "INR"}
        onEventChanged={onEventChanged}
      />
    </div>
  );
}

function RiskPage({
  events,
  activeEvent,
  activeEventId,
  onSelectEvent,
  scenario,
  scenarioBusy,
  scenarioError,
  onAnalyze,
  navigate,
}: {
  events: SessionEvent[];
  activeEvent?: SessionEvent;
  activeEventId: string;
  onSelectEvent: (id: string) => void;
  scenario: ScenarioResult | null;
  scenarioBusy: boolean;
  scenarioError: string;
  onAnalyze: (changes: { guest_count?: number; budget?: number; event_date?: string }) => Promise<void>;
  navigate: (path: string) => void;
}) {
  return (
    <div className="page-wrap">
      <PageIntro
        eyebrow="PLAN WITH PERSPECTIVE"
        title="Risk intelligence"
        description="Explore how a change in guests, budget, or event date affects capacity, budget status, and readiness."
      />
      {events.length ? (
        <>
          {events.length > 1 && (
            <label className="field risk-event-picker">
              <span>Plan to analyze</span>
              <select value={activeEventId} onChange={(event) => onSelectEvent(event.target.value)}>
                {events.map(({ id, plan }) => <option value={id} key={id}>{plan.event.event_name}</option>)}
              </select>
            </label>
          )}
          {activeEvent && (
            <div className="risk-context">
              <span className="risk-context-mark" aria-hidden="true">⌁</span>
              <div><span className="eyebrow">ANALYZING SAVED PLAN</span><strong>{activeEvent.plan.event.event_name}</strong><span>{activeEvent.plan.event.guest_count?.toLocaleString() ?? "Guest count not supplied"} guests · {formatMoney(activeEvent.plan.event.budget, activeEvent.plan.event.currency)} budget</span></div>
              <button className="text-link" type="button" onClick={() => navigate(`/events/${encodeURIComponent(activeEvent.id)}`)}>View event <span aria-hidden="true">→</span></button>
            </div>
          )}
          {activeEvent && (
            <ScenarioPanel
              key={activeEvent.id}
              event={activeEvent.plan.event}
              busy={scenarioBusy}
              result={scenario}
              error={scenarioError}
              onAnalyze={onAnalyze}
            />
          )}
          {activeEvent && (
            <section className="risk-baseline">
              <div className="section-title-row"><div><span className="eyebrow">CURRENT SIGNALS</span><h2>Baseline risk assessment</h2></div></div>
              {activeEvent.plan.risks.length ? (
                <div className="risk-baseline-list">
                  {activeEvent.plan.risks.map((risk) => (
                    <article className="baseline-risk" key={risk.id}>
                      <span className={`risk-severity-dot severity-dot-${risk.severity}`} />
                      <div><strong>{risk.type.replaceAll("_", " ")}</strong><p>{risk.reason}</p></div>
                      <span className={`severity-badge severity-${risk.severity}`}>{risk.severity}</span>
                    </article>
                  ))}
                </div>
              ) : <div className="all-clear"><span aria-hidden="true">✓</span><div><strong>No risks identified</strong><p>Based on the details returned for this event.</p></div></div>}
            </section>
          )}
        </>
      ) : (
        <div className="empty-card empty-page">
          <span className="empty-art" aria-hidden="true">⌁</span>
          <div><h2>Create an event to explore scenarios</h2><p>Scenario analysis uses a returned event plan and recalculates impacts through the backend API. No example or placeholder event is used.</p></div>
          <button className="button button-primary" type="button" onClick={() => navigate("/create")}>Create an event plan <span aria-hidden="true">↗</span></button>
        </div>
      )}
    </div>
  );
}

function SettingsPage({
  backendStatus,
  backendError,
  apiInfo,
  apiInfoError,
  aiConfigured,
  onCheck,
}: {
  backendStatus: "checking" | "connected" | "disconnected";
  backendError: string;
  apiInfo: ApiInfo | null;
  apiInfoError: string;
  aiConfigured: boolean | null;
  onCheck: () => Promise<void>;
}) {
  return (
    <div className="page-wrap">
      <PageIntro
        eyebrow="PREFERENCES & CONNECTION"
        title="Settings"
        description="Review local application storage and check the status of your Planova backend."
      />
      <section className="settings-card">
        <div className="settings-card-heading"><div><span className="eyebrow">CONNECTION</span><h2>Backend status</h2></div><span className={`connection-badge connection-${backendStatus}`}><span />{backendStatus === "checking" ? "Checking" : backendStatus === "connected" ? "Connected" : "Unavailable"}</span></div>
        <p>Planova uses its configured API for event plan creation, scenario analysis, and this connection check.</p>
        <div className="connection-detail">
          <span>Health endpoint</span>
          <code>{getApiBaseUrl()}/health</code>
        </div>
        {backendError && <div className="alert alert-error settings-error" role="alert">{backendError}</div>}
        {apiInfoError && apiInfoError !== backendError && <div className="alert alert-error settings-error" role="alert">{apiInfoError}</div>}
        <button className="button button-secondary" type="button" onClick={onCheck} disabled={backendStatus === "checking"}>
          {backendStatus === "checking" ? <><span className="spinner" aria-hidden="true" /> Checking connection…</> : "Check connection"}
        </button>
      </section>
      <section className="settings-card product-card">
        <div><span className="eyebrow">PRODUCT</span><h2>{apiInfo?.app ?? "Planova AI"}</h2></div>
        <p>{apiInfo?.message ?? "Every detail aligned. Every moment extraordinary."}</p>
        <div className="product-capability"><span aria-hidden="true">✳</span><div><strong>Event Risk Intelligence Engine</strong><p>Event planning signals are calculated from the details you provide; external data sources are not connected.</p></div></div>
      </section>
      <section className="settings-card preferences-card">
        <div><span className="eyebrow">APPLICATION</span><h2>Local data</h2></div>
        <div className="preference-row"><div><strong>Event plan storage</strong><p>Plans and dashboard tasks are stored in a local SQLite database on this backend installation.</p></div><span className="preference-value">Local SQLite</span></div>
        <div className="preference-row"><div><strong>GenAI provider</strong><p>{aiConfigured === null ? "Provider configuration could not be determined until the Dashboard data loads." : aiConfigured ? "Configured on the backend. Requests are sent to the configured provider; credentials are not exposed to this browser." : "Not configured. Set OPENAI_API_KEY in the backend environment and restart the API to enable optional planning and recovery guidance."}</p></div><span className="preference-value">{aiConfigured === null ? "Unknown" : aiConfigured ? "Configured" : "Not configured"}</span></div>
        <div className="preference-row"><div><strong>External integrations</strong><p>No vendor, venue, weather, or calendar integrations are currently connected.</p></div><span className="preference-value">Not connected</span></div>
        <div className="preference-row"><div><strong>Currency display</strong><p>Budget values are displayed in Indian rupees.</p></div><span className="preference-value">INR (₹)</span></div>
      </section>
    </div>
  );
}

function MissingEvent({ navigate }: { navigate: (path: string) => void }) {
  return (
    <div className="page-wrap">
      <div className="empty-card empty-page">
        <span className="empty-art" aria-hidden="true">◇</span>
        <div><h1>Event plan not found</h1><p>This plan ID is not present in the backend's local event database. Check that the backend is using the same local database.</p></div>
        <button className="button button-primary" type="button" onClick={() => navigate("/events")}>Back to my events <span aria-hidden="true">→</span></button>
      </div>
    </div>
  );
}

function MissingPage({ navigate }: { navigate: (path: string) => void }) {
  return (
    <div className="page-wrap">
      <div className="empty-card empty-page">
        <span className="empty-art" aria-hidden="true">?</span>
        <div><h1>Page not found</h1><p>The page you requested does not exist.</p></div>
        <button className="button button-primary" type="button" onClick={() => navigate("/")}>Go to dashboard <span aria-hidden="true">→</span></button>
      </div>
    </div>
  );
}

export default App;
