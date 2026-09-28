// EchoMemory Companion — frontend logic
// Talks to the FastAPI backend (backend/api.py) over relative /api/* routes.

const MOOD_EMOJI = { happy: "😊", calm: "😌", confused: "😕", distressed: "😟", lonely: "🥺" };
const TYPE_EMOJI = { medication: "💊", task: "🔔", appointment: "📅" };

//  Helpers 
const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: options.body && !(options.body instanceof FormData)
      ? { "Content-Type": "application/json" } : undefined,
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${text}`);
  }
  return res.status === 204 ? null : res.json();
}

function capitalize(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

//  Sidebar 
const sidebar = $("sidebar");
const overlay = $("drawerOverlay");

function openSidebar() {
  sidebar.classList.add("open");
  overlay.classList.add("visible");
  $("openSidebarBtn").setAttribute("aria-expanded", "true");
}
function closeSidebar() {
  sidebar.classList.remove("open");
  overlay.classList.remove("visible");
  $("openSidebarBtn").setAttribute("aria-expanded", "false");
}
$("openSidebarBtn").addEventListener("click", openSidebar);
$("closeSidebarBtn").addEventListener("click", closeSidebar);
overlay.addEventListener("click", closeSidebar);

//  Mood badge 
function setMood(mood, emoji) {
  $("moodEmoji").textContent = emoji || MOOD_EMOJI[mood] || "😌";
  $("moodWord").textContent = capitalize(mood || "calm");
}

//  Mood chips (status bar) 
const moodCounts = {};

function updateMoodChips(mood) {
  if (!mood) return;
  moodCounts[mood] = (moodCounts[mood] || 0) + 1;
  const container = $("moodChips");
  container.innerHTML = "";
  Object.entries(moodCounts).forEach(([m, c]) => {
    const chip = document.createElement("span");
    chip.className = "mood-chip";
    chip.textContent = `${MOOD_EMOJI[m] || "❔"} ${capitalize(m)}`;
    container.appendChild(chip);
  });
}

//  Chat 
const chatArea = $("chatArea");

// Get patient name from backend status or default
let patientName = "";

function addMessage(role, text, emoji) {
  const div = document.createElement("div");
  div.className = `msg msg-${role}`;
  div.textContent = role === "user" && emoji ? `${emoji} ${text}` : text;
  chatArea.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
  return div;
}

function addThinking() {
  const div = document.createElement("div");
  div.className = "msg msg-assistant msg-thinking";
  div.textContent = "Remembering…";
  chatArea.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
  return div;
}

function addPhotoMessage(url) {
  const div = document.createElement("div");
  div.className = "msg msg-assistant msg-photo";
  const img = document.createElement("img");
  img.src = url;
  img.alt = "Family photo";
  img.className = "chat-photo";
  div.appendChild(img);
  chatArea.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
}

// Session log for new info and wellbeing
const sessionLog = [];

//  Reminder follow-up tracking 
const SNOOZE_MS = 30 * 60 * 1000; // 30 minutes
let awaitingReminderReply = null; 
let snoozedReminders = {};        

function loadSnoozed() {
  try {
    snoozedReminders = JSON.parse(localStorage.getItem("echo_snoozed_reminders") || "{}");
  } catch (e) { snoozedReminders = {}; }
}
function saveSnoozed() {
  try { localStorage.setItem("echo_snoozed_reminders", JSON.stringify(snoozedReminders)); }
  catch (e) { /* storage unavailable, snooze just won't survive a reload */ }
}

const FORGOT_RE = /\b(forgot|forgotten|didn'?t|haven'?t|not yet|nope|no i|not really)\b/i;
const CONFIRM_DONE_RE = /\b(yes|yeah|yep|i did|took it|already (took|did|had)|done|finished)\b/i

function logSessionNote(type, note) {
  const entry = { type, note, time: new Date().toLocaleTimeString() };
  sessionLog.push(entry);
  
  api("/session/note", {
    method: "POST",
    body: JSON.stringify({ note_type: type, note }),
  }).catch(() => { /* non-critical if this fails, still kept locally */ });
}

async function sendQuestion(question) {
  if (!question || !question.trim()) return;
  question = question.trim();

  addMessage("user", question);
  const thinkingEl = addThinking();
  $("sendBtn").disabled = true;


  const lowerQ = question.toLowerCase();
  const wellbeingKeywords = ["tired", "exhausted", "unwell", "sick", "pain", "hurts", "difficult", "struggle", "forgot"];
  const mentionsWellbeing = wellbeingKeywords.some(w => lowerQ.includes(w));

  if (awaitingReminderReply && Date.now() - awaitingReminderReply.askedAt > 5 * 60 * 1000) {
    awaitingReminderReply = null;
  }

  let handledReminderReply = false;
  if (awaitingReminderReply) {
    if (FORGOT_RE.test(lowerQ)) {
      const until = Date.now() + SNOOZE_MS;
      awaitingReminderReply.ids.forEach((id, i) => {
        snoozedReminders[id] = { until, label: awaitingReminderReply.labels[i] };
      });
      saveSnoozed();
      logSessionNote("missed_reminder_confirmed",
        `Patient confirmed not yet done: ${awaitingReminderReply.labels.join(", ")}. Will gently check again in 30 min.`);
      awaitingReminderReply = null;
      handledReminderReply = true;
    } else if (CONFIRM_DONE_RE.test(lowerQ)) {
      const ids = awaitingReminderReply.ids;
      const labels = awaitingReminderReply.labels;
      awaitingReminderReply = null;
      handledReminderReply = true;
      Promise.all(ids.map(id => api(`/reminders/${id}/done`, { method: "POST" }).catch(() => {})))
        .then(refreshReminders);
      logSessionNote("missed_reminder", `Patient confirmed completing: ${labels.join(", ")}`);
    }
  }

  try {
    const result = await api("/ask", { method: "POST", body: JSON.stringify({ question }) });
    thinkingEl.remove();

    setMood(result.mood, result.mood_emoji);
    updateMoodChips(result.mood);
    addMessage("assistant", result.answer);
    speak(result.answer);
    if (result.photo_url) addPhotoMessage(result.photo_url);

    if (result.alert_caregiver) $("caregiverAlert").hidden = false;
    if (result.due_reminder) showDueAlert(result.due_reminder);


    if (mentionsWellbeing && !handledReminderReply) {
      logSessionNote("wellbeing", question);
      await checkPendingRemindersForWellbeing();
    }

    if (result.new_info_detected) {
      const summaries = result.new_info_summaries && result.new_info_summaries.length
        ? result.new_info_summaries.join(" ")
        : `Mentioned "${(result.new_info_names || []).join(", ")}" — not in family records.`;
      logSessionNote("new_info", summaries);
    }

  } catch (err) {
    thinkingEl.remove();
    addMessage("assistant", "I'm having a little trouble right now. Could we try again in a moment?");
    console.error(err);
  } finally {
    $("sendBtn").disabled = false;
  }
}

async function checkPendingRemindersForWellbeing() {
  try {
    const list = await api("/reminders/today");
    const now = new Date();
    const currentMinutes = now.getHours() * 60 + now.getMinutes();

    const pending = list.filter(r => {
      if (r.done_today) return false;
      const snooze = snoozedReminders[r.id];
      if (snooze && snooze.until > Date.now()) return false; 
      const [h, m] = r.time.split(":").map(Number);
      const reminderMinutes = h * 60 + m;
      return reminderMinutes <= currentMinutes; 
    });

    if (pending.length > 0) {
      const pendingMeds = pending.filter(r => r.type === "medication");
      const pendingMeals = pending.filter(r => ["Breakfast", "Lunch", "Dinner"].some(m => r.label.includes(m)));
      const pendingWater = pending.filter(r => r.label.includes("Water"));

      let followUp = "";
      if (pendingMeds.length > 0) {
        followUp = `I also noticed you may not have taken your ${pendingMeds.map(r => r.label).join(", ")} yet. Have you been able to take your medication?`;
      } else if (pendingMeals.length > 0) {
        followUp = `I also noticed you may not have had your ${pendingMeals.map(r => r.label).join(" or ")} yet. Have you eaten today?`;
      } else if (pendingWater.length > 0) {
        followUp = `I also want to remind you to drink some water — staying hydrated can help with tiredness.`;
      }

      if (followUp) {
        setTimeout(() => {
          addMessage("assistant", followUp);
          speak(followUp);
        }, 1200);

        awaitingReminderReply = {
          ids: pending.map(r => r.id),
          labels: pending.map(r => r.label),
          askedAt: Date.now(),
        };

        const missedLabels = pending.map(r => `${r.label} (${r.time})`).join(", ");
        logSessionNote("missed_reminder", `Possibly missed: ${missedLabels}`);
      }
    }
  } catch (e) { /* non-critical */ }
}


async function checkSnoozedReminders() {
  const now = Date.now();
  const dueIds = Object.entries(snoozedReminders).filter(([, s]) => s.until <= now);
  if (!dueIds.length) return;

  let list;
  try { list = await api("/reminders/today"); } catch (e) { return; }

  dueIds.forEach(([id, snooze]) => {
    const reminder = list.find(r => String(r.id) === String(id));
    delete snoozedReminders[id];
    if (!reminder || reminder.done_today) return; // already taken care of, nothing to re-ask

    const followUp = `I wanted to gently check again — have you had a chance to take your ${snooze.label}?`;
    addMessage("assistant", followUp);
    speak(followUp);
    awaitingReminderReply = { ids: [reminder.id], labels: [snooze.label], askedAt: Date.now() };
  });
  saveSnoozed();
}

$("sendBtn").addEventListener("click", () => {
  const input = $("textInput");
  const value = input.value;
  input.value = "";
  sendQuestion(value);
});

$("textInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    $("sendBtn").click();
  }
});

//  TTS 
function speak(text) {
  if (!$("ttsToggle").checked) return;
  try {
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 0.9;
    utter.pitch = 1.0;
    window.speechSynthesis.speak(utter);
  } catch (e) { }
}

// ---------- STT ----------
const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
const micBtn = $("micBtn");

if (!SpeechRecognitionCtor) {
  micBtn.hidden = true;
} else {
  const recognition = new SpeechRecognitionCtor();
  recognition.lang = "en-US";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  let listening = false;

  micBtn.addEventListener("click", () => {
    if (listening) { recognition.stop(); return; }
    try {
      recognition.start();
      listening = true;
      micBtn.classList.add("listening");
      micBtn.querySelector(".btn-round-label").textContent = "Listening…";
    } catch (e) { }
  });

  recognition.addEventListener("result", (e) => {
    sendQuestion(e.results[0][0].transcript);
  });

  const reset = () => {
    listening = false;
    micBtn.classList.remove("listening");
    micBtn.querySelector(".btn-round-label").textContent = "Speak";
  };
  recognition.addEventListener("end", reset);
  recognition.addEventListener("error", reset);
}

//  Due-now alert 
function showDueAlert(text) {
  const el = $("dueAlert");
  el.textContent = `⏰ ${text}`;
  el.hidden = false;
}

async function refreshDueAlert() {
  try {
    const { alert } = await api("/reminders/due");
    if (alert) showDueAlert(alert);
    else $("dueAlert").hidden = true;
  } catch (e) { }
}

//  Reminder modal 
const reminderModal = $("reminderModalBackdrop");

function openReminderModal() { reminderModal.hidden = false; }
function closeReminderModal() { reminderModal.hidden = true; }

$("openReminderModal").addEventListener("click", openReminderModal);
$("closeReminderModal").addEventListener("click", closeReminderModal);
reminderModal.addEventListener("click", (e) => {
  if (e.target === reminderModal) closeReminderModal();
});

// Tabs
document.querySelectorAll(".modal-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".modal-tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    const which = tab.dataset.tab;
    $("modalViewBody").hidden = which !== "view";
    $("modalAddBody").hidden = which !== "add";
  });
});

//  Reminders 
function renderReminders(list) {
  const ul = $("reminderList");
  ul.innerHTML = "";

  if (!list.length) {
    const li = document.createElement("li");
    li.className = "reminder-empty";
    li.textContent = "No reminders for today. Add some using the Add Reminder tab.";
    ul.appendChild(li);
  } else {
    list.forEach((r) => {
      const li = document.createElement("li");
      li.className = "reminder-item" + (r.done_today ? " done" : "");

      const emoji = document.createElement("span");
      emoji.className = "reminder-item-emoji";
      emoji.textContent = TYPE_EMOJI[r.type] || "🔔";

      const text = document.createElement("span");
      text.className = "reminder-item-text";
      text.innerHTML = `<span class="reminder-item-time">${r.time}</span> — ${r.label}` +
        (r.notes ? `<span class="reminder-item-notes">${r.notes}</span>` : "");

      li.appendChild(emoji);
      li.appendChild(text);

      if (r.done_today) {
        const done = document.createElement("span");
        done.className = "reminder-item-emoji";
        done.textContent = "✓";
        li.appendChild(done);
      } else {
        const btn = document.createElement("button");
        btn.className = "reminder-done-btn";
        btn.setAttribute("aria-label", `Mark ${r.label} done`);
        btn.textContent = "✓";
        btn.addEventListener("click", async () => {
          try {
            await api(`/reminders/${r.id}/done`, { method: "POST" });
            refreshReminders();
          } catch (e) { console.error(e); }
        });
        li.appendChild(btn);
      }

      ul.appendChild(li);
    });
  }

  // Update bell badge
  const doneCount = list.filter(r => r.done_today).length;
  const pending = list.length - doneCount;
  const badge = $("bellBadge");
  if (pending > 0) {
    badge.textContent = pending;
    badge.hidden = false;
  } else {
    badge.hidden = true;
  }
}

async function refreshReminders() {
  try {
    const list = await api("/reminders/today");
    renderReminders(list);
  } catch (e) { }
}

// Quick reminder buttons
document.querySelectorAll(".quick-btn").forEach(btn => {
  btn.addEventListener("click", async () => {
    const label = btn.dataset.label;
    const type = btn.dataset.type;
    const time = btn.dataset.time;
    const notes = btn.dataset.notes || "";
    try {
      await api("/reminders", {
        method: "POST",
        body: JSON.stringify({ label, type, time, notes }),
      });
      refreshReminders();

      $("tabView").click();
    } catch (e) {
      alert("Couldn't save the reminder. Please try again.");
    }
  });
});

// Add reminder form
$("reminderForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const label = $("rLabel").value.trim();
  const type = $("rType").value;
  const time = $("rTime").value;
  const notes = $("rNotes").value.trim();

  if (!label || !time) return;

  try {
    await api("/reminders", {
      method: "POST",
      body: JSON.stringify({ label, type, time, notes }),
    });
    $("reminderForm").reset();
    refreshReminders();
    $("tabView").click();
  } catch (err) {
    alert("Couldn't save the reminder. Please try again.");
  }
});

//  Photo modal 
const openPhotoBtn = $("openPhotoBtn");
if (openPhotoBtn) {
  openPhotoBtn.addEventListener("click", () => {
    $("photoModalBackdrop").hidden = false;
    closeSidebar();
  });
}

$("closePhotoModal").addEventListener("click", () => {
  $("photoModalBackdrop").hidden = true;
});

$("photoModalBackdrop").addEventListener("click", (e) => {
  if (e.target === $("photoModalBackdrop")) $("photoModalBackdrop").hidden = true;
});

$("photoCancelBtn").addEventListener("click", () => {
  $("photoModalBackdrop").hidden = true;
  $("photoFile").value = "";
  $("photoName").value = "";
});

$("photoSaveBtn").addEventListener("click", async () => {
  const file = $("photoFile").files[0];
  const name = $("photoName").value.trim();
  if (!file || !name) {
    alert("Please choose a photo and enter a name.");
    return;
  }
  const form = new FormData();
  form.append("name", name);
  form.append("file", file);
  try {
    await api("/photo", { method: "POST", body: form });
    $("photoModalBackdrop").hidden = true;
    $("photoFile").value = "";
    $("photoName").value = "";
    addMessage("assistant", `I'll remember ${name}'s photo now. 💛`);
  } catch (err) {
    // If backend not available, show confirmation anyway for demo
    $("photoModalBackdrop").hidden = true;
    $("photoFile").value = "";
    $("photoName").value = "";
    addMessage("assistant", `I've saved ${name}'s photo. 💛`);
  }
});

//  Session save 
$("saveSessionBtn").addEventListener("click", async () => {
  const btn = $("saveSessionBtn");
  const original = btn.textContent;

  // Save mood log server-side (non-blocking for the caregiver file below)
  try { await api("/session/save", { method: "POST" }); } catch (e) { /* still produce the file */ }

  const timestamp = new Date().toLocaleString();
  const chatMessages = [...document.querySelectorAll(".msg")].map(el => {
    const role = el.classList.contains("msg-user") ? "User" : "Companion";
    return `[${role}] ${el.textContent}`;
  }).join("\n");

  const notesText = sessionLog.length
    ? sessionLog.map(n => `[${n.time}] (${n.type}) ${n.note}`).join("\n")
    : "None flagged this session.";

  const sessionData =
    `EchoMemory Session — ${timestamp}\n${"=".repeat(50)}\n\n` +
    `THINGS FOR A CAREGIVER TO CHECK:\n${notesText}\n\n` +
    `${"=".repeat(50)}\nFULL CONVERSATION:\n${chatMessages}`;

  const blob = new Blob([sessionData], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `echomemory-session-${Date.now()}.txt`;
  a.click();
  URL.revokeObjectURL(url);

  btn.textContent = "Saved!";
  setTimeout(() => { btn.textContent = original; }, 2000);
});

//  Startup 
async function init() {
  loadSnoozed();
  try {
    const status = await api("/status");

    // Get patient name from status if available
    if (status.patient_name) {
      patientName = status.patient_name;
    }

    const loaded = status.memory_loaded;
    $("memoryStatus").textContent = loaded
      ? "Family records loaded"
      : "No family records found";

    // Greeting with patient name
    const greeting = patientName
      ? `Hello, ${patientName}! I am here to help you remember your family.`
      : `Hello! I am here to help you remember your family.`;
    addMessage("assistant", greeting);

  } catch (e) {
    $("memoryStatus").textContent = "Could not reach server";
    addMessage("assistant", "Hello! I am here to help you remember your family today.");
  }

  refreshReminders();
  refreshDueAlert();

  // Re-check for due reminders every minute
  setInterval(refreshDueAlert, 60000);
  setInterval(checkSnoozedReminders, 60000);
}

init();