const startBotButton = document.getElementById("start-bot");
const stopBotButton = document.getElementById("stop-bot");
const clearLogsButton = document.getElementById("clear-logs");
const logsDiv = document.getElementById("logs");
const statsDiv = document.getElementById("stats");

let autoRefreshInterval = null;

// Start the bot
startBotButton.addEventListener("click", async () => {
  const startTime = document.getElementById("start-time").value;
  const interval = document.getElementById("interval").value;

  try {
    startBotButton.disabled = true;
    const response = await fetch("/start-bot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        start_time: startTime, 
        interval: parseInt(interval) 
      }),
    });
    const data = await response.json();
    
    if (data.status === "success") {
      stopBotButton.disabled = false;
      appendLog(`[INFO] ${data.message}`, false);
      // Initiate auto-refresh if not already started
      if (!autoRefreshInterval) {
        autoRefreshInterval = setInterval(updateDashboard, 4000);
      }
    } else {
      appendLog(`[ERROR] ${data.message}`, true);
    }
  } catch (error) {
    appendLog("[ERROR] Could not start the bot: " + error.message, true);
  } finally {
    startBotButton.disabled = false;
  }
});

// Stop the bot
stopBotButton.addEventListener("click", async () => {
  try {
    stopBotButton.disabled = true;
    const response = await fetch("/stop-bot", { method: "POST" });
    const data = await response.json();
    
    if (data.status === "success") {
      startBotButton.disabled = false;
      appendLog(`[INFO] ${data.message}`, false);
    } else {
      appendLog(`[ERROR] ${data.message}`, true);
    }
  } catch (error) {
    appendLog("[ERROR] Could not stop the bot: " + error.message, true);
  } finally {
    stopBotButton.disabled = false;
  }
});

// Clear logs
clearLogsButton.addEventListener("click", () => {
  logsDiv.innerHTML = "";
});

// Fetch logs and stats periodically
async function updateDashboard() {
  await updateLogs();
  await updateStats();
}

// Update logs from server
async function updateLogs() {
  try {
    const logsResponse = await fetch("/logs");
    const logsData = await logsResponse.json();
    if (logsData.status === "success") {
      renderLogs(logsData.logs);
    }
  } catch (error) {
    console.error("Error fetching logs:", error);
  }
}

// Update stats from server
async function updateStats() {
  try {
    const statsResponse = await fetch("/stats");
    const statsData = await statsResponse.json();
    if (statsData.status === "success") {
      renderStats(statsData.stats);
    } else {
      statsDiv.innerHTML = `<p>${statsData.message}</p>`;
    }
  } catch (error) {
    console.error("Error fetching stats:", error);
  }
}

// Render logs with color coding
function renderLogs(logLines) {
  logsDiv.innerHTML = logLines
    .map(line => parseLogLine(line))
    .join("");

  // Auto-scroll to bottom
  logsDiv.scrollTop = logsDiv.scrollHeight;
}

// Color-code a single log line
function parseLogLine(line) {
  let cssClass = "log-info";
  if (line.includes("[ERROR]")) cssClass = "log-error";
  else if (line.includes("[WARN]")) cssClass = "log-warn";
  
  return `<div class="${cssClass}">${line}</div>`;
}

// Append a single log line to logsDiv
function appendLog(line, isError) {
  const cssClass = isError ? "log-error" : "log-info";
  const div = document.createElement("div");
  div.className = cssClass;
  div.textContent = line;
  logsDiv.appendChild(div);
  logsDiv.scrollTop = logsDiv.scrollHeight;
}

// Render stats
function renderStats(stats) {
  statsDiv.innerHTML = `
    <p><strong>Total Attempts:</strong> ${stats.total_attempts}</p>
    <p><strong>Successful:</strong> ${stats.successful_publishes}</p>
    <p><strong>Failed:</strong> ${stats.failed_publishes}</p>
    <p><strong>Success Rate:</strong> ${stats.success_rate.toFixed(1)}%</p>
    <p><strong>Running Time:</strong> ${stats.running_time}</p>
  `;
}

// Start periodic refresh immediately on page load (optional)
document.addEventListener("DOMContentLoaded", () => {
  autoRefreshInterval = setInterval(updateDashboard, 4000);
});