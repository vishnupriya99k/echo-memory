const $ = (id) => document.getElementById(id);

const todayStr = new Date().toISOString().slice(0, 10);
const datePicker = $("datePicker");
datePicker.value = todayStr;
datePicker.addEventListener("change", loadAll);

async function api(path) {
  
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

function esc(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

async function loadMood() {
  try {
    const summary = await api("/api/caregiver/mood");
    if (!summary.total) {
      $("moodBox").innerHTML = `<span class="dash-empty">No conversation yet today.</span>`;
      return;
    }
    $("moodBox").innerHTML = `<div class="dash-mood-row">` +
      Object.entries(summary.moods).map(([m, c]) => `<span class="dash-mood-chip">${esc(m)} × ${c}</span>`).join("") +
      `</div>`;
  } catch (e) {
    $("moodBox").innerHTML = `<span class="dash-empty">Couldn't load mood.</span>`;
  }
}

async function loadNotes() {
  try {
    const notes = await api(`/api/caregiver/notes?date=${datePicker.value}`);
    if (!notes.length) {
      $("notesBox").innerHTML = `<span class="dash-empty">Nothing flagged for this day.</span>`;
      return;
    }
    $("notesBox").innerHTML = notes.map(n => `
      <div class="dash-note-row">
        <div>
          <div class="dash-note-type">${esc(n.note_type.replace("_", " "))}</div>
          <div>${esc(n.note)}</div>
        </div>
        <div style="color:var(--ink-soft);font-size:0.85rem;white-space:nowrap;">
          ${new Date(n.created_at).toLocaleTimeString()}
        </div>
      </div>`).join("");
  } catch (e) {
    $("notesBox").innerHTML = `<span class="dash-empty">Couldn't load notes.</span>`;
  }
}

async function loadFacts() {
  try {
    const facts = await api("/api/caregiver/facts");
    if (!facts.length) {
      $("factsBox").innerHTML = `<span class="dash-empty">Nothing picked up yet.</span>`;
      return;
    }
    $("factsBox").innerHTML = facts.map(f => {
      let statusHtml;
      if (f.verified === 1) statusHtml = `<span class="dash-badge-verified">✓ Confirmed</span>`;
      else if (f.verified === -1) statusHtml = `<span class="dash-badge-rejected">Rejected</span>`;
      else statusHtml = `
        <div class="dash-fact-actions">
          <button class="dash-btn dash-btn-confirm" data-id="${f.id}" data-action="verify">Confirm</button>
          <button class="dash-btn dash-btn-reject" data-id="${f.id}" data-action="reject">Reject</button>
        </div>`;
      return `
        <div class="dash-fact-row">
          <div>
            <strong>${esc(f.fact_name)}</strong>
            <div style="color:var(--ink-soft);font-size:0.85rem;">${esc(f.source_question)}</div>
          </div>
          ${statusHtml}
        </div>`;
    }).join("");

    $("factsBox").querySelectorAll("button[data-action]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        const action = btn.dataset.action;
        try {
          await fetch(`/api/caregiver/facts/${id}/${action}`, { method: "POST" });
          loadFacts();
        } catch (e) { alert("Couldn't update that fact."); }
      });
    });
  } catch (e) {
    $("factsBox").innerHTML = `<span class="dash-empty">Couldn't load facts.</span>`;
  }
}

async function loadChat() {
  try {
    const messages = await api(`/api/caregiver/chat?date=${datePicker.value}`);
    if (!messages.length) {
      $("chatBox").innerHTML = `<span class="dash-empty">No conversation on this day.</span>`;
      return;
    }
    $("chatBox").innerHTML = messages.map(m => `
      <div class="dash-chat-msg">
        <span class="dash-chat-role">${m.role === "user" ? "Patient" : "Companion"}:</span>
        ${esc(m.content)}
        <span style="color:var(--ink-soft);font-size:0.8rem;"> — ${new Date(m.created_at).toLocaleTimeString()}</span>
      </div>`).join("");
  } catch (e) {
    $("chatBox").innerHTML = `<span class="dash-empty">Couldn't load conversation.</span>`;
  }
}

function loadAll() {
  loadMood();
  loadNotes();
  loadFacts();
  loadChat();
}

loadAll();
