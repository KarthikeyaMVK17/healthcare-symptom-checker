const resultEl = document.getElementById("result");
const sidebar = document.getElementById("sidebar");
const overlay = document.getElementById("overlay");
const historyList = document.getElementById("history-list");
const historyBtn = document.getElementById("history-btn");
const clearBtn = document.getElementById("clear-history-btn");
const themeToggle = document.getElementById("theme-toggle");

// 🌙 THEME TOGGLE
themeToggle.addEventListener("click", () => {
  document.body.classList.toggle("dark");
  const dark = document.body.classList.contains("dark");
  themeToggle.textContent = dark ? "☀️" : "🌙";
  localStorage.setItem("theme", dark ? "dark" : "light");
});
if (localStorage.getItem("theme") === "dark") {
  document.body.classList.add("dark");
  themeToggle.textContent = "☀️";
}

// 🕒 SIDEBAR TOGGLE
historyBtn.addEventListener("click", () => {
  sidebar.classList.toggle("show");
  overlay.style.display = sidebar.classList.contains("show") ? "block" : "none";
});
overlay.addEventListener("click", () => {
  sidebar.classList.remove("show");
  overlay.style.display = "none";
});

// 🧾 LOAD HISTORY
async function loadHistory() {
  try {
    const res = await fetch("http://127.0.0.1:8000/history");
    const data = await res.json();
    historyList.innerHTML = "";

    if (!data.history.length) {
      historyList.innerHTML = "<li>No previous queries</li>";
      return;
    }

    data.history.forEach((h) => {
      const li = document.createElement("li");
      li.textContent = h.symptoms.length > 50 ? h.symptoms.slice(0, 50) + "..." : h.symptoms;
      li.title = new Date(h.timestamp).toLocaleString();
      li.addEventListener("click", () => {
        loadResultById(h.query_id);
        sidebar.classList.remove("show");
        overlay.style.display = "none";
      });
      historyList.appendChild(li);
    });
  } catch {
    historyList.innerHTML = "<li>⚠️ Failed to load history</li>";
  }
}
loadHistory();

// 🧠 ANALYZE SYMPTOMS
document.getElementById("symptom-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const symptoms = document.getElementById("symptoms").value.trim();
  const age = document.getElementById("age").value || null;
  const pregnant = document.getElementById("pregnant").checked;
  const btn = document.getElementById("analyze-btn");

  btn.disabled = true;
  btn.textContent = "Analyzing...";
  resultEl.innerHTML = "<p class='loading'>⏳ Analyzing your symptoms...</p>";

  try {
    const response = await fetch("http://127.0.0.1:8000/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symptoms, age, pregnant }),
    });
    const data = await response.json();
    typeResult(data);
    loadHistory();
  } catch (err) {
    resultEl.innerHTML = `<p class='error'>❌ ${err.message}</p>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Analyze";
  }
});

// 🧾 LOAD SAVED RESULT
async function loadResultById(queryId) {
  try {
    const res = await fetch("http://127.0.0.1:8000/history");
    const data = await res.json();
    const record = data.history.find((r) => r.query_id === queryId);
    if (!record || !record.model_response) {
      resultEl.innerHTML = "<p class='error'>❌ No saved response found.</p>";
      return;
    }
    typeResult(record.model_response);
  } catch (err) {
    resultEl.innerHTML = `<p class='error'>❌ ${err.message}</p>`;
  }
}

// 🩹 TYPING EFFECT
function typeResult(data) {
  const html = buildResultHTML(data);
  resultEl.innerHTML = "";
  let i = 0;
  const speed = 8; // smaller = faster
  const tempDiv = document.createElement("div");

  const timer = setInterval(() => {
    tempDiv.innerHTML = html.slice(0, i++);
    resultEl.innerHTML = tempDiv.innerHTML;
    if (i >= html.length) clearInterval(timer);
  }, speed);
}

// 🩺 BUILD RESULT HTML
function buildResultHTML(data) {
  const escalation = data.escalation
    ? `<div class="alert ${data.escalation.level}">
        🚨 <b>${data.escalation.level.toUpperCase()}</b>: ${data.escalation.message}
      </div>`
    : "";

  const conditions = (data.probable_conditions || [])
    .map(
      (c) => `
      <div class="condition">
        <h3>${c.name}</h3>
        <div class="confidence-bar ${c.confidence?.toLowerCase()}"><div></div></div>
        <p><b>Confidence:</b> ${c.confidence}</p>
        <p>${c.rationale}</p>
      </div>`
    )
    .join("");

  const nextSteps = (data.next_steps || []).map((s) => `<li>${s}</li>`).join("");

  return `
    <div class="result-card">
      <p class="disclaimer">${data.disclaimer}</p>
      ${escalation}
      <h2>🩺 Probable Conditions</h2>
      ${conditions}
      <h2>🧭 Recommended Next Steps</h2>
      <ul>${nextSteps}</ul>
      <div class="meta">
        <small><b>Model:</b> ${data.metadata?.model || "local"}</small> |
        <small>${new Date(data.metadata?.timestamp || Date.now()).toLocaleString()}</small>
      </div>
    </div>`;
}

// 🧹 CLEAR HISTORY
clearBtn.addEventListener("click", async () => {
  if (!confirm("Are you sure you want to clear all history?")) return;
  try {
    const res = await fetch("http://127.0.0.1:8000/history/clear", {
      method: "DELETE",
    });
    const data = await res.json();
    alert(data.message || "History cleared!");
    loadHistory();
  } catch (err) {
    alert("❌ Failed to clear history");
    console.error(err);
  }
});
