import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  cancelInvitationReminder,
  createInvitationGuest,
  deleteInvitationGuest,
  generateInvitationDraft,
  getInvitationDuplicates,
  getInvitationOverview,
  prepareInvitationReminders,
  previewInvitationDelivery,
  recordInvitationRsvp,
  retryInvitationDelivery,
  sendInvitationDelivery,
  sendInvitationReminder,
  updateInvitationDraft,
  updateInvitationGuest,
} from "../api";
import type {
  InvitationDeliveryPreview,
  InvitationDuplicateSuggestion,
  InvitationGuest,
  InvitationOverview,
  InvitationTone,
  RSVPStatus,
} from "../types";

interface EventOption {
  id: string;
  name: string;
  eventType: string;
  eventDate: string;
}

interface GuestFormState {
  name: string;
  email: string;
  phone: string;
  group_name: string;
  party_size: string;
  notes: string;
  dietary_requirements: string;
  accessibility_requirements: string;
  accommodation_requirements: string;
}

const emptyGuestForm = (): GuestFormState => ({
  name: "",
  email: "",
  phone: "",
  group_name: "",
  party_size: "1",
  notes: "",
  dietary_requirements: "",
  accessibility_requirements: "",
  accommodation_requirements: "",
});

function splitItems(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "Not supplied";
  const normalized = value.includes("T") ? value : `${value}T00:00:00Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function titleCase(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function makeIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `inv-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function guestFormFrom(guest: InvitationGuest): GuestFormState {
  return {
    name: guest.name,
    email: guest.email ?? "",
    phone: guest.phone ?? "",
    group_name: guest.group_name ?? "",
    party_size: String(guest.party_size),
    notes: guest.notes ?? "",
    dietary_requirements: guest.dietary_requirements.join(", "),
    accessibility_requirements: guest.accessibility_requirements.join(", "),
    accommodation_requirements: guest.accommodation_requirements.join(", "),
  };
}

export default function Invitations({ events, onNavigateToEvent, onNavigate }: {
  events: EventOption[];
  onNavigateToEvent: (eventId: string) => void;
  onNavigate: (path: string) => void;
}) {
  const [eventId, setEventId] = useState("");
  const [overview, setOverview] = useState<InvitationOverview | null>(null);
  const [duplicates, setDuplicates] = useState<InvitationDuplicateSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState("");
  const [search, setSearch] = useState("");
  const [rsvpFilter, setRsvpFilter] = useState<"all" | RSVPStatus>("all");
  const [groupFilter, setGroupFilter] = useState("all");
  const [selectedGuestIds, setSelectedGuestIds] = useState<string[]>([]);
  const [guestForm, setGuestForm] = useState<GuestFormState>(emptyGuestForm);
  const [editingGuestId, setEditingGuestId] = useState<string | null>(null);
  const [showGuestForm, setShowGuestForm] = useState(false);
  const [rsvpEdits, setRsvpEdits] = useState<Record<string, { status: RSVPStatus; partySize: string }>>({});
  const [tone, setTone] = useState<InvitationTone>("friendly");
  const [language, setLanguage] = useState("English");
  const [deadline, setDeadline] = useState("");
  const [groupName, setGroupName] = useState("");
  const [instructions, setInstructions] = useState("");
  const [selectedDraftId, setSelectedDraftId] = useState("");
  const [draftSubject, setDraftSubject] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [preview, setPreview] = useState<InvitationDeliveryPreview | null>(null);
  const [deliveryApproved, setDeliveryApproved] = useState(false);
  const [reminderApproved, setReminderApproved] = useState<Record<string, boolean>>({});
  const [retryApproved, setRetryApproved] = useState<Record<string, boolean>>({});

  const currentEvent = events.find((event) => event.id === eventId);

  async function loadWorkspace(nextEventId = eventId) {
    if (!nextEventId) {
      setOverview(null);
      setDuplicates([]);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [nextOverview, nextDuplicates] = await Promise.all([
        getInvitationOverview(nextEventId),
        getInvitationDuplicates(nextEventId),
      ]);
      setOverview(nextOverview);
      setDuplicates(nextDuplicates);
      setSelectedGuestIds((current) => current.filter((id) => nextOverview.guests.some((guest) => guest.id === id)));
    } catch (reason) {
      setOverview(null);
      setDuplicates([]);
      setError(reason instanceof Error ? reason.message : "Could not load invitations and RSVP records.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!events.length) {
      setEventId("");
      return;
    }
    setEventId((current) => events.some((event) => event.id === current) ? current : events[0].id);
  }, [events]);

  useEffect(() => {
    void loadWorkspace(eventId);
  }, [eventId]);

  useEffect(() => {
    const selected = overview?.drafts.find((draft) => draft.id === selectedDraftId);
    if (selected) {
      setDraftSubject(selected.subject);
      setDraftBody(selected.body);
      return;
    }
    const first = overview?.drafts[0];
    if (first) {
      setSelectedDraftId(first.id);
      setDraftSubject(first.subject);
      setDraftBody(first.body);
    } else {
      setSelectedDraftId("");
      setDraftSubject("");
      setDraftBody("");
    }
  }, [overview, selectedDraftId]);

  const groups = useMemo(() => Array.from(new Set(
    (overview?.guests ?? []).map((guest) => guest.group_name).filter((group): group is string => Boolean(group)),
  )).sort((a, b) => a.localeCompare(b)), [overview]);

  const visibleGuests = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return (overview?.guests ?? []).filter((guest) => {
      const haystack = [guest.name, guest.email, guest.phone, guest.group_name].filter(Boolean).join(" ").toLocaleLowerCase();
      return (!query || haystack.includes(query))
        && (rsvpFilter === "all" || guest.rsvp_status === rsvpFilter)
        && (groupFilter === "all" || guest.group_name === groupFilter);
    });
  }, [groupFilter, overview, rsvpFilter, search]);

  const selectedDraft = overview?.drafts.find((draft) => draft.id === selectedDraftId) ?? null;
  const selectedPendingIds = selectedGuestIds.filter((id) => overview?.summary.pending_guest_ids.includes(id));

  function resetGuestForm() {
    setGuestForm(emptyGuestForm());
    setEditingGuestId(null);
    setShowGuestForm(false);
  }

  function updateGuestForm(field: keyof GuestFormState, value: string) {
    setGuestForm((current) => ({ ...current, [field]: value }));
  }

  async function submitGuest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!eventId) return;
    setBusy("guest");
    setError("");
    setSuccess("");
    const input = {
      name: guestForm.name,
      email: guestForm.email.trim() || null,
      phone: guestForm.phone.trim() || null,
      group_name: guestForm.group_name.trim() || null,
      party_size: Number(guestForm.party_size),
      notes: guestForm.notes.trim() || null,
      dietary_requirements: splitItems(guestForm.dietary_requirements),
      accessibility_requirements: splitItems(guestForm.accessibility_requirements),
      accommodation_requirements: splitItems(guestForm.accommodation_requirements),
    };
    try {
      if (editingGuestId) {
        await updateInvitationGuest(eventId, editingGuestId, input);
        setSuccess("Guest record updated.");
      } else {
        await createInvitationGuest(eventId, input);
        setSuccess("Guest record added.");
      }
      resetGuestForm();
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save the guest record.");
    } finally {
      setBusy("");
    }
  }

  async function removeGuest(guest: InvitationGuest) {
    if (!eventId || !window.confirm(`Remove ${guest.name} from this event?`)) return;
    setBusy(`remove:${guest.id}`);
    setError("");
    try {
      await deleteInvitationGuest(eventId, guest.id);
      setSelectedGuestIds((current) => current.filter((id) => id !== guest.id));
      setSuccess(`${guest.name} was removed.`);
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not remove the guest.");
    } finally {
      setBusy("");
    }
  }

  async function saveRsvp(guest: InvitationGuest) {
    if (!eventId) return;
    const change = rsvpEdits[guest.id] ?? { status: guest.rsvp_status, partySize: String(guest.rsvp_party_size ?? guest.party_size) };
    setBusy(`rsvp:${guest.id}`);
    setError("");
    try {
      await recordInvitationRsvp(eventId, guest.id, {
        rsvp_status: change.status,
        ...(change.status === "attending" ? { party_size: Number(change.partySize) } : {}),
        source: "manual",
      });
      setRsvpEdits((current) => {
        const next = { ...current };
        delete next[guest.id];
        return next;
      });
      setSuccess(`Manual RSVP recorded for ${guest.name}.`);
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not record the RSVP.");
    } finally {
      setBusy("");
    }
  }

  async function resolveDuplicate(suggestion: InvitationDuplicateSuggestion) {
    if (!eventId) return;
    setBusy(`duplicate:${suggestion.guest_id}`);
    setError("");
    try {
      await updateInvitationGuest(eventId, suggestion.guest_id, { duplicate_of_id: suggestion.possible_duplicate_id });
      setSuccess("The duplicate relationship was saved. The duplicate no longer contributes to RSVP counts.");
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not resolve the duplicate suggestion.");
    } finally {
      setBusy("");
    }
  }

  async function generateDraft() {
    if (!eventId) return;
    setBusy("generate-draft");
    setError("");
    setSuccess("");
    try {
      const draft = await generateInvitationDraft(eventId, {
        tone,
        language,
        ...(groupName.trim() ? { group_name: groupName.trim() } : {}),
        ...(deadline ? { rsvp_deadline: deadline } : {}),
        ...(instructions.trim() ? { instructions: instructions.trim() } : {}),
      });
      setSelectedDraftId(draft.id);
      setPreview(null);
      setDeliveryApproved(false);
      setSuccess(draft.generated_by === "genai" ? "Editable AI draft created." : "Editable draft created from saved event facts.");
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not generate the invitation draft.");
    } finally {
      setBusy("");
    }
  }

  async function saveDraft() {
    if (!eventId || !selectedDraft) return;
    setBusy("save-draft");
    setError("");
    try {
      await updateInvitationDraft(eventId, selectedDraft.id, { subject: draftSubject, body: draftBody });
      setPreview(null);
      setDeliveryApproved(false);
      setSuccess("Invitation draft saved. It still requires a recipient review and approval before any external delivery.");
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save the invitation draft.");
    } finally {
      setBusy("");
    }
  }

  function toggleGuest(id: string, selected: boolean) {
    setPreview(null);
    setDeliveryApproved(false);
    setSelectedGuestIds((current) => selected ? Array.from(new Set([...current, id])) : current.filter((item) => item !== id));
  }

  function selectVisibleGuests() {
    setPreview(null);
    setDeliveryApproved(false);
    setSelectedGuestIds(Array.from(new Set(visibleGuests.filter((guest) => !guest.duplicate_of_id).map((guest) => guest.id))));
  }

  function selectPendingGuests() {
    setPreview(null);
    setDeliveryApproved(false);
    setSelectedGuestIds(overview?.summary.pending_guest_ids ?? []);
  }

  async function preparePreview() {
    if (!eventId || !selectedDraft) return;
    if (!selectedGuestIds.length) {
      setError("Select one or more guests before preparing a delivery review.");
      return;
    }
    setBusy("preview");
    setError("");
    try {
      const nextPreview = await previewInvitationDelivery(eventId, {
        draft_id: selectedDraft.id,
        guest_ids: selectedGuestIds,
      });
      setPreview(nextPreview);
      setDeliveryApproved(false);
      setSuccess("Recipient and message review is ready. No external message has been sent.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not prepare the delivery review.");
    } finally {
      setBusy("");
    }
  }

  async function approveDelivery() {
    if (!eventId || !selectedDraft || !preview || !deliveryApproved) return;
    setBusy("send");
    setError("");
    try {
      const result = await sendInvitationDelivery(eventId, {
        draft_id: selectedDraft.id,
        guest_ids: selectedGuestIds,
        approved: true,
        idempotency_key: makeIdempotencyKey(),
      });
      setSuccess(result.notice);
      setPreview(null);
      setDeliveryApproved(false);
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not process the approved delivery request.");
    } finally {
      setBusy("");
    }
  }

  async function copyPreview() {
    if (!preview?.recipients[0]) return;
    const recipient = preview.recipients[0];
    const content = `${recipient.subject ?? ""}\n\n${recipient.body ?? ""}`.trim();
    try {
      await navigator.clipboard.writeText(content);
      setSuccess("The first reviewed message was copied. Draft-only mode does not send it anywhere.");
    } catch {
      setError("The browser could not copy the message. Select it from the preview and copy it manually.");
    }
  }

  async function prepareReminders() {
    if (!eventId) return;
    if (!selectedPendingIds.length) {
      setError("Select one or more guests who are still awaiting an RSVP before preparing reminders.");
      return;
    }
    setBusy("prepare-reminders");
    setError("");
    try {
      const preparation = await prepareInvitationReminders(eventId, {
        guest_ids: selectedPendingIds,
        tone,
        language,
        ...(deadline ? { rsvp_deadline: deadline } : {}),
        ...(instructions.trim() ? { instructions: instructions.trim() } : {}),
      });
      setSuccess(preparation.notice);
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not prepare RSVP reminders.");
    } finally {
      setBusy("");
    }
  }

  async function approveReminder(preparationId: string) {
    if (!eventId || !reminderApproved[preparationId]) return;
    setBusy(`reminder:${preparationId}`);
    setError("");
    try {
      const result = await sendInvitationReminder(eventId, preparationId, {
        approved: true,
        idempotency_key: makeIdempotencyKey(),
      });
      setSuccess(result.notice);
      setReminderApproved((current) => ({ ...current, [preparationId]: false }));
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not process the approved reminder request.");
    } finally {
      setBusy("");
    }
  }

  async function cancelReminder(preparationId: string) {
    if (!eventId) return;
    setBusy(`cancel:${preparationId}`);
    setError("");
    try {
      const result = await cancelInvitationReminder(eventId, preparationId);
      setSuccess(result.notice);
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not cancel the reminder.");
    } finally {
      setBusy("");
    }
  }

  async function retryAttempt(attemptId: string) {
    if (!eventId || !retryApproved[attemptId]) return;
    setBusy(`retry:${attemptId}`);
    setError("");
    try {
      const result = await retryInvitationDelivery(eventId, attemptId, {
        approved: true,
        idempotency_key: makeIdempotencyKey(),
      });
      setSuccess(result.notice);
      setRetryApproved((current) => ({ ...current, [attemptId]: false }));
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not retry the selected delivery.");
    } finally {
      setBusy("");
    }
  }

  if (!events.length) {
    return (
      <div className="page-wrap">
        <section className="empty-card empty-page">
          <span className="empty-art" aria-hidden="true">✉</span>
          <div><h2>Create an event before managing invitations</h2><p>Guest records, drafts, RSVP tracking, and delivery reviews are saved against a specific event plan.</p></div>
          <button className="button button-primary" type="button" onClick={() => onNavigate("/create")}>Create an event</button>
        </section>
      </div>
    );
  }

  return (
    <div className="page-wrap invitations-page">
      <div className="page-intro invitations-intro">
        <div>
          <div className="eyebrow">GUEST COORDINATION</div>
          <h1>Invitations & RSVP</h1>
          <p>Prepare editable drafts, track responses, and review exactly who will receive a message before you approve anything external.</p>
        </div>
        <button className="button button-secondary" type="button" onClick={() => void loadWorkspace()} disabled={loading}>Refresh records</button>
      </div>

      <section className="invitations-event-bar" aria-label="Selected event">
        <label className="field">
          <span>Event</span>
          <select value={eventId} onChange={(event) => { setEventId(event.target.value); setPreview(null); setSuccess(""); }}>
            {events.map((event) => <option key={event.id} value={event.id}>{event.name}</option>)}
          </select>
        </label>
        {currentEvent && <div className="invitations-event-context"><strong>{currentEvent.eventType}</strong><span>{formatDate(currentEvent.eventDate)}</span><button className="text-link" type="button" onClick={() => onNavigateToEvent(currentEvent.id)}>View event</button></div>}
      </section>

      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {success && <div className="alert invitations-success" role="status">{success}</div>}

      {loading && <section className="invitations-loading" aria-live="polite"><span className="loading-orb" aria-hidden="true" /> Loading persisted guest coordination records…</section>}

      {!loading && overview && <>
        <section className="invitations-summary" aria-label="RSVP summary">
          <article><span>Tracked guests</span><strong>{overview.summary.total_guests}</strong><small>Duplicates excluded from counts</small></article>
          <article className="summary-attending"><span>Attending</span><strong>{overview.summary.rsvp_counts.attending}</strong><small>{overview.summary.confirmed_party_size} confirmed places</small></article>
          <article className="summary-pending"><span>Awaiting response</span><strong>{overview.summary.pending_count}</strong><small>{overview.summary.response_rate_percent}% response rate</small></article>
          <article className="summary-declined"><span>Not attending</span><strong>{overview.summary.declined_count}</strong><small>RSVPs are host-recorded</small></article>
        </section>

        <section className="invitations-disclosure">
          <div><strong>{overview.delivery.mode === "smtp" ? "SMTP delivery is configured" : "Draft-only mode"}</strong><p>{overview.delivery.notice}</p></div>
          <div><strong>RSVP coordination</strong><p>{overview.coordination.notice}</p></div>
        </section>

        {duplicates.length > 0 && <section className="invitations-duplicates" aria-label="Likely duplicate guests">
          <div><span className="eyebrow">REVIEW NEEDED</span><h2>Likely duplicate guest records</h2><p>Resolve these before delivery so a person is not contacted twice.</p></div>
          <div className="duplicate-list">
            {duplicates.map((suggestion) => {
              const duplicate = overview.guests.find((guest) => guest.id === suggestion.guest_id);
              const original = overview.guests.find((guest) => guest.id === suggestion.possible_duplicate_id);
              return <div key={suggestion.guest_id} className="duplicate-row"><span><strong>{duplicate?.name ?? "Guest"}</strong> may duplicate <strong>{original?.name ?? "another guest"}</strong> · {suggestion.match_reasons.map(titleCase).join(", ")}</span><button className="button button-small" type="button" disabled={busy === `duplicate:${suggestion.guest_id}`} onClick={() => void resolveDuplicate(suggestion)}>Mark duplicate</button></div>;
            })}
          </div>
        </section>}

        <div className="invitations-layout">
          <section className="invitations-panel invitations-guests-panel">
            <div className="invitations-panel-heading">
              <div><span className="eyebrow">GUEST LIST</span><h2>Guests and manual RSVPs</h2><p>Store only the contact and access details needed to coordinate this event.</p></div>
              <button className="button button-primary" type="button" onClick={() => { setShowGuestForm((open) => !open); setEditingGuestId(null); setGuestForm(emptyGuestForm()); }}>{showGuestForm ? "Close form" : "Add guest"}</button>
            </div>

            {showGuestForm && <form className="invitation-guest-form" onSubmit={submitGuest}>
              <div className="invitation-form-title"><strong>{editingGuestId ? "Edit guest" : "Add guest"}</strong><button className="text-link" type="button" onClick={resetGuestForm}>Cancel</button></div>
              <label><span>Name <i>*</i></span><input required value={guestForm.name} onChange={(event) => updateGuestForm("name", event.target.value)} maxLength={160} /></label>
              <label><span>Email</span><input type="email" value={guestForm.email} onChange={(event) => updateGuestForm("email", event.target.value)} maxLength={320} /></label>
              <label><span>Phone</span><input type="tel" value={guestForm.phone} onChange={(event) => updateGuestForm("phone", event.target.value)} maxLength={32} /></label>
              <label><span>Group</span><input value={guestForm.group_name} onChange={(event) => updateGuestForm("group_name", event.target.value)} maxLength={80} placeholder="Family, friends, colleagues…" /></label>
              <label><span>Invited party size <i>*</i></span><input required type="number" min="1" max="100" value={guestForm.party_size} onChange={(event) => updateGuestForm("party_size", event.target.value)} /></label>
              <label className="invitation-wide"><span>Dietary requirements</span><input value={guestForm.dietary_requirements} onChange={(event) => updateGuestForm("dietary_requirements", event.target.value)} placeholder="Comma-separated, if supplied" /></label>
              <label className="invitation-wide"><span>Accessibility requirements</span><input value={guestForm.accessibility_requirements} onChange={(event) => updateGuestForm("accessibility_requirements", event.target.value)} placeholder="Comma-separated, if supplied" /></label>
              <label className="invitation-wide"><span>Accommodation requirements</span><input value={guestForm.accommodation_requirements} onChange={(event) => updateGuestForm("accommodation_requirements", event.target.value)} placeholder="Comma-separated, if supplied" /></label>
              <label className="invitation-wide"><span>Private host notes</span><textarea value={guestForm.notes} onChange={(event) => updateGuestForm("notes", event.target.value)} maxLength={2000} /></label>
              <div className="invitation-wide invitation-form-actions"><button className="button button-primary" disabled={busy === "guest"} type="submit">{busy === "guest" ? "Saving…" : editingGuestId ? "Save guest" : "Add guest"}</button></div>
            </form>}

            <div className="invitation-filters">
              <label><span className="visually-hidden">Search guests</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, email, phone" /></label>
              <label><span className="visually-hidden">Filter RSVP status</span><select value={rsvpFilter} onChange={(event) => setRsvpFilter(event.target.value as "all" | RSVPStatus)}><option value="all">All RSVP statuses</option><option value="awaiting_response">Awaiting response</option><option value="attending">Attending</option><option value="not_attending">Not attending</option></select></label>
              <label><span className="visually-hidden">Filter guest group</span><select value={groupFilter} onChange={(event) => setGroupFilter(event.target.value)}><option value="all">All groups</option>{groups.map((group) => <option key={group} value={group}>{group}</option>)}</select></label>
            </div>
            <div className="invitation-selection-actions"><button className="text-link" type="button" onClick={selectVisibleGuests}>Select visible</button><button className="text-link" type="button" onClick={selectPendingGuests}>Select pending responses</button><span>{selectedGuestIds.length} selected</span></div>

            {visibleGuests.length ? <div className="invitation-guest-list">
              {visibleGuests.map((guest) => {
                const edit = rsvpEdits[guest.id] ?? { status: guest.rsvp_status, partySize: String(guest.rsvp_party_size ?? guest.party_size) };
                const checked = selectedGuestIds.includes(guest.id);
                return <article key={guest.id} className={`invitation-guest${guest.duplicate_of_id ? " guest-duplicate" : ""}`}>
                  <label className="guest-select"><input type="checkbox" checked={checked} disabled={Boolean(guest.duplicate_of_id)} onChange={(event) => toggleGuest(guest.id, event.target.checked)} /><span className="visually-hidden">Select {guest.name}</span></label>
                  <div className="guest-main"><div className="guest-name-row"><strong>{guest.name}</strong>{guest.group_name && <span>{guest.group_name}</span>}{guest.duplicate_of_id && <em>Duplicate</em>}</div><p>{guest.email || guest.phone || "No contact detail supplied"}</p><div className="guest-meta"><span>{guest.party_size} invited</span>{guest.dietary_requirements.length > 0 && <span>Dietary details</span>}{guest.accessibility_requirements.length > 0 && <span>Accessibility details</span>}{guest.accommodation_requirements.length > 0 && <span>Accommodation details</span>}</div></div>
                  <div className="guest-statuses"><span className={`guest-status invitation-${guest.invitation_status}`}>{titleCase(guest.invitation_status)}</span><span className={`guest-status rsvp-${guest.rsvp_status}`}>{titleCase(guest.rsvp_status)}</span></div>
                  <div className="guest-rsvp-editor"><select aria-label={`RSVP for ${guest.name}`} value={edit.status} disabled={Boolean(guest.duplicate_of_id)} onChange={(event) => setRsvpEdits((current) => ({ ...current, [guest.id]: { ...edit, status: event.target.value as RSVPStatus } }))}><option value="awaiting_response">Awaiting response</option><option value="attending">Attending</option><option value="not_attending">Not attending</option></select>{edit.status === "attending" && <input aria-label={`Confirmed party size for ${guest.name}`} type="number" min="1" max={guest.party_size} value={edit.partySize} onChange={(event) => setRsvpEdits((current) => ({ ...current, [guest.id]: { ...edit, partySize: event.target.value } }))} />}</div>
                  <div className="guest-actions"><button className="button button-small" type="button" disabled={Boolean(guest.duplicate_of_id) || busy === `rsvp:${guest.id}`} onClick={() => void saveRsvp(guest)}>{busy === `rsvp:${guest.id}` ? "Saving…" : "Save RSVP"}</button><button className="text-link" type="button" onClick={() => { setEditingGuestId(guest.id); setGuestForm(guestFormFrom(guest)); setShowGuestForm(true); }}>Edit</button><button className="text-link text-link-danger" type="button" disabled={busy === `remove:${guest.id}`} onClick={() => void removeGuest(guest)}>Remove</button></div>
                </article>;
              })}
            </div> : <div className="invitation-empty"><strong>No matching guests</strong><p>Add a guest or adjust the filters. Planova does not invent guest records.</p></div>}
          </section>

          <aside className="invitations-side-stack">
            <section className="invitations-panel invitation-draft-panel">
              <div className="invitations-panel-heading"><div><span className="eyebrow">EDITABLE DRAFTS</span><h2>Invitation studio</h2><p>Missing event information stays visible instead of being invented.</p></div></div>
              
<div className={`ai-draft-status ${selectedDraft?.generated_by === "genai" ? "ai-draft-status-live" : "ai-draft-status-fallback"}`}>
  <div className="ai-draft-status-icon" aria-hidden="true">
    {selectedDraft?.generated_by === "genai" ? "✦" : "✓"}
  </div>
  <div className="ai-draft-status-content">
    <strong>
      {selectedDraft?.generated_by === "genai"
        ? "AI-generated draft"
        : selectedDraft?.generated_by === "deterministic"
          ? "Event-facts draft"
          : selectedDraft
            ? "Manually editable draft"
            : "Ready to create your invitation"}
    </strong>
    <p>
      {selectedDraft?.generated_by === "genai"
        ? "AI helped write this invitation. Review names, dates, venue and other details before use."
        : selectedDraft?.generated_by === "deterministic"
          ? "This draft uses saved event facts and predefined generation logic, not a live AI response."
          : selectedDraft
            ? "Review and edit the saved invitation before preparing a recipient preview."
            : "Choose a tone and language, then generate a draft using your event information."}
    </p>
    <span className="ai-draft-status-note">
      Draft generation never sends an email.
    </span>
  </div>
</div>

              <div className="invitation-draft-options"><label><span>Tone</span><select value={tone} onChange={(event) => setTone(event.target.value as InvitationTone)}><option value="friendly">Friendly</option><option value="formal">Formal</option><option value="celebratory">Celebratory</option><option value="professional">Professional</option></select></label><label><span>Language</span><input value={language} onChange={(event) => setLanguage(event.target.value)} maxLength={64} /></label><label><span>RSVP deadline</span><input type="date" value={deadline} onChange={(event) => setDeadline(event.target.value)} /></label><label><span>Guest group</span><input value={groupName} onChange={(event) => setGroupName(event.target.value)} placeholder="Optional" /></label><label className="draft-instructions"><span>Relevant instructions</span><textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} maxLength={1000} placeholder="Optional instructions for this editable draft" /></label></div>
              <button className="button button-primary" type="button" disabled={busy === "generate-draft"} onClick={() => void generateDraft()}>{busy === "generate-draft" ? "Generating…" : "Generate editable draft"}</button>
              {overview.drafts.length > 0 && <div className="saved-drafts"><label><span>Saved draft</span><select value={selectedDraftId} onChange={(event) => { setSelectedDraftId(event.target.value); setPreview(null); setDeliveryApproved(false); }}>{overview.drafts.map((draft) => <option key={draft.id} value={draft.id}>{draft.kind === "reminder" ? "Reminder" : "Invitation"} · {draft.subject}</option>)}</select></label>{selectedDraft && <><label><span>Subject</span><input value={draftSubject} onChange={(event) => setDraftSubject(event.target.value)} maxLength={200} /></label><label><span>Message</span><textarea value={draftBody} onChange={(event) => setDraftBody(event.target.value)} maxLength={6000} /></label>{selectedDraft.missing_information.length > 0 && <div className="draft-missing"><strong>Needs confirmation</strong><ul>{selectedDraft.missing_information.map((item) => <li key={item}>{item}</li>)}</ul></div>}<div className="draft-footer"><small>{selectedDraft.generated_by === "genai" ? "AI-generated; edit before use." : selectedDraft.generated_by === "deterministic" ? "Generated from saved facts; edit before use." : "Manual draft."}</small><button className="button button-small" type="button" disabled={busy === "save-draft"} onClick={() => void saveDraft()}>{busy === "save-draft" ? "Saving…" : "Save changes"}</button></div></>}</div>}
            </section>

            <section className="invitations-panel invitation-delivery-panel">
              <div className="invitations-panel-heading"><div><span className="eyebrow">RECIPIENT REVIEW</span><h2>Preview before approval</h2><p>{selectedGuestIds.length} selected recipient{selectedGuestIds.length === 1 ? "" : "s"}.</p></div></div>
              <button className="button button-secondary" type="button" disabled={!selectedDraft || busy === "preview"} onClick={() => void preparePreview()}>{busy === "preview" ? "Preparing…" : "Preview selected recipients"}</button>
              {preview && <div className="delivery-preview"><p className="preview-notice">{preview.notice}</p><div className="preview-recipient-list">{preview.recipients.map((recipient) => <article key={recipient.guest_id} className={!recipient.eligible ? "preview-recipient-ineligible" : ""}><div><strong>{recipient.guest_name}</strong><span>{recipient.email || "No email supplied"}</span></div>{recipient.eligible ? <span className="preview-eligible">Ready for review</span> : <span className="preview-ineligible">{recipient.reason}</span>}</article>)}</div>{preview.recipients[0] && <details className="preview-message"><summary>View exact first message</summary><strong>{preview.recipients[0].subject}</strong><pre>{preview.recipients[0].body}</pre></details>}{preview.delivery_mode === "draft_only" && <button className="button button-small" type="button" onClick={() => void copyPreview()}>Copy first reviewed message</button>}<label className="approval-check"><input type="checkbox" checked={deliveryApproved} onChange={(event) => setDeliveryApproved(event.target.checked)} /> I reviewed this draft and the selected recipients. I approve this delivery request.</label><button className="button button-primary" type="button" disabled={!deliveryApproved || busy === "send" || preview.recipients.some((recipient) => !recipient.eligible)} onClick={() => void approveDelivery()}>{busy === "send" ? "Processing…" : preview.delivery_mode === "smtp" ? "Approve and request email delivery" : "Record draft-only review"}</button></div>}
            </section>
          </aside>
        </div>

        <section className="invitations-panel invitations-reminders">
          <div className="invitations-panel-heading"><div><span className="eyebrow">FOLLOW-UPS</span><h2>Pending-response reminders</h2><p>Only guests still awaiting a response can be selected. Each reminder needs a fresh approval.</p></div><button className="button button-secondary" type="button" disabled={busy === "prepare-reminders" || selectedPendingIds.length === 0} onClick={() => void prepareReminders()}>{busy === "prepare-reminders" ? "Preparing…" : `Prepare reminder for ${selectedPendingIds.length || "selected"}`}</button></div>
          {overview.summary.pending_count === 0 ? <div className="invitation-empty"><strong>No pending responses</strong><p>Every non-duplicate tracked guest has an RSVP status.</p></div> : <div className="pending-guest-list">{overview.guests.filter((guest) => overview.summary.pending_guest_ids.includes(guest.id)).map((guest) => <span key={guest.id}>{guest.name}{guest.group_name ? ` · ${guest.group_name}` : ""}</span>)}</div>}
          {overview.reminder_preparations.length > 0 && <div className="reminder-list">{overview.reminder_preparations.map((preparation) => <article key={preparation.id} className="reminder-card"><div><span className={`guest-status reminder-${preparation.status}`}>{titleCase(preparation.status)}</span><strong>{preparation.guest_ids.length} selected pending recipient{preparation.guest_ids.length === 1 ? "" : "s"}</strong><small>Prepared {formatTimestamp(preparation.created_at)}</small><p>{preparation.notice}</p></div>{preparation.status === "prepared" && <div className="reminder-actions"><details><summary>Review reminder</summary><strong>{preparation.draft.subject}</strong><pre>{preparation.draft.body}</pre></details><label className="approval-check"><input type="checkbox" checked={Boolean(reminderApproved[preparation.id])} onChange={(event) => setReminderApproved((current) => ({ ...current, [preparation.id]: event.target.checked }))} /> I approve this selected reminder request.</label><div><button className="button button-primary button-small" type="button" disabled={!reminderApproved[preparation.id] || busy === `reminder:${preparation.id}`} onClick={() => void approveReminder(preparation.id)}>{busy === `reminder:${preparation.id}` ? "Processing…" : overview.delivery.mode === "smtp" ? "Approve reminder" : "Record draft-only review"}</button><button className="button button-secondary button-small" type="button" disabled={busy === `cancel:${preparation.id}`} onClick={() => void cancelReminder(preparation.id)}>Cancel</button></div></div>}</article>)}</div>}
        </section>

        <div className="invitations-bottom-grid">
          <section className="invitations-panel">
            <div className="invitations-panel-heading"><div><span className="eyebrow">DELIVERY EVIDENCE</span><h2>Status and failures</h2><p>Sent means SMTP accepted a message. Delivered appears only when a provider supplies evidence.</p></div></div>
            {overview.delivery_attempts.length ? <div className="delivery-attempt-list">{overview.delivery_attempts.map((attempt) => <article key={attempt.id} className={`delivery-attempt attempt-${attempt.status}`}><div><span className={`guest-status attempt-status-${attempt.status}`}>{titleCase(attempt.status)}</span><strong>{attempt.recipient_address}</strong><small>{formatTimestamp(attempt.updated_at)}</small>{attempt.error_message && <p className="attempt-error">{attempt.error_message}</p>}{attempt.provider_message_id && <p>Provider message ID: {attempt.provider_message_id}</p>}{attempt.transport_message_id && <p>Transport message ID: {attempt.transport_message_id}</p>}</div>{(attempt.status === "failed" || attempt.status === "unknown") && <div className="retry-controls"><label className="approval-check"><input type="checkbox" checked={Boolean(retryApproved[attempt.id])} onChange={(event) => setRetryApproved((current) => ({ ...current, [attempt.id]: event.target.checked }))} /> I approve retrying this individual recipient.</label><button className="button button-small" type="button" disabled={!retryApproved[attempt.id] || busy === `retry:${attempt.id}`} onClick={() => void retryAttempt(attempt.id)}>{busy === `retry:${attempt.id}` ? "Retrying…" : "Retry"}</button></div>}</article>)}</div> : <div className="invitation-empty"><strong>No external delivery attempts</strong><p>Draft-only reviews do not create a sent or delivered status.</p></div>}
          </section>

          <section className="invitations-panel invitation-activity-panel">
            <div className="invitations-panel-heading"><div><span className="eyebrow">RSVP HISTORY</span><h2>Recent changes</h2><p>Changes are recorded with their source; message bodies are not logged here.</p></div></div>
            {overview.rsvp_activity.length ? <ol className="rsvp-activity-list">{overview.rsvp_activity.slice(0, 8).map((activity) => { const guest = overview.guests.find((item) => item.id === activity.guest_id); return <li key={activity.id}><span>{formatTimestamp(activity.created_at)}</span><strong>{titleCase(activity.action)}</strong><p>{guest?.name ?? "Guest record"} · {activity.source}</p></li>; })}</ol> : <div className="invitation-empty"><strong>No RSVP activity yet</strong><p>Add guests or record a manual response to create the first history entry.</p></div>}
          </section>
        </div>
      </>}
    </div>
  );
}
