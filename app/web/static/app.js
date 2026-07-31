const toast = document.getElementById("toast");
const authStatus = document.getElementById("authStatus");

/** @type {{ id: string, text: string, eventId?: string|null, calendarId?: string|null }[]} */
let tasks = [];
/** @type {any[]} */
let currentProposals = [];

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => {
    toast.hidden = true;
  }, 2800);
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function toLocalInputValue(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fromLocalInputValue(value) {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

function formatRange(start, end) {
  try {
    const s = new Date(start);
    const e = new Date(end);
    const opts = { weekday: "short", hour: "numeric", minute: "2-digit" };
    return `${s.toLocaleString(undefined, opts)} → ${e.toLocaleString(undefined, { hour: "numeric", minute: "2-digit" })}`;
  } catch {
    return `${start || "?"} → ${end || "?"}`;
  }
}

function connectGoogle() {
  window.location.href = "/api/auth/google";
}

document.querySelectorAll(".nav-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll(".nav-tab").forEach((b) => {
      const active = b.dataset.tab === tab;
      b.classList.toggle("active", active);
      b.setAttribute("aria-selected", active ? "true" : "false");
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      const match = panel.id === `tab-${tab}`;
      panel.classList.toggle("active", match);
      panel.hidden = !match;
    });
  });
});

document.getElementById("connectGoogle").addEventListener("click", (e) => {
  e.currentTarget.disabled = true;
  connectGoogle();
});
document.getElementById("connectGooglePalette").addEventListener("click", (e) => {
  e.currentTarget.disabled = true;
  connectGoogle();
});

/* —— Chip task list —— */
const taskChips = document.getElementById("taskChips");
const taskInput = document.getElementById("taskInput");
const chipBox = document.getElementById("chipBox");

function renderChips() {
  taskChips.innerHTML = "";
  tasks.forEach((task) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.dataset.id = task.id;
    chip.innerHTML = `<span class="chip-label">${escapeHtml(task.text)}</span><button type="button" class="chip-x" aria-label="Remove ${escapeHtml(task.text)}">×</button>`;
    chip.querySelector(".chip-x").addEventListener("click", () => removeTask(task.id));
    taskChips.appendChild(chip);
  });
}

function addTask(text) {
  const cleaned = text.trim().replace(/^[-•*]\s*/, "");
  if (!cleaned) return;
  if (tasks.some((t) => t.text.toLowerCase() === cleaned.toLowerCase())) {
    showToast("Task already on the list");
    return;
  }
  tasks.push({ id: crypto.randomUUID(), text: cleaned, eventId: null, calendarId: null });
  renderChips();
}

async function removeTask(id) {
  const task = tasks.find((t) => t.id === id);
  if (!task) return;

  // Also remove matching proposal events from calendar
  const related = currentProposals.filter(
    (p) =>
      (task.eventId && p.event_id === task.eventId) ||
      (p.task_title || "").toLowerCase() === task.text.toLowerCase()
  );

  const toDelete = [];
  if (task.eventId) {
    toDelete.push({ event_id: task.eventId, calendar_id: task.calendarId || null });
  }
  for (const p of related) {
    if (p.event_id && !toDelete.some((d) => d.event_id === p.event_id)) {
      toDelete.push({ event_id: p.event_id, calendar_id: p.calendar_id || null });
    }
  }

  for (const item of toDelete) {
    try {
      const res = await fetch("/api/events/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(item),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Could not delete calendar event");
      }
    } catch (err) {
      showToast(err.message || "Calendar delete failed");
    }
  }

  tasks = tasks.filter((t) => t.id !== id);
  currentProposals = currentProposals.filter(
    (p) => (p.task_title || "").toLowerCase() !== task.text.toLowerCase()
  );
  renderChips();
  renderProposals(currentProposals);
  if (toDelete.length) showToast("Removed from list and calendar");
}

taskInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    addTask(taskInput.value);
    taskInput.value = "";
  } else if (event.key === "Backspace" && !taskInput.value && tasks.length) {
    removeTask(tasks[tasks.length - 1].id);
  }
});

chipBox.addEventListener("click", () => taskInput.focus());

/* —— Schedule proposals —— */
const proposalsEl = document.getElementById("proposals");
const summaryText = document.getElementById("summaryText");
const feedbackBar = document.getElementById("feedbackBar");
const submitFeedback = document.getElementById("submitFeedback");
const traceEl = document.getElementById("trace");
const planForm = document.getElementById("planForm");
const planBtn = document.getElementById("planBtn");

function renderProposals(proposals) {
  proposalsEl.innerHTML = "";
  currentProposals = proposals || [];
  if (!currentProposals.length) {
    feedbackBar.hidden = true;
    return;
  }
  feedbackBar.hidden = false;

  // Sync event ids back onto chips
  currentProposals.forEach((p) => {
    const match = tasks.find((t) => t.text.toLowerCase() === (p.task_title || "").toLowerCase());
    if (match) {
      match.eventId = p.event_id || match.eventId;
      match.calendarId = p.calendar_id || match.calendarId;
    }
  });

  currentProposals.forEach((p, idx) => {
    const card = document.createElement("article");
    card.className = "card";
    card.style.animationDelay = `${idx * 0.04}s`;
    const startLocal = toLocalInputValue(p.start);
    const endLocal = toLocalInputValue(p.end);
    const cal = p.calendar_name || p.calendar_id || "calendar";
    card.innerHTML = `
      <div class="card-top">
        <h3>${escapeHtml(p.task_title || "Untitled")}</h3>
        <span class="badge">${escapeHtml(cal)}</span>
      </div>
      <p class="meta">${escapeHtml(formatRange(p.start, p.end))}</p>
      <p class="rationale">${escapeHtml(p.rationale || "")}</p>
      <div class="card-actions">
        <label><input type="radio" name="action-${idx}" value="accept" checked /> Accept</label>
        <label><input type="radio" name="action-${idx}" value="reject" /> Reject</label>
        <label><input type="radio" name="action-${idx}" value="edit" /> Edit</label>
        <label class="time-field">Start <input type="datetime-local" class="edit-start" value="${startLocal}" /></label>
        <label class="time-field">End <input type="datetime-local" class="edit-end" value="${endLocal}" /></label>
      </div>
    `;
    proposalsEl.appendChild(card);
  });
}

planForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!tasks.length) {
    showToast("Add at least one task");
    taskInput.focus();
    return;
  }

  planBtn.disabled = true;
  planBtn.textContent = "Planning…";
  summaryText.textContent = "Detecting calendars and free slots…";
  proposalsEl.innerHTML = "";
  feedbackBar.hidden = true;
  traceEl.hidden = true;

  const formData = new FormData();
  formData.append("task_list", tasks.map((t) => `- ${t.text}`).join("\n"));
  formData.append("target_day", document.getElementById("targetDay").value);
  // Propose first; writing happens from Put in calendar after accept/reject/edit.
  formData.append("write_to_calendar", "false");

  try {
    const res = await fetch("/api/plan", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Planning failed");

    summaryText.textContent = data.summary || (data.ok ? "Schedule proposed." : "Planning incomplete.");
    renderProposals(data.proposals || []);

    const skipped = data.skipped_tasks || [];
    if (skipped.length) {
      const skippedLower = new Set(skipped.map((s) => String(s).trim().toLowerCase()));
      tasks = tasks.filter((t) => !skippedLower.has(t.text.trim().toLowerCase()));
      renderChips();
    }

    if (data.tool_trace?.length) {
      traceEl.hidden = false;
      traceEl.textContent = JSON.stringify(data.tool_trace, null, 2);
    }
    if (skipped.length && !(data.proposals || []).length) {
      showToast(`Skipped existing: ${skipped.join(", ")}`);
    } else if (skipped.length) {
      showToast(`Proposal ready; skipped existing: ${skipped.join(", ")}`);
    } else {
      showToast(data.ok ? "Proposal ready — review, then Put in calendar" : "Agent finished with warnings");
    }
  } catch (err) {
    summaryText.textContent = err.message || "Something went wrong.";
    showToast(summaryText.textContent);
  } finally {
    planBtn.disabled = false;
    planBtn.textContent = "Plan schedule";
  }
});

submitFeedback.addEventListener("click", async () => {
  const items = [];
  const cards = proposalsEl.querySelectorAll(".card");
  cards.forEach((card, idx) => {
    const proposal = currentProposals[idx];
    const action = card.querySelector(`input[name="action-${idx}"]:checked`)?.value || "accept";
    const startVal = card.querySelector(".edit-start")?.value;
    const endVal = card.querySelector(".edit-end")?.value;
    const finalStart = fromLocalInputValue(startVal) || proposal.start;
    const finalEnd = fromLocalInputValue(endVal) || proposal.end;

    items.push({
      action,
      task_title: proposal.task_title,
      category: proposal.category || null,
      proposed_start: proposal.start,
      proposed_end: proposal.end,
      final_start: action === "edit" ? finalStart : proposal.start,
      final_end: action === "edit" ? finalEnd : proposal.end,
      event_id: proposal.event_id || null,
      calendar_id: proposal.calendar_id || null,
      reason: action === "reject" ? "Rejected in UI" : null,
    });
  });

  submitFeedback.disabled = true;
  submitFeedback.textContent = "Writing…";
  try {
    const res = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not update calendar");

    const results = data.results || [];
    let written = 0;
    let rejected = 0;
    let failed = 0;
    results.forEach((r, idx) => {
      const cal = r.calendar || {};
      if (r.action === "reject") rejected += 1;
      else if (cal.ok) {
        written += 1;
        if (r.event_id && currentProposals[idx]) {
          currentProposals[idx].event_id = r.event_id;
          const match = tasks.find(
            (t) => t.text.toLowerCase() === (r.task_title || "").toLowerCase()
          );
          if (match) {
            match.eventId = r.event_id;
            match.calendarId = r.calendar_id || match.calendarId;
          }
        }
      } else {
        failed += 1;
      }
    });

    const parts = [];
    if (written) parts.push(`${written} written`);
    if (rejected) parts.push(`${rejected} rejected`);
    if (failed) parts.push(`${failed} failed`);
    showToast(parts.length ? parts.join(" · ") : "Preference memory updated");
    if (failed) {
      const firstErr = results.find((r) => r.calendar && r.calendar.ok === false);
      if (firstErr?.calendar?.error) {
        summaryText.textContent = `Some events failed: ${firstErr.calendar.error}`;
      }
    } else if (written) {
      summaryText.textContent = `Saved to Google Calendar (${written} event${written === 1 ? "" : "s"}).`;
    }
  } catch (err) {
    showToast(err.message || "Could not put events in calendar");
  } finally {
    submitFeedback.disabled = false;
    submitFeedback.textContent = "Put in calendar";
  }
});

/* —— Palette tab —— */
const paletteForm = document.getElementById("paletteForm");
const paletteBtn = document.getElementById("paletteBtn");
const paletteSummary = document.getElementById("paletteSummary");
const palettePreview = document.getElementById("palettePreview");
const assignmentsEl = document.getElementById("assignments");
const paletteTrace = document.getElementById("paletteTrace");

function renderPalettePreview(hexes, assignments) {
  palettePreview.innerHTML = "";
  const entries = (assignments || []).length
    ? assignments.map((a) => ({
        label: a.calendar_name || a.calendar_id,
        hex: a.background_color,
        fg: a.foreground_color || "#000",
      }))
    : (hexes || []).map((hex, i) => ({ label: `tone ${i + 1}`, hex, fg: "#000" }));

  if (!entries.length) {
    palettePreview.hidden = true;
    return;
  }
  palettePreview.hidden = false;
  for (const entry of entries) {
    const el = document.createElement("div");
    el.className = "swatch";
    el.innerHTML = `<i style="background:${entry.hex}"></i><span>${escapeHtml(entry.label)}</span>`;
    palettePreview.appendChild(el);
  }
}

function renderAssignments(assignments) {
  assignmentsEl.innerHTML = "";
  (assignments || []).forEach((a, idx) => {
    const card = document.createElement("article");
    card.className = "card";
    card.style.animationDelay = `${idx * 0.04}s`;
    card.innerHTML = `
      <div class="card-top">
        <h3>${escapeHtml(a.calendar_name || a.calendar_id || "Calendar")}</h3>
        <span class="badge color-badge" style="background:${escapeHtml(a.background_color || "#ccc")};color:${escapeHtml(a.foreground_color || "#000")}">Aa</span>
      </div>
      <p class="meta">${escapeHtml(a.background_color || "")} · text ${escapeHtml(a.foreground_color || "#000")}</p>
      <p class="rationale">${escapeHtml(a.rationale || "")}</p>
    `;
    assignmentsEl.appendChild(card);
  });
}

paletteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  paletteBtn.disabled = true;
  paletteBtn.textContent = "Generating…";
  paletteSummary.textContent = "Mapping palette onto your calendars…";
  assignmentsEl.innerHTML = "";
  paletteTrace.hidden = true;

  const formData = new FormData();
  formData.append("aesthetic_description", document.getElementById("aesthetic").value);
  formData.append("style_preferences", document.getElementById("stylePrefs").value);
  formData.append("apply_changes", document.getElementById("applyPalette").checked ? "true" : "false");
  const image = document.getElementById("image").files[0];
  if (image) formData.append("image", image);

  try {
    const res = await fetch("/api/palette", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Palette failed");

    paletteSummary.textContent = data.summary || (data.ok ? "Palette applied." : "Palette incomplete.");
    if (data.notes?.length) {
      paletteSummary.textContent += " " + data.notes.join(" ");
    }
    renderPalettePreview(data.source_hex_palette, data.assignments);
    renderAssignments(data.assignments || []);
    if (data.tool_trace?.length) {
      paletteTrace.hidden = false;
      paletteTrace.textContent = JSON.stringify(data.tool_trace, null, 2);
    }
    showToast(data.ok ? "Calendar colors updated" : "Finished with warnings");
  } catch (err) {
    paletteSummary.textContent = err.message || "Something went wrong.";
    showToast(paletteSummary.textContent);
  } finally {
    paletteBtn.disabled = false;
    paletteBtn.textContent = "Generate palette";
  }
});
