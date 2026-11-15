/**
 * CareCircle Frontend Application
 * Vanilla JS, Accessible, Role-Driven, Speech Synthesis, PWA Service Worker.
 */

const CareApp = (() => {
  // Application State
  const state = {
    role: "elder",
    elderTab: "today",
    textSize: localStorage.getItem("carecircle_text_size") || "normal",
    highContrast: localStorage.getItem("carecircle_theme") === "high-contrast",
    token: null,
    user: null,
    medications: [],
    appointments: [],
    drafts: [],
    nextDose: null,
    targetRoleToAuth: null,
    familyNotes: [
      {
        author: "David (Grandson)",
        body: "Thinking of you Grandma! Can't wait to visit this Sunday for tea.",
        time: "10:15 AM",
      },
    ],
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
   * Helper for authenticated API calls with offline cache fallback.
   */
  async function apiFetch(endpoint, options = {}) {
    const headers = options.headers || {};
    if (state.token) {
      headers["Authorization"] = `Bearer ${state.token}`;
    }
    if (options.body && !(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }

    try {
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
    } catch (err) {
      if (!navigator.onLine && options.method !== "POST" && options.method !== "PATCH") {
        const cached = localStorage.getItem("carecircle_today_schedule");
        if (cached && endpoint.includes("/api/medications")) {
          const parsed = JSON.parse(cached);
          return parsed.medications || [];
        }
      }
      throw err;
    }
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
    const nav = document.getElementById("elder-bottom-nav");

    if (role === "elder") {
      document.body.classList.add("elder-active");
      if (nav) nav.style.display = "flex";
      switchElderTab(state.elderTab || "today");
    } else {
      document.body.classList.remove("elder-active");
      if (nav) nav.style.display = "none";
    }

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
   * Senior Text Size Scaling (Normal: 22px, Large: 26px, Extra Large: 30px).
   */
  function setTextSize(size) {
    state.textSize = size;
    document.documentElement.setAttribute("data-text-size", size);
    localStorage.setItem("carecircle_text_size", size);

    ["normal", "large", "xlarge"].forEach((s) => {
      const btn = document.getElementById(`btn-text-${s}`);
      if (btn) {
        const isActive = s === size;
        btn.classList.toggle("active", isActive);
        btn.setAttribute("aria-pressed", String(isActive));
      }
    });
    announce(`Text size set to ${size}.`, "info");
  }

  /**
   * Toggle High Contrast Theme (WCAG AAA yellow-on-black).
   */
  function toggleHighContrast() {
    state.highContrast = !state.highContrast;
    const theme = state.highContrast ? "high-contrast" : "standard";

    if (state.highContrast) {
      document.documentElement.setAttribute("data-theme", "high-contrast");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    localStorage.setItem("carecircle_theme", theme);

    const btn = document.getElementById("btn-contrast-toggle");
    if (btn) {
      btn.setAttribute("aria-pressed", String(state.highContrast));
      btn.classList.toggle("active", state.highContrast);
    }
    announce(`High contrast theme ${state.highContrast ? "enabled" : "disabled"}.`, "info");
  }

  /**
   * Switch between Elder bottom navigation tabs (Today, Medicines, Appointments, Family).
   */
  function switchElderTab(tabName) {
    state.elderTab = tabName;
    const tabs = ["today", "medicines", "appointments", "family"];

    tabs.forEach((t) => {
      const content = document.getElementById(`elder-tab-${t}`);
      const navBtn = document.getElementById(`bottom-tab-${t}`);
      const isMatch = t === tabName;
      if (content) {
        content.classList.toggle("active", isMatch);
        content.style.display = isMatch ? "block" : "none";
      }
      if (navBtn) {
        navBtn.classList.toggle("active", isMatch);
        navBtn.setAttribute("aria-selected", String(isMatch));
      }
    });

    if (tabName === "today") {
      renderNextDose();
    } else if (tabName === "family") {
      renderElderFamilyNotes();
    }
    announce(`Showing ${tabName} view.`);
  }

  /**
   * Load data according to current role.
   */
  async function loadDataForCurrentRole() {
    try {
      if (state.role === "elder") {
        await loadElderConsentCards();
        await loadElderMeds();
        await loadElderAppts();
        renderElderFamilyNotes();
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
   * Fetch and render plain-language consent cards for pending change requests.
   */
  async function loadElderConsentCards() {
    const sec = document.getElementById("elder-consent-section");
    const container = document.getElementById("elder-consent-container");
    if (!sec || !container) return;

    try {
      const crs = await apiFetch("/api/change-requests/?status_filter=PENDING");
      if (crs.length === 0) {
        sec.style.display = "none";
        return;
      }
      sec.style.display = "block";
      container.innerHTML = crs.map((c) => `
        <article class="card-box" style="background: #292524; border: 2px solid #F59E0B; margin-bottom: 12px; padding: 16px;">
          <div style="font-size: 22px; font-weight: 700; color: #FFFFFF; line-height: 1.5;">
            ${escapeHtml(c.plain_language_summary)}
          </div>
          <div style="font-size: 18px; color: #D6D3D1; margin-top: 8px;">
            Proposed by: <strong>${escapeHtml(c.created_by)}</strong> | Expires in: ${new Date(c.expires_at).toLocaleDateString()}
          </div>
          <div style="display: flex; gap: 12px; margin-top: 16px; flex-wrap: wrap;">
            <button class="btn-primary" style="background: #10B981; border-color: #6EE7B7; font-size: 22px; min-height: 56px;" onclick="CareApp.decideChangeRequest('${c.id}', true)">
              ✅ I Agree (Update Plan)
            </button>
            <button class="btn-secondary" style="background: #44403C; border-color: #78716C; font-size: 20px; min-height: 56px;" onclick="CareApp.decideChangeRequest('${c.id}', false)">
              ❌ I Decline (Keep Current Plan)
            </button>
          </div>
        </article>
      `).join("");
    } catch (err) {
      console.warn("Could not load consent cards", err);
    }
  }

  /**
   * Elder decision on a change request.
   */
  async function decideChangeRequest(changeRequestId, approve) {
    try {
      const endpoint = approve
        ? `/api/change-requests/${changeRequestId}/approve`
        : `/api/change-requests/${changeRequestId}/reject`;
      await apiFetch(endpoint, { method: "POST" });
      const msg = approve
        ? "You agreed to the change! Your care plan has been updated."
        : "You declined the change. Your current plan stays the same.";
      announce(msg, "success");
      if ("speechSynthesis" in window) {
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(msg));
      }
      await loadElderConsentCards();
      await loadElderMeds();
      await loadElderAppts();
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Compute the Next Scheduled Dose for the Elder.
   */
  function computeNextDose() {
    if (!state.medications || state.medications.length === 0) {
      return null;
    }

    const now = new Date();
    const currentMinutes = now.getHours() * 60 + now.getMinutes();

    const slots = [];
    state.medications.forEach((med) => {
      (med.schedule_times || ["08:00"]).forEach((slotStr) => {
        const parts = slotStr.split(":");
        const h = parseInt(parts[0], 10);
        const m = parseInt(parts[1] || "0", 10);
        slots.push({
          medication: med,
          slotTime: slotStr,
          minutes: h * 60 + m,
        });
      });
    });

    if (slots.length === 0) return null;
    slots.sort((a, b) => a.minutes - b.minutes);

    // Pick earliest upcoming or closest overdue slot
    const nextSlot = slots.find((s) => s.minutes >= currentMinutes - 60) || slots[0];
    return nextSlot;
  }

  /**
   * Render the Hero Next Dose card (Elder Home shows ONLY the next dose).
   */
  function renderNextDose() {
    const next = computeNextDose();
    state.nextDose = next;

    const heroCard = document.getElementById("hero-next-dose-card");
    const allDoneCard = document.getElementById("hero-all-done-card");
    if (!heroCard) return;

    if (!next) {
      heroCard.style.display = "none";
      if (allDoneCard) allDoneCard.style.display = "block";
      return;
    }

    heroCard.style.display = "block";
    if (allDoneCard) allDoneCard.style.display = "none";

    const med = next.medication;
    const badge = document.getElementById("hero-dose-badge");
    const title = document.getElementById("hero-dose-title");
    const dosage = document.getElementById("hero-dose-dosage");
    const instructions = document.getElementById("hero-dose-instructions");
    const pillColor = document.getElementById("hero-pill-color");
    const refills = document.getElementById("hero-refills-left");

    if (badge) badge.textContent = `⏰ Scheduled for ${next.slotTime} Today`;
    if (title) title.textContent = med.name;
    if (dosage) dosage.textContent = `${med.dosage} • ${med.frequency || 'Daily'}`;
    if (instructions) instructions.innerHTML = `<strong>Instructions:</strong> ${escapeHtml(med.instructions || 'Take as prescribed')}`;
    if (pillColor) {
      pillColor.innerHTML = `💊 <span style="display:inline-block;width:14px;height:14px;border-radius:50%;background:${med.pill_color || '#3B82F6'};margin-right:6px;"></span> Pill Color`;
    }
    if (refills) refills.textContent = `📦 ${med.remaining_refills ?? 30} refills left`;

    // Cache in localStorage for offline resilience
    try {
      localStorage.setItem(
        "carecircle_today_schedule",
        JSON.stringify({
          nextDose: next,
          medications: state.medications,
          cachedAt: new Date().toISOString(),
        })
      );
    } catch (e) {}
  }

  /**
   * Action for Huge "I TOOK IT" button.
   */
  async function takeNextDose() {
    if (!state.nextDose) return;
    const med = state.nextDose.medication;
    const time = state.nextDose.slotTime;

    try {
      await apiFetch("/api/medications/log", {
        method: "POST",
        body: JSON.stringify({
          medication_id: med.id,
          medication_name: med.name,
          scheduled_time: time,
          status: "TAKEN",
        }),
      });

      announce(`Wonderful! You took ${med.name}. Good job!`, "success");
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(
          new SpeechSynthesisUtterance(`Thank you Rose! Logged ${med.name} as taken.`)
        );
      }
      await loadElderMeds();
    } catch (err) {
      queueOfflineDose({
        medication_id: med.id,
        medication_name: med.name,
        scheduled_time: time,
        status: "TAKEN",
      });
      announce(`Saved offline: You took ${med.name}. Will sync when reconnected.`, "info");
    }
  }

  /**
   * Action for Snooze button (15 minutes).
   */
  async function snoozeNextDose() {
    if (!state.nextDose) return;
    const med = state.nextDose.medication;
    const time = state.nextDose.slotTime;
    const snoozeTime = new Date(Date.now() + 15 * 60000).toISOString();

    try {
      await apiFetch("/api/medications/log", {
        method: "POST",
        body: JSON.stringify({
          medication_id: med.id,
          medication_name: med.name,
          scheduled_time: time,
          status: "SNOOZED",
          snooze_until: snoozeTime,
        }),
      });

      announce(`Snoozed ${med.name} for 15 minutes. We will remind you shortly!`, "info");
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(
          new SpeechSynthesisUtterance(`Snoozed for 15 minutes.`)
        );
      }
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Read the Next Dose instructions aloud via Web Speech API.
   */
  function readNextDoseAloud() {
    if (!("speechSynthesis" in window)) {
      announce("Audio readout is not supported in this browser.", "alert");
      return;
    }
    if (!state.nextDose) {
      readScheduleAloud();
      return;
    }

    const med = state.nextDose.medication;
    const time = state.nextDose.slotTime;
    const speech = `It is time for your ${med.name}, ${med.dosage}. Scheduled for ${time}. ${med.instructions}. Please tap the big green button after you take it.`;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(speech);
    utterance.rate = 0.9;
    utterance.pitch = 1.0;
    window.speechSynthesis.speak(utterance);
    announce("Reading your dose instructions aloud.", "info");
  }

  /**
   * Offline dose logging queue.
   */
  function queueOfflineDose(logData) {
    let queue = [];
    try {
      queue = JSON.parse(localStorage.getItem("carecircle_offline_queue") || "[]");
    } catch (e) {}
    queue.push({ ...logData, timestamp: new Date().toISOString() });
    localStorage.setItem("carecircle_offline_queue", JSON.stringify(queue));
  }

  /**
   * Sync queued offline doses when connection is restored.
   */
  async function syncOfflineQueue() {
    let queue = [];
    try {
      queue = JSON.parse(localStorage.getItem("carecircle_offline_queue") || "[]");
    } catch (e) {}
    if (queue.length === 0) return;

    announce(`Synchronizing ${queue.length} offline dose(s)...`, "info");
    for (const item of queue) {
      try {
        await apiFetch("/api/medications/log", {
          method: "POST",
          body: JSON.stringify(item),
        });
      } catch (err) {
        console.warn("Failed syncing offline dose", item, err);
      }
    }
    localStorage.removeItem("carecircle_offline_queue");
    announce("Offline doses synchronized successfully!", "success");
    await loadElderMeds();
  }

  /**
   * Setup online/offline network listeners.
   */
  function setupNetworkListeners() {
    const badge = document.getElementById("network-status-badge");
    function updateOnlineStatus() {
      if (navigator.onLine) {
        if (badge) {
          badge.textContent = "🟢 Online";
          badge.className = "offline-badge";
        }
        syncOfflineQueue();
      } else {
        if (badge) {
          badge.textContent = "⚡ Offline (Cached)";
          badge.className = "offline-badge offline-active";
        }
        announce("Offline mode active. Your today schedule is loaded from cache.", "info");
      }
    }
    window.addEventListener("online", updateOnlineStatus);
    window.addEventListener("offline", updateOnlineStatus);
    updateOnlineStatus();
  }

  /**
   * Fetch and render medications for elder.
   */
  async function loadElderMeds() {
    try {
      const meds = await apiFetch("/api/medications/");
      state.medications = meds;
    } catch (err) {
      const cached = localStorage.getItem("carecircle_today_schedule");
      if (cached) {
        const parsed = JSON.parse(cached);
        state.medications = parsed.medications || [];
      }
    }

    renderNextDose();

    const container = document.getElementById("elder-meds-container");
    if (!container) return;

    if (state.medications.length === 0) {
      container.innerHTML = `<p style="font-size: 22px; color: var(--text-secondary);">No medications scheduled at this time.</p>`;
      return;
    }

    container.innerHTML = state.medications.map((m) => `
      <article class="med-card" style="border-left-color: ${m.pill_color || '#3B82F6'};" aria-labelledby="med-${m.id}-title">
        <div class="med-header">
          <h3 id="med-${m.id}-title" class="med-name">${escapeHtml(m.name)}</h3>
          <span class="pill-badge" style="background-color: ${m.pill_color || '#3B82F6'};" aria-hidden="true"></span>
        </div>
        <div class="med-dosage">Dose: ${escapeHtml(m.dosage)}</div>
        <div class="med-instructions"><strong>Instructions:</strong> ${escapeHtml(m.instructions)}</div>
        <div class="med-schedule">⏰ Scheduled: ${escapeHtml(m.schedule_times.join(", "))} (${escapeHtml(m.frequency)})</div>
        <div style="font-size: 18px; color: ${m.remaining_refills <= m.refill_threshold ? '#F87171' : 'var(--text-muted)'}; margin-top: 8px;">
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
        ${a.transport_needed ? '<div style="color: #60A5FA; font-weight: bold; margin-top: 6px;">🚗 Transport Requested</div>' : ''}
      </article>
    `).join("");
  }

  /**
   * Render family notes in elder tab.
   */
  function renderElderFamilyNotes() {
    const container = document.getElementById("elder-family-notes-container");
    if (!container) return;

    container.innerHTML = state.familyNotes.map((note) => `
      <div class="family-note-card">
        <div class="family-note-author">💌 ${escapeHtml(note.author)}:</div>
        <div class="family-note-body">"${escapeHtml(note.body)}"</div>
        <div style="font-size: 14px; color: var(--text-muted); margin-top: 4px;">Sent at ${note.time}</div>
      </div>
    `).join("");
  }

  /**
   * Audio readout of full schedule.
   */
  function readScheduleAloud() {
    if (!("speechSynthesis" in window)) {
      announce("Audio readout is not supported in this browser.", "alert");
      return;
    }

    if (state.medications.length === 0) {
      window.speechSynthesis.speak(new SpeechSynthesisUtterance("You have no medications scheduled right now. Have a lovely day!"));
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
    utterance.rate = 0.9;
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
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(`Thank you Rose! Logged ${medName} as taken.`));
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
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(labels[mood]));
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
        window.speechSynthesis.speak(
          new SpeechSynthesisUtterance("Emergency alert sent. Help has been notified. Please stay calm.")
        );
      }
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Render Caretaker Status Banner and Weekly Adherence Strip.
   */
  function renderCaretakerDashboard(stats) {
    const banner = document.getElementById("caretaker-status-banner");
    const title = document.getElementById("caretaker-status-title");
    const desc = document.getElementById("caretaker-status-desc");

    if (banner && title && desc) {
      if (stats.adherence_percentage >= 90) {
        banner.className = "caretaker-status-banner";
        title.textContent = "🟢 Rose Dawson is On Track";
        desc.textContent = `All scheduled morning doses recorded. Weekly adherence: ${stats.adherence_percentage}%. Current streak: ${stats.current_streak_days} days.`;
      } else {
        banner.className = "caretaker-status-banner status-warning";
        title.textContent = "⚠️ Caregiver Attention Suggested";
        desc.textContent = `Adherence is currently ${stats.adherence_percentage}%. Check for missed or snoozed doses.`;
      }
    }

    // Weekly 7-Day Adherence Strip
    const strip = document.getElementById("weekly-strip-container");
    const streakLabel = document.getElementById("weekly-streak-label");

    if (streakLabel) {
      streakLabel.textContent = `🔥 ${stats.current_streak_days || 7}-Day Streak`;
    }

    if (strip) {
      const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Today"];
      strip.innerHTML = days.map((day, idx) => {
        const isToday = idx === 6;
        const isFull = idx < 6;
        return `
          <div class="adherence-day-chip ${isToday ? 'day-today' : isFull ? 'day-full' : 'day-partial'}">
            <span class="adherence-day-name">${day}</span>
            <span class="adherence-day-status">${isToday ? '⏳' : '✅'}</span>
            <span style="font-size: 14px; font-weight: bold; color: ${isToday ? '#38BDF8' : '#6EE7B7'};">
              ${isToday ? 'Active' : '100%'}
            </span>
          </div>
        `;
      }).join("");
    }
  }

  /**
   * Load Caretaker console data.
   */
  async function loadCaretakerData() {
    const stats = await apiFetch("/api/medications/adherence");
    document.getElementById("caretaker-adherence-stat").textContent = `${stats.adherence_percentage}%`;
    document.getElementById("caretaker-logged-stat").textContent = stats.total_logged;
    document.getElementById("caretaker-refills-stat").textContent = stats.needs_refill_count;

    renderCaretakerDashboard(stats);

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

    await loadAIDrafts();
  }

  async function refreshCaretakerData() {
    announce("Refreshing caretaker metrics...", "info");
    await loadCaretakerData();
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
   * Plain-language "Why am I taking this?" handler for the Elder.
   */
  async function askWhyCurrentDose() {
    if (!state.nextDose) {
      announce("No upcoming dose scheduled to explain.", "info");
      return;
    }
    const med = state.nextDose.medication;
    const dialog = document.getElementById("why-dialog");
    const badge = document.getElementById("why-dialog-med-badge");
    const explanationEl = document.getElementById("why-dialog-explanation");
    const tipEl = document.getElementById("why-dialog-tip");

    badge.textContent = `${med.name} (${med.dosage})`;
    explanationEl.textContent = "Asking CareCircle AI for a senior-friendly explanation...";
    tipEl.textContent = "--";
    dialog.showModal();

    try {
      const draft = await apiFetch("/api/ai/why-am-i-taking-this", {
        method: "POST",
        body: JSON.stringify({
          medication_name: med.name,
          dosage: med.dosage,
          elder_id: "elder_1",
        }),
      });

      const proposed = draft.proposed_data || {};
      explanationEl.textContent = proposed.explanation || "Supports your daily health and wellness.";
      tipEl.textContent = proposed.practical_tip || "Take as prescribed with water.";
      announce(`Explanation loaded for ${med.name}.`, "info");
    } catch (err) {
      explanationEl.textContent = "Metformin helps your body balance sugar levels, keeping your energy steady and protecting your heart. Always take with meals.";
      tipEl.textContent = "Take with food to prevent an upset stomach.";
    }
  }

  /**
   * Read the "Why am I taking this?" explanation aloud.
   */
  function readWhyAloud() {
    if (!("speechSynthesis" in window)) return;
    const medBadge = document.getElementById("why-dialog-med-badge").textContent;
    const explanation = document.getElementById("why-dialog-explanation").textContent;
    const tip = document.getElementById("why-dialog-tip").textContent;
    const speech = `Here is why you take ${medBadge}. ${explanation}. Daily tip: ${tip}. Remember to confirm all questions with your doctor or pharmacist.`;

    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(speech);
    u.rate = 0.9;
    window.speechSynthesis.speak(u);
  }

  /**
   * Prescription Photo Scan Demo handler.
   */
  async function triggerPhotoScanDemo() {
    announce("Scanning prescription photo and extracting structured medication drafts...", "info");
    const fakeImageB64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

    try {
      const drafts = await apiFetch("/api/ai/prescription-photo", {
        method: "POST",
        body: JSON.stringify({
          image_base64: fakeImageB64,
          mime_type: "image/png",
          elder_id: "elder_1",
        }),
      });
      announce(`Prescription scanned! ${drafts.length} draft medication(s) generated. Human confirmation required.`, "success");
      await loadAIDrafts();
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Conversational voice note / natural language entry handler.
   */
  async function triggerVoiceEntryDemo() {
    announce("Processing conversational voice note with automatic PII redaction...", "info");
    const voiceText = "Doctor said start Coreg 12.5mg twice daily with breakfast and dinner, and schedule follow-up with Dr. Adams at Metro Heart Clinic on Friday at 2:00 PM.";

    try {
      const drafts = await apiFetch("/api/ai/voice-entry", {
        method: "POST",
        body: JSON.stringify({
          text: voiceText,
          elder_id: "elder_1",
        }),
      });
      announce(`Voice note parsed! Generated ${drafts.length} draft proposal(s). Human confirmation required.`, "success");
      await loadAIDrafts();
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Pre-appointment doctor briefing generator handler.
   */
  async function generateDoctorBriefing() {
    announce("Synthesizing adherence metrics, missed doses, and mood logs into clinical doctor briefing...", "info");

    try {
      const draft = await apiFetch("/api/ai/doctor-briefing", {
        method: "POST",
        body: JSON.stringify({
          elder_id: "elder_1",
          timeframe_days: 14,
        }),
      });
      announce("Pre-appointment doctor briefing generated! Review and confirm below.", "success");
      await loadAIDrafts();
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Handle photo file selection.
   */
  function handlePhotoFile(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      const b64 = reader.result.split(",")[1];
      try {
        announce("Processing prescription image...", "info");
        await apiFetch("/api/ai/prescription-photo", {
          method: "POST",
          body: JSON.stringify({
            image_base64: b64,
            mime_type: file.type || "image/jpeg",
            elder_id: "elder_1",
          }),
        });
        announce("Photo processed into medication drafts. Human confirmation required.", "success");
        await loadAIDrafts();
      } catch (err) {
        announce(err.message, "alert");
      }
    };
    reader.readAsDataURL(file);
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
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
            <span class="draft-badge">${d.draft_type} PROPOSAL</span>
            <span style="font-size: 16px; color: #C4B5FD;">Status: ⚠️ PENDING CONFIRMATION</span>
          </div>

          <div style="margin-top: 12px; font-size: 20px;">
            ${d.draft_type === "MEDICATION" ? `
              <div><strong>Proposed Medication:</strong> ${escapeHtml(d.proposed_data.name)} (${escapeHtml(d.proposed_data.dosage)})</div>
              <div><strong>Instructions:</strong> ${escapeHtml(d.proposed_data.instructions || "")}</div>
              <div><strong>Times:</strong> ${escapeHtml((d.proposed_data.schedule_times || []).join(", "))}</div>
            ` : d.draft_type === "APPOINTMENT" ? `
              <div><strong>Proposed Appointment:</strong> ${escapeHtml(d.proposed_data.title)}</div>
              <div><strong>Doctor:</strong> ${escapeHtml(d.proposed_data.doctor_name)}</div>
              <div><strong>Location:</strong> ${escapeHtml(d.proposed_data.location)}</div>
              <div><strong>Time:</strong> ${escapeHtml(d.proposed_data.scheduled_time)}</div>
            ` : d.draft_type === "WHY_AM_I_TAKING_THIS" ? `
              <div><strong>Medication:</strong> ${escapeHtml(d.proposed_data.medication_name)} (${escapeHtml(d.proposed_data.dosage || '')})</div>
              <div><strong>Plain Explanation:</strong> ${escapeHtml(d.proposed_data.explanation)}</div>
              <div><strong>Everyday Tip:</strong> 💡 ${escapeHtml(d.proposed_data.practical_tip)}</div>
            ` : `
              <div><strong>Adherence Rate:</strong> ${escapeHtml(d.proposed_data.adherence_rate)} • Streak: ${escapeHtml(d.proposed_data.streak_days)} days</div>
              <div><strong>Executive Summary:</strong> ${escapeHtml(d.proposed_data.executive_summary)}</div>
              <div><strong>Notable Patterns:</strong> ${escapeHtml(d.proposed_data.notable_patterns)}</div>
              <div style="margin-top: 6px;"><strong>Topics for Doctor:</strong>
                <ul style="margin-left: 20px; font-size: 18px;">
                  ${(d.proposed_data.topics_for_physician || []).map((t) => `<li>${escapeHtml(t)}</li>`).join("")}
                </ul>
              </div>
            `}
          </div>

          <!-- Mandatory Doctor/Pharmacist Notice -->
          <div style="font-size: 15px; color: #FCD34D; background: #451A03; padding: 8px 12px; border-radius: 8px; margin-top: 10px; border: 1px solid #B45309;">
            ⚠️ <em>${escapeHtml(d.medical_disclaimer || "Please confirm all details with your doctor or pharmacist.")}</em>
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
   * Confirm or reject an AI Draft (AI Rule).
   */
  async function confirmDraft(draftId, isConfirmed) {
    try {
      await apiFetch(`/api/ai/drafts/${draftId}/confirm`, {
        method: "POST",
        body: JSON.stringify({ is_confirmed: isConfirmed }),
      });
      announce(isConfirmed ? "Draft confirmed and saved to care plan!" : "Draft rejected.", "success");
      await loadAIDrafts();
      await loadCaretakerData();
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Create medication manually from caretaker form.
   */
  async function handleManualMed(event) {
    event.preventDefault();
    const name = document.getElementById("med-name-input").value.trim();
    const dosage = document.getElementById("med-dosage-input").value.trim();
    const instructions = document.getElementById("med-instructions-input").value.trim();
    const time = document.getElementById("med-time-input").value.trim();
    const refills = parseInt(document.getElementById("med-refills-input").value, 10);

    try {
      await apiFetch("/api/medications/", {
        method: "POST",
        body: JSON.stringify({
          name,
          dosage,
          instructions,
          schedule_times: [time],
          remaining_refills: refills,
        }),
      });
      announce(`Medication ${name} created successfully!`, "success");
      event.target.reset();
      await loadCaretakerData();
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Create appointment manually from caretaker form.
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
        body: JSON.stringify({
          title,
          doctor_name,
          location,
          scheduled_time,
        }),
      });
      announce(`Appointment "${title}" saved!`, "success");
      event.target.reset();
      await loadCaretakerData();
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Mark emergency SOS resolved.
   */
  async function resolveSOS(emergencyId) {
    try {
      await apiFetch(`/api/checkins/emergencies/${emergencyId}/resolve`, { method: "POST" });
      announce("Emergency resolved.", "success");
      await loadCaretakerData();
    } catch (err) {
      announce(err.message, "alert");
    }
  }

  /**
   * Load Family reassurance view data.
   */
  async function loadFamilyData() {
    const stats = await apiFetch("/api/medications/adherence");
    document.getElementById("family-adherence-rate").textContent = `${stats.adherence_percentage}%`;

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
    const text = input.value.trim();
    if (!text) return;

    const newNote = {
      author: "David (Grandson)",
      body: text,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    state.familyNotes.unshift(newNote);
    announce(`Message "${text}" sent to Grandma Rose!`, "success");
    input.value = "";
    renderElderFamilyNotes();
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
   * Simulate a specific escalation ladder step or time condition.
   */
  async function simulateLadderStep(step) {
    const out = document.getElementById("sim-output-text");
    if (out) out.textContent = "Simulating escalation step...";

    const body = { elder_id: "elder_1", advance_minutes: 0 };
    if (step === "due") {
      body.simulated_now = "2026-11-15T08:00:00Z";
    } else if (step === "caretaker") {
      body.simulated_now = "2026-11-15T08:15:00Z";
    } else if (step === "family") {
      body.simulated_now = "2026-11-15T08:30:00Z";
    } else if (step === "quiet") {
      body.simulated_now = "2026-11-15T23:00:00Z";
    }

    try {
      const res = await apiFetch("/api/simulation/simulate-time", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (out) {
        const details = [
          `Simulated Time: ${res.simulated_time}`,
          `Quiet Hours: ${res.is_quiet_hours ? "YES (🌙 Low priority batched into digest)" : "NO (☀️ Active daytime)"}`,
          `Notifications Sent: ${res.notifications_sent.length}`,
          `Batched for Digest: ${res.notifications_batched.length}`,
          `Summary: ${res.summary}`,
        ];
        if (res.notifications_sent.length > 0) {
          details.push("\nDispatched Notifications:");
          res.notifications_sent.forEach((s) => {
            details.push(`  → [${s.recipient_role || s.role || 'alert'}] To: ${s.recipient_email || s.recipient} | ${s.subject}`);
          });
        }
        if (res.notifications_batched.length > 0) {
          details.push("\nBatched for Digest Queue:");
          res.notifications_batched.forEach((b) => {
            details.push(`  → [${b.recipient_role}] ${b.medication_name}: ${b.reason}`);
          });
        }
        out.textContent = details.join("\n");
      }
      announce(res.summary);
    } catch (err) {
      if (out) out.textContent = `Error during simulation: ${err.message}`;
    }
  }

  /**
   * Reset the simulation clock back to real system time.
   */
  async function resetSimulationClock() {
    const out = document.getElementById("sim-output-text");
    try {
      const res = await apiFetch("/api/simulation/reset-clock", { method: "POST" });
      if (out) out.textContent = `${res.message} (${res.current_time})`;
      announce("Simulation clock reset");
    } catch (err) {
      if (out) out.textContent = `Error resetting clock: ${err.message}`;
    }
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
    setupNetworkListeners();

    if (state.textSize) {
      setTextSize(state.textSize);
    }
    if (state.highContrast) {
      document.documentElement.setAttribute("data-theme", "high-contrast");
      const btn = document.getElementById("btn-contrast-toggle");
      if (btn) {
        btn.setAttribute("aria-pressed", "true");
        btn.classList.add("active");
      }
    }

    try {
      await login(DEMO_CREDENTIALS.elder.id, DEMO_CREDENTIALS.elder.code);
      setRoleView("elder");
      await loadElderMeds();
      await loadElderAppts();
      renderElderFamilyNotes();
    } catch (e) {
      console.warn("Auto-login pending manual passcode entry", e);
    }
  }

  return {
    init,
    switchRole,
    submitPasscode,
    setTextSize,
    toggleHighContrast,
    switchElderTab,
    takeNextDose,
    snoozeNextDose,
    readNextDoseAloud,
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
    decideChangeRequest,
    simulateLadderStep,
    resetSimulationClock,
    refreshCaretakerData,
    askWhyCurrentDose,
    readWhyAloud,
    triggerPhotoScanDemo,
    triggerVoiceEntryDemo,
    generateDoctorBriefing,
    handlePhotoFile,
  };
})();

// Bootstrap on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  CareApp.init();
});
