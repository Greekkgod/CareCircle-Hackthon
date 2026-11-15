/**
 * CareCircle Frontend Application
 * Vanilla JS, Accessible, Role-Driven, Speech Synthesis, PWA Service Worker.
 */

const CareApp = (() => {
  // Application State
  const state = {
    role: "elder",
    token: null,
    user: null,
    medications: [],
    appointments: [],
    drafts: [],
    targetRoleToAuth: null,
  };

  // Demo passcodes mapping for quick demo convenience
  const DEMO_CREDENTIALS = {
    elder: { id: "elder_1", code: "1234" },
    caretaker: { id: "caretaker_1", code: "care2026" },
    family: { id: "family_1", code: "fam1234" },
  };

  /**
   * Show an accessible banner message and announce via ARIA live region.
   */
  function announce(message, type = "info") {
    const liveRegion = document.getElementById("aria-status");
    if (liveRegion) {
      liveRegion.textContent = message;
    }

    const banner = document.getElementById("status-banner");
    if (banner) {
      banner.textContent = message;
      banner.className = `status-banner show ${type}`;
      setTimeout(() => {
        banner.className = "status-banner";
      }, 5000);
    }
  }

  /**
   * Helper for authenticated API calls.
   */
  async function apiFetch(endpoint, options = {}) {
    const headers = options.headers || {};
    if (state.token) {
      headers["Authorization"] = `Bearer ${state.token}`;
    }
    if (options.body && !(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }

    const response = await fetch(endpoint, { ...options, headers });
    if (response.status === 401) {
      announce("Passcode required to continue.", "alert");
      openAuthDialog(state.role);
      throw new Error("Unauthorized");
    }
    if (response.status === 429) {
      const err = await response.json();
      announce(err.detail || "Rate limit reached. Please wait before trying again.", "alert");
      throw new Error("Rate limited");
    }
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(err.detail || "Request failed");
    }
    return response.json();
  }

  /**
   * Authenticate with passcode.
   */
  async function login(identifier, passcode) {
    const data = await apiFetch("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, passcode }),
    });
    state.token = data.access_token;
    state.user = data;
    return data;
  }

  /**
   * Open the passcode modal.
   */
  function openAuthDialog(role) {
    state.targetRoleToAuth = role;
    const dialog = document.getElementById("auth-dialog");
    const title = document.getElementById("auth-dialog-title");
    const desc = document.getElementById("auth-dialog-desc");
    const codeInput = document.getElementById("dialog-passcode-input");
    const rateMsg = document.getElementById("dialog-rate-limit-msg");

    if (rateMsg) rateMsg.style.display = "none";
    if (codeInput) codeInput.value = DEMO_CREDENTIALS[role] ? DEMO_CREDENTIALS[role].code : "";

    title.textContent = `Unlock ${role.toUpperCase()} View`;
    desc.textContent = `Demo passcode: "${DEMO_CREDENTIALS[role]?.code}". Enter passcode to switch roles.`;
    dialog.showModal();
  }

  /**
   * Handle submission from passcode dialog.
   */
  async function submitPasscode(event) {
    event.preventDefault();
    const codeInput = document.getElementById("dialog-passcode-input");
    const rateMsg = document.getElementById("dialog-rate-limit-msg");
    const role = state.targetRoleToAuth || "elder";
    const cred = DEMO_CREDENTIALS[role];

    try {
      await login(cred.id, codeInput.value.trim());
      document.getElementById("auth-dialog").close();
      setRoleView(role);
      announce(`Switched to ${role.toUpperCase()} view.`, "success");
      loadDataForCurrentRole();
    } catch (err) {
      if (rateMsg) {
        rateMsg.textContent = err.message || "Invalid passcode.";
        rateMsg.style.display = "block";
      }
    }
  }

  /**
   * Switch between Elder, Caretaker, and Family roles.
   */
  async function switchRole(newRole) {
    if (state.role === newRole && state.token) return;
    openAuthDialog(newRole);
  }

  /**
   * Update UI tab states and display appropriate role section.
   */
  function setRoleView(role) {
    state.role = role;
    ["elder", "caretaker", "family"].forEach((r) => {
      const btn = document.getElementById(`${r}-tab`);
      const sec = document.getElementById(`${r}-view`);
      const isActive = r === role;
      if (btn) {
        btn.setAttribute("aria-pressed", isActive ? "true" : "false");
        btn.classList.toggle("active", isActive);
      }
      if (sec) {
        sec.style.display = isActive ? "flex" : "none";
      }
    });
  }

  /**
   * Load data according to current role.
   */
  async function loadDataForCurrentRole() {
    try {
      if (state.role === "elder") {
        await loadElderMeds();
        await loadElderAppts();
      } else if (state.role === "caretaker") {
        await loadCaretakerData();
      } else if (state.role === "family") {
        await loadFamilyData();
      }
    } catch (e) {
      console.error("Error loading role data", e);
    }
  }

  /**
   * Fetch and render medications for elder.
   */
  async function loadElderMeds() {
    const meds = await apiFetch("/api/medications/");
    state.medications = meds;
    const container = document.getElementById("elder-meds-container");
    if (!container) return;

    if (meds.length === 0) {
      container.innerHTML = `<p style="font-size: 22px; color: var(--text-secondary);">No medications scheduled at this time.</p>`;
      return;
    }

    container.innerHTML = meds.map((m) => `
      <article class="med-card" style="border-left-color: ${m.pill_color || '#3B82F6'};" aria-labelledby="med-${m.id}-title">
        <div class="med-header">
          <h3 id="med-${m.id}-title" class="med-name">${escapeHtml(m.name)}</h3>
          <span class="pill-badge" style="background-color: ${m.pill_color || '#3B82F6'};" aria-hidden="true"></span>
        </div>
        <div class="med-dosage">Dose: ${escapeHtml(m.dosage)}</div>
        <div class="med-instructions"><strong>Instructions:</strong> ${escapeHtml(m.instructions)}</div>
        <div class="med-schedule">⏰ Scheduled: ${escapeHtml(m.schedule_times.join(", "))} (${escapeHtml(m.frequency)})</div>
        <div style="font-size: 18px; color: ${m.remaining_refills <= m.refill_threshold ? '#F87171' : 'var(--text-muted)'};">
          Remaining Pills: ${m.remaining_refills} ${m.remaining_refills <= m.refill_threshold ? '⚠️ Refill Soon!' : ''}
        </div>
        <button class="btn-take-pill" onclick="CareApp.takePill('${m.id}', '${escapeHtml(m.name)}')" aria-label="Confirm I took ${escapeHtml(m.name)} ${escapeHtml(m.dosage)}">
          ✅ I TOOK MY PILL
        </button>
      </article>
    `).join("");
  }

  /**
   * Fetch and render appointments for elder.
   */
  async function loadElderAppts() {
    const appts = await apiFetch("/api/appointments/");
    state.appointments = appts;
    const container = document.getElementById("elder-appts-container");
    if (!container) return;

    if (appts.length === 0) {
      container.innerHTML = `<p style="font-size: 22px; color: var(--text-secondary);">No doctor appointments scheduled.</p>`;
      return;
    }

    container.innerHTML = appts.map((a) => `
      <article class="med-card" style="border-left-color: #A855F7;">
        <h3 class="med-name">${escapeHtml(a.title)}</h3>
        <div class="med-dosage">Doctor: ${escapeHtml(a.doctor_name)}</div>
        <div class="med-instructions">📍 ${escapeHtml(a.location)}</div>
        <div class="med-schedule">📅 ${escapeHtml(a.scheduled_time)}</div>
        ${a.transport_needed ? '<div style="color: #60A5FA; font-weight: bold;">🚗 Transport Requested</div>' : ''}
      </article>
    `).join("");
  }

  /**
   * Audio readout of daily schedule using Web Speech API.
   */
  function readScheduleAloud() {
    if (!("speechSynthesis" in window)) {
      announce("Audio readout is not supported in this browser.", "alert");
      return;
    }

    if (state.medications.length === 0) {
      const emptyUtterance = new SpeechSynthesisUtterance("You have no medications scheduled right now. Have a lovely day!");
      window.speechSynthesis.speak(emptyUtterance);
      return;
    }

    let speechText = `Hello Rose. Here is your medication schedule. `;
    state.medications.forEach((m, idx) => {
      speechText += `Medication ${idx + 1}: ${m.name}, ${m.dosage}. ${m.instructions}. Scheduled for ${m.schedule_times.join(" and ")}. `;
    });

    if (state.appointments.length > 0) {
      speechText += `You also have an appointment: ${state.appointments[0].title} with ${state.appointments[0].doctor_name} at ${state.appointments[0].scheduled_time}.`;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(speechText);
    utterance.rate = 0.9; // Slightly slower, clear cadence for elderly listeners
    utterance.pitch = 1.0;
    window.speechSynthesis.speak(utterance);
    announce("Reading your medication schedule aloud.", "info");
  }

  /**
   * Record pill taken.
   */
  async function takePill(medId, medName) {
    try {
      await apiFetch("/api/medications/log", {
        method: "POST",
        body: JSON.stringify({
          medication_id: medId,
          medication_name: medName,
          scheduled_time: "Now",
          status: "TAKEN",
        }),
      });
      announce(`Great job! You logged ${medName} as taken.`, "success");
      if ("speechSynthesis" in window) {
        const u = new SpeechSynthesisUtterance(`Thank you Rose! Logged ${medName} as taken.`);
        window.speechSynthesis.speak(u);
      }
      await loadElderMeds();
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Record mood check-in.
   */
  async function submitCheckin(mood) {
    try {
      await apiFetch("/api/checkins/", {
        method: "POST",
        body: JSON.stringify({ mood, note: `Elder pressed ${mood}` }),
      });
      const labels = {
        GREAT: "Wonderful! We let your family know you feel great!",
        OKAY: "Thank you for checking in. We are always here for you.",
        NEED_HELP: "Check-in received. Your caregiver has been notified.",
      };
      announce(labels[mood] || "Check-in recorded.", "success");
      if ("speechSynthesis" in window) {
        const u = new SpeechSynthesisUtterance(labels[mood]);
        window.speechSynthesis.speak(u);
      }
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Emergency SOS trigger.
   */
  async function triggerSOS() {
    try {
      await apiFetch("/api/checkins/sos", {
        method: "POST",
        body: JSON.stringify({ note: "URGENT SOS triggered from Elder screen!" }),
      });
      announce("EMERGENCY ALERT SENT! Help is on the way. Caretaker and family notified.", "alert");
      if ("speechSynthesis" in window) {
        const u = new SpeechSynthesisUtterance("Emergency alert sent. Help has been notified. Please stay calm.");
        window.speechSynthesis.speak(u);
      }
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Load Caretaker console data.
   */
  async function loadCaretakerData() {
    // Adherence Stats
    const stats = await apiFetch("/api/medications/adherence");
    document.getElementById("caretaker-adherence-stat").textContent = `${stats.adherence_percentage}%`;
    document.getElementById("caretaker-logged-stat").textContent = stats.total_logged;
    document.getElementById("caretaker-refills-stat").textContent = stats.needs_refill_count;

    // Active Emergencies
    const emergencies = await apiFetch("/api/checkins/emergencies?only_active=true");
    const emBox = document.getElementById("caretaker-emergencies-box");
    const emList = document.getElementById("caretaker-emergencies-list");
    if (emergencies.length > 0) {
      emBox.style.display = "block";
      emList.innerHTML = emergencies.map((e) => `
        <div style="background: #7F1D1D; padding: 16px; border-radius: 8px; margin-top: 8px; display: flex; justify-content: space-between; align-items: center;">
          <div>
            <strong>${escapeHtml(e.elder_name)}:</strong> ${escapeHtml(e.note)} (${new Date(e.created_at).toLocaleTimeString()})
          </div>
          <button class="btn-primary" onclick="CareApp.resolveSOS('${e.id}')" style="min-height: 48px; font-size: 18px;">
            Mark Resolved
          </button>
        </div>
      `).join("");
    } else {
      emBox.style.display = "none";
    }

    // Load AI Drafts
    await loadAIDrafts();
  }

  /**
   * AI Prescription / Note extraction handler.
   */
  async function handleAIExtract(event) {
    event.preventDefault();
    const btn = document.getElementById("btn-parse-ai");
    const textarea = document.getElementById("ai-raw-text");
    btn.disabled = true;
    btn.textContent = "Scanning & Redacting PII...";

    try {
      announce("Redacting personal identifiers and parsing clinical notes...", "info");
      const drafts = await apiFetch("/api/ai/parse-draft", {
        method: "POST",
        body: JSON.stringify({ raw_text: textarea.value }),
      });
      announce(`Generated ${drafts.length} AI draft(s). Please review and confirm below.`, "success");
      await loadAIDrafts();
    } catch (err) {
      announce(err.message, "alert");
    } finally {
      btn.disabled = false;
      btn.textContent = "✨ Scan & Generate Drafts";
    }
  }

  /**
   * Load and render AI Drafts awaiting human confirmation.
   */
  async function loadAIDrafts() {
    const drafts = await apiFetch("/api/ai/drafts?status_filter=PENDING_CONFIRMATION");
    state.drafts = drafts;
    const container = document.getElementById("ai-drafts-list");
    if (!container) return;

    if (drafts.length === 0) {
      container.innerHTML = `<p style="font-size: 20px; color: var(--text-muted); margin-top: 12px;">No drafts pending confirmation.</p>`;
      return;
    }

    container.innerHTML = `
      <h3 style="font-size: 24px; color: #E9D5FF; margin-top: 16px;">
        Pending Drafts (${drafts.length}) - Human Confirmation Required:
      </h3>
      ${drafts.map((d) => `
        <article class="draft-item" id="draft-${d.id}">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span class="draft-badge">${d.draft_type} PROPOSAL</span>
            <span style="font-size: 16px; color: #C4B5FD;">Status: ⚠️ PENDING CONFIRMATION</span>
          </div>

          <div style="margin-top: 12px; font-size: 20px;">
            ${d.draft_type === "MEDICATION" ? `
              <div><strong>Proposed Medication:</strong> ${escapeHtml(d.proposed_data.name)} (${escapeHtml(d.proposed_data.dosage)})</div>
              <div><strong>Instructions:</strong> ${escapeHtml(d.proposed_data.instructions || "")}</div>
              <div><strong>Times:</strong> ${escapeHtml((d.proposed_data.schedule_times || []).join(", "))}</div>
            ` : `
              <div><strong>Proposed Appointment:</strong> ${escapeHtml(d.proposed_data.title)}</div>
              <div><strong>Doctor:</strong> ${escapeHtml(d.proposed_data.doctor_name)}</div>
              <div><strong>Location:</strong> ${escapeHtml(d.proposed_data.location)}</div>
              <div><strong>Time:</strong> ${escapeHtml(d.proposed_data.scheduled_time)}</div>
            `}
          </div>

          <div style="font-size: 16px; color: var(--text-muted); margin-top: 8px;">
            <em>AI Reasoning: ${escapeHtml(d.reasoning)}</em>
          </div>

          <div class="draft-actions">
            <button class="btn-confirm-draft" onclick="CareApp.confirmDraft('${d.id}', true)">
              ✅ Confirm &amp; Save
            </button>
            <button class="btn-reject-draft" onclick="CareApp.confirmDraft('${d.id}', false)">
              ❌ Reject Draft
            </button>
          </div>
        </article>
      `).join("")}
    `;
  }

  /**
   * Human decision to confirm or reject an AI draft.
   */
  async function confirmDraft(draftId, approved) {
    try {
      const res = await apiFetch(`/api/ai/drafts/${draftId}/confirm`, {
        method: "POST",
        body: JSON.stringify({ approved, modifications: null }),
      });
      announce(`Draft successfully ${approved ? "approved and saved" : "rejected"}.`, "success");
      await loadCaretakerData();
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Manual medication addition handler.
   */
  async function handleManualMed(event) {
    event.preventDefault();
    const name = document.getElementById("med-name-input").value.trim();
    const dosage = document.getElementById("med-dosage-input").value.trim();
    const instructions = document.getElementById("med-instructions-input").value.trim();
    const timeVal = document.getElementById("med-time-input").value.trim();
    const refills = parseInt(document.getElementById("med-refills-input").value, 10);

    try {
      await apiFetch("/api/medications/", {
        method: "POST",
        body: JSON.stringify({
          name,
          dosage,
          instructions,
          schedule_times: [timeVal],
          frequency: "Daily",
          remaining_refills: refills,
        }),
      });
      announce(`Medication "${name}" saved successfully.`, "success");
      event.target.reset();
      await loadCaretakerData();
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Manual appointment addition handler.
   */
  async function handleManualAppt(event) {
    event.preventDefault();
    const title = document.getElementById("appt-title-input").value.trim();
    const doctor_name = document.getElementById("appt-doctor-input").value.trim();
    const location = document.getElementById("appt-loc-input").value.trim();
    const scheduled_time = document.getElementById("appt-time-input").value.trim();

    try {
      await apiFetch("/api/appointments/", {
        method: "POST",
        body: JSON.stringify({ title, doctor_name, location, scheduled_time }),
      });
      announce(`Appointment with ${doctor_name} scheduled.`, "success");
      event.target.reset();
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Resolve an emergency alert.
   */
  async function resolveSOS(alertId) {
    try {
      await apiFetch(`/api/checkins/emergencies/${alertId}/resolve`, { method: "POST" });
      announce("Emergency alert resolved.", "success");
      await loadCaretakerData();
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Load Family reassurance view.
   */
  async function loadFamilyData() {
    const adherence = await apiFetch("/api/medications/adherence");
    document.getElementById("family-adherence-rate").textContent = `${adherence.adherence_percentage}%`;

    const checkins = await apiFetch("/api/checkins/?limit=1");
    if (checkins.length > 0) {
      const moodEmojis = { GREAT: "😊 Great", OKAY: "😐 Okay", NEED_HELP: "🙋 Needs Check-In" };
      document.getElementById("family-latest-mood").textContent = moodEmojis[checkins[0].mood] || checkins[0].mood;
    }

    const emergencies = await apiFetch("/api/checkins/emergencies?only_active=true");
    const emStatus = document.getElementById("family-emergency-status");
    if (emergencies.length > 0) {
      emStatus.textContent = "🚨 ALERT!";
      emStatus.style.color = "#EF4444";
    } else {
      emStatus.textContent = "🟢 Safe";
      emStatus.style.color = "#10B981";
    }

    const logs = await apiFetch("/api/medications/logs?limit=5");
    const container = document.getElementById("family-timeline-list");
    if (logs.length === 0) {
      container.innerHTML = `<p style="color: var(--text-muted);">No medication activity logged today.</p>`;
    } else {
      container.innerHTML = logs.map((l) => `
        <div style="background: #0F172A; padding: 12px; border-radius: 8px; margin-bottom: 8px; border-left: 6px solid #10B981;">
          <strong>${escapeHtml(l.medication_name)}</strong> was logged as <strong>${escapeHtml(l.status)}</strong> at ${new Date(l.taken_at).toLocaleTimeString()}.
        </div>
      `).join("");
    }
  }

  /**
   * Send love note from family.
   */
  function sendFamilyNote(event) {
    event.preventDefault();
    const input = document.getElementById("family-note-text");
    announce(`Message "${input.value}" sent to Grandma!`, "success");
    input.value = "";
  }

  /**
   * Reset sample text for AI scanner demonstration.
   */
  function loadSampleText() {
    const textarea = document.getElementById("ai-raw-text");
    if (textarea) {
      textarea.value = "Patient: Rose Dawson, DOB: 04/12/1944. Phone: (555) 234-5678. Start Lisinopril 10mg once daily in morning with food. Metformin 500mg twice daily with meals. Scheduled follow-up appointment with Dr. Adams at Metro Cardiology on Friday at 10:00 AM.";
    }
  }

  /**
   * HTML sanitization helper.
   */
  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  /**
   * Register PWA Service Worker.
   */
  function registerServiceWorker() {
    if ("serviceWorker" in navigator) {
      window.addEventListener("load", () => {
        navigator.serviceWorker.register("/sw.js").catch((err) => {
          console.warn("ServiceWorker registration failed:", err);
        });
      });
    }
  }

  /**
   * App initialization.
   */
  async function init() {
    registerServiceWorker();
    // Default initial auto-login as Elder for immediate demonstration
    try {
      await login(DEMO_CREDENTIALS.elder.id, DEMO_CREDENTIALS.elder.code);
      setRoleView("elder");
      await loadElderMeds();
      await loadElderAppts();
    } catch (e) {
      console.warn("Auto-login pending manual passcode entry", e);
    }
  }

  return {
    init,
    switchRole,
    submitPasscode,
    takePill,
    submitCheckin,
    triggerSOS,
    readScheduleAloud,
    handleAIExtract,
    confirmDraft,
    handleManualMed,
    handleManualAppt,
    resolveSOS,
    sendFamilyNote,
    loadSampleText,
  };
})();

// Bootstrap on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  CareApp.init();
});
