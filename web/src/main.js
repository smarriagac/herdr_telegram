// Telegram Mini App Controller for Herdr Agent Bridge

const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
  if (tg.setHeaderColor) tg.setHeaderColor('#030712');
  if (tg.setBackgroundColor) tg.setBackgroundColor('#030712');
}

function haptic(type = 'light') {
  try {
    if (tg?.HapticFeedback) {
      tg.HapticFeedback.impactOccurred(type);
    }
  } catch (e) {
    // Ignore fallback outside Telegram
  }
}

// State
let agents = [];
let selectedAgent = null;
let activeTab = 'result';
let pollInterval = null;

// DOM Elements
const agentChipsEl = document.getElementById('agent-chips');
const agentCountEl = document.getElementById('agent-count');
const agentTitleEl = document.getElementById('agent-title');
const agentIconEl = document.getElementById('agent-icon');
const agentBackendBadgeEl = document.getElementById('agent-backend-badge');
const agentEngineEl = document.getElementById('agent-engine');
const agentStatusTextEl = document.getElementById('agent-status-text');
const agentStatusBadgeEl = document.getElementById('agent-status-badge');
const resultViewEl = document.getElementById('result-view');
const terminalViewEl = document.getElementById('terminal-view');
const promptInputEl = document.getElementById('prompt-input');

// Tabs
const tabBtnResult = document.getElementById('tab-btn-result');
const tabBtnTerminal = document.getElementById('tab-btn-terminal');
const tabBtnPrompt = document.getElementById('tab-btn-prompt');
const tabContentResult = document.getElementById('tab-content-result');
const tabContentTerminal = document.getElementById('tab-content-terminal');
const tabContentPrompt = document.getElementById('tab-content-prompt');

async function fetchAgents() {
  try {
    const res = await fetch('/api/agents');
    const data = await res.json();
    if (data.ok && Array.isArray(data.agents)) {
      agents = data.agents;
      agentCountEl.textContent = agents.length;
      renderChips();
      
      // Auto-select first or keep current
      if (!selectedAgent && agents.length > 0) {
        selectAgent(agents[0].id);
      } else if (selectedAgent) {
        const updated = agents.find(a => a.id === selectedAgent.id);
        if (updated) {
          selectedAgent = updated;
          updateActiveAgentHeader();
        }
      }
    }
  } catch (err) {
    console.error('Error fetching agents:', err);
  }
}

function renderChips() {
  agentChipsEl.innerHTML = '';
  if (agents.length === 0) {
    agentChipsEl.innerHTML = '<span class="text-xs text-gray-400 italic">No hay agentes activos</span>';
    return;
  }

  agents.forEach(agent => {
    const chip = document.createElement('button');
    const isSelected = selectedAgent && selectedAgent.id === agent.id;
    chip.className = `px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition active:scale-95 flex items-center space-x-1.5 shadow-sm ${
      isSelected
        ? 'bg-blue-600 text-white ring-2 ring-blue-500/50'
        : 'bg-gray-900 border border-gray-800 text-gray-300 hover:text-white'
    }`;

    chip.innerHTML = `
      <span>${agent.status_icon || '🤖'}</span>
      <span class="truncate max-w-[120px]">${agent.display_name}</span>
    `;

    chip.addEventListener('click', () => {
      haptic('light');
      selectAgent(agent.id);
    });

    agentChipsEl.appendChild(chip);
  });
}

function selectAgent(agentId) {
  selectedAgent = agents.find(a => a.id === agentId);
  if (!selectedAgent) return;

  renderChips();
  updateActiveAgentHeader();

  if (activeTab === 'result') {
    fetchResult();
  } else if (activeTab === 'terminal') {
    fetchTerminal();
  }
}

function updateActiveAgentHeader() {
  if (!selectedAgent) return;

  agentTitleEl.textContent = selectedAgent.display_name;
  agentIconEl.textContent = selectedAgent.status_icon || '🤖';
  agentBackendBadgeEl.textContent = (selectedAgent.backend || 'classic').toUpperCase();
  agentEngineEl.textContent = (selectedAgent.engine || 'agy').toUpperCase();
  agentStatusTextEl.textContent = selectedAgent.status_label || selectedAgent.status;

  // Status color styles
  const st = selectedAgent.status;
  if (st === 'working') {
    agentStatusBadgeEl.className = 'px-2.5 py-1 rounded-full text-xs font-semibold flex items-center space-x-1.5 bg-blue-950/70 text-blue-300 border border-blue-800/60 shadow-sm';
  } else if (st === 'idle' || st === 'done') {
    agentStatusBadgeEl.className = 'px-2.5 py-1 rounded-full text-xs font-semibold flex items-center space-x-1.5 bg-emerald-950/70 text-emerald-300 border border-emerald-800/60 shadow-sm';
  } else if (st === 'blocked') {
    agentStatusBadgeEl.className = 'px-2.5 py-1 rounded-full text-xs font-semibold flex items-center space-x-1.5 bg-amber-950/70 text-amber-300 border border-amber-800/60 shadow-sm';
  } else {
    agentStatusBadgeEl.className = 'px-2.5 py-1 rounded-full text-xs font-semibold flex items-center space-x-1.5 bg-gray-800 text-gray-300 border border-gray-700/60 shadow-sm';
  }
}

async function fetchResult() {
  if (!selectedAgent) return;
  resultViewEl.innerHTML = '<p class="text-gray-400 italic">Cargando resultado del agente...</p>';

  try {
    const res = await fetch(`/api/agents/${encodeURIComponent(selectedAgent.id)}/result`);
    const data = await res.json();
    if (data.ok) {
      resultViewEl.innerHTML = data.formatted_html || '<p class="text-gray-400 italic">Sin resultado disponible.</p>';
    } else {
      resultViewEl.innerHTML = `<p class="text-rose-400">Error: ${data.error}</p>`;
    }
  } catch (err) {
    resultViewEl.innerHTML = `<p class="text-rose-400">Error de conexión: ${err.message}</p>`;
  }
}

async function fetchTerminal() {
  if (!selectedAgent) return;

  try {
    const res = await fetch(`/api/agents/${encodeURIComponent(selectedAgent.id)}/terminal?lines=50`);
    const data = await res.json();
    if (data.ok) {
      terminalViewEl.textContent = data.output || 'Terminal sin salida reciente.';
      terminalViewEl.scrollTop = terminalViewEl.scrollHeight;
    } else {
      terminalViewEl.textContent = `Error: ${data.error}`;
    }
  } catch (err) {
    terminalViewEl.textContent = `Error de conexión: ${err.message}`;
  }
}

// Tab Switching
function setTab(tab) {
  activeTab = tab;
  haptic('light');

  const tabs = [
    { name: 'result', btn: tabBtnResult, pane: tabContentResult },
    { name: 'terminal', btn: tabBtnTerminal, pane: tabContentTerminal },
    { name: 'prompt', btn: tabBtnPrompt, pane: tabContentPrompt },
  ];

  tabs.forEach(t => {
    if (t.name === tab) {
      t.btn.className = 'tab-btn flex-1 py-1.5 rounded-md text-center transition bg-blue-600 text-white font-semibold';
      t.pane.classList.remove('hidden');
    } else {
      t.btn.className = 'tab-btn flex-1 py-1.5 rounded-md text-center text-gray-400 hover:text-white transition';
      t.pane.classList.add('hidden');
    }
  });

  if (tab === 'result') fetchResult();
  if (tab === 'terminal') fetchTerminal();
}

tabBtnResult.addEventListener('click', () => setTab('result'));
tabBtnTerminal.addEventListener('click', () => setTab('terminal'));
tabBtnPrompt.addEventListener('click', () => setTab('prompt'));
document.getElementById('btn-reload-terminal')?.addEventListener('click', () => {
  haptic('light');
  fetchTerminal();
});
document.getElementById('btn-refresh')?.addEventListener('click', () => {
  haptic('medium');
  fetchAgents();
});

// Quick Action Buttons
document.querySelectorAll('.quick-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    if (!selectedAgent) return;
    const action = btn.dataset.quick;
    haptic('medium');

    const prompts = {
      test: 'Ejecutá los tests del proyecto y reportá el resultado.',
      diff: 'Mostrame el git diff y estado actual del repositorio.',
      push: 'Hacé commit con conventional commits de los cambios pendientes y hacé push.',
    };

    const text = prompts[action];
    if (text) {
      btn.classList.add('opacity-50');
      try {
        await fetch(`/api/agents/${encodeURIComponent(selectedAgent.id)}/prompt`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: text }),
        });
        setTab('terminal');
      } finally {
        btn.classList.remove('opacity-50');
      }
    }
  });
});

// Key Control Buttons (Enter / Esc)
document.querySelectorAll('.key-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    if (!selectedAgent) return;
    const key = btn.dataset.key;
    haptic('heavy');

    btn.classList.add('opacity-50');
    try {
      await fetch(`/api/agents/${encodeURIComponent(selectedAgent.id)}/keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key }),
      });
      fetchTerminal();
    } finally {
      btn.classList.remove('opacity-50');
    }
  });
});

// Send Prompt
document.getElementById('btn-send-prompt').addEventListener('click', async () => {
  if (!selectedAgent) return;
  const promptText = promptInputEl.value.trim();
  if (!promptText) return;

  haptic('medium');
  const btn = document.getElementById('btn-send-prompt');
  btn.disabled = true;
  btn.textContent = 'Enviando...';

  try {
    const res = await fetch(`/api/agents/${encodeURIComponent(selectedAgent.id)}/prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: promptText }),
    });
    const data = await res.json();
    if (data.ok) {
      promptInputEl.value = '';
      setTab('terminal');
    } else {
      alert(`Error enviando orden: ${data.error}`);
    }
  } catch (err) {
    alert(`Error de red: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = '🚀 Enviar Orden';
  }
});

// Initial boot
fetchAgents();
pollInterval = setInterval(fetchAgents, 3000);
