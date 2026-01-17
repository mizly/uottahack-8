import { sendJson } from './network.js';
import { processTransaction, connectWallet, getUserWallet } from './wallet.js';

// DOM Elements
export const videoFeed = document.getElementById('video-feed');
export const videoOverlay = document.getElementById('video-overlay');
export const connectionStatus = document.getElementById('connection-status');
const timerDisplay = document.getElementById('timer-display');
const scoreDisplay = document.getElementById('score-display');
const leaderboardBody = document.getElementById('leaderboard-body');
const startPanel = document.getElementById('start-panel');
const gameActivePanel = document.getElementById('game-active-panel');
const playerNameInput = document.getElementById('player-name');
const queueInfo = document.getElementById('queue-info');
const queueCount = document.getElementById('queue-count');
const queueNames = document.getElementById('queue-names');
const joinBtn = document.getElementById('join-btn');
const cancelBtn = document.getElementById('cancel-btn');
const statusDisplay = document.getElementById('status-display');
const playerStatus = document.getElementById('player-status');
const currentPilotName = document.getElementById('current-pilot-name');
const stopBtn = document.getElementById('stop-btn');
const simControls = document.getElementById('sim-controls');

// State
let myName = "";
let isMyTurn = false;
let wasActive = false;
export let currentMode = 'casual';
export let selectedLoadout = { id: 'vanguard', name: 'Vanguard' };
let confirmationTimerInterval = null;

export function getIsMyTurn() {
    return isMyTurn;
}

export function setConnectionState(connected) {
    if (connected) {
        connectionStatus.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-ios-green shadow-[0_0_8px_rgba(48,209,88,0.6)]"></span><span class="text-ios-green">Online</span>';
    } else {
        connectionStatus.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-ios-red animate-pulse"></span><span>Offline</span>';
    }
}

export function updateGameState(state) {
    // Timer & Score
    if (timerDisplay) timerDisplay.textContent = state.time_left;
    if (scoreDisplay) scoreDisplay.textContent = state.score;
    if (currentPilotName) currentPilotName.textContent = state.player || "None";

    // Check if game just ended
    if (wasActive && !state.active) {
        if (state.player === myName) {
            console.log("Game Ended. Refreshing balance...");
            setTimeout(async () => {
                const { refreshBalance } = await import('./wallet.js');
                refreshBalance();
            }, 2000);
        }
    }
    wasActive = state.active;

    // Check if it's MY turn
    isMyTurn = (state.active && state.player === myName);

    // Update Player Status UI
    if (statusDisplay) statusDisplay.classList.remove('hidden');
    if (isMyTurn) {
        playerStatus.textContent = "PILOTING";
        playerStatus.className = "text-[10px] font-bold tracking-wide uppercase text-ios-green bg-ios-green/10 px-2 py-0.5 rounded-full";
        // Show Abort & Sim Controls
        stopBtn.classList.remove('hidden');
        if (simControls) simControls.classList.remove('hidden');
    } else {
        // Am I in queue?
        const position = state.queue.indexOf(myName);
        if (position !== -1) {
            playerStatus.textContent = `QUEUE #${position + 1}`;
            playerStatus.className = "text-[10px] font-bold tracking-wide uppercase text-ios-yellow bg-ios-yellow/10 px-2 py-0.5 rounded-full";
        } else {
            playerStatus.textContent = "SPECTATING";
            playerStatus.className = "text-[10px] font-bold tracking-wide uppercase text-white/50 bg-white/10 px-2 py-0.5 rounded-full";
        }
        // Hide control buttons
        stopBtn.classList.add('hidden');
        if (simControls) simControls.classList.add('hidden');
    }

    // Game Mode UI
    if (state.queue.includes(myName)) {
        joinBtn.classList.add('hidden');
        cancelBtn.classList.remove('hidden');
        if (playerNameInput) playerNameInput.disabled = true;
    } else {
        joinBtn.classList.remove('hidden');
        cancelBtn.classList.add('hidden');
        if (playerNameInput) playerNameInput.disabled = false;
    }

    if (state.active) {
        if (gameActivePanel) gameActivePanel.classList.remove('hidden');
        if (startPanel) {
            if (isMyTurn) {
                startPanel.classList.add('hidden');
                if (playerNameInput) playerNameInput.disabled = true;
            } else {
                startPanel.classList.remove('hidden');
            }
        }
    } else {
        if (startPanel) startPanel.classList.remove('hidden');
        if (gameActivePanel) gameActivePanel.classList.add('hidden');
    }

    // Update Queue Info
    if (state.queue.length > 0) {
        if (queueInfo) queueInfo.classList.remove('hidden');
        if (queueCount) queueCount.textContent = state.queue.length;
        if (queueNames) queueNames.textContent = state.queue.slice(0, 3).join(', ') + (state.queue.length > 3 ? '...' : '');
    } else {
        if (queueInfo) queueInfo.classList.add('hidden');
    }

    renderLeaderboard(state.leaderboard);
}

function renderLeaderboard(data) {
    if (!leaderboardBody) return;
    if (!data || data.length === 0) {
        leaderboardBody.innerHTML = '<tr class="text-gray-500 italic"><td colspan="3" class="py-4 text-center">No records yet</td></tr>';
        return;
    }

    leaderboardBody.innerHTML = data.map((entry, index) => {
        const className = entry.class || 'Vanguard';
        let icon = '🛡️';
        let styleClass = 'text-blue-400 bg-blue-500/10 border-blue-500/20';

        if (className === 'Interceptor') {
            icon = '⚡';
            styleClass = 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20';
        } else if (className === 'Juggernaut') {
            icon = '🦍';
            styleClass = 'text-red-400 bg-red-500/10 border-red-500/20';
        }

        return `
        <tr class="hover:bg-white/5 transition-colors border-b border-white/5 last:border-0">
            <td class="py-3 pl-3 text-white/30 font-mono text-xs w-8">${String(index + 1).padStart(2, '0')}</td>
            <td class="py-3 text-white/80 font-medium text-sm">${entry.name}</td>
            <td class="py-3 text-right">
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[10px] font-medium uppercase tracking-wider ${styleClass}">
                    <span class="text-xs">${icon}</span>
                    <span class="hidden sm:inline">${className}</span>
                </span>
            </td>
            <td class="py-3 pr-3 text-right text-ios-blue font-semibold text-sm w-16">${entry.score}</td>
        </tr>
    `}).join('');
}

// ----- EXPOSED UI ACTIONS -----

export function setMode(mode) {
    currentMode = mode;
    console.log("Mode set to:", mode);

    const casualBtn = document.getElementById('mode-casual');
    const rankedBtn = document.getElementById('mode-ranked');
    const rankedInfo = document.getElementById('ranked-info');
    const deployBtn = document.getElementById('deploy-btn') || document.querySelector('button[onclick="confirmLoadout()"]');

    if (mode === 'casual') {
        casualBtn.className = "px-6 py-2 rounded-full text-sm font-medium transition-all bg-ios-blue text-white shadow-lg";
        rankedBtn.className = "px-6 py-2 rounded-full text-sm font-medium transition-all text-white/50 hover:text-white";
        rankedInfo.classList.add('hidden');
        if (deployBtn) deployBtn.innerHTML = "DEPLOY UNIT";
    } else {
        rankedBtn.className = "px-6 py-2 rounded-full text-sm font-medium transition-all bg-ios-yellow text-black shadow-lg shadow-ios-yellow/20";
        casualBtn.className = "px-6 py-2 rounded-full text-sm font-medium transition-all text-white/50 hover:text-white";
        rankedInfo.classList.remove('hidden');
        if (deployBtn) deployBtn.innerHTML = `PAY 0.1 SOL & DEPLOY`;
    }
}

export function requestLoadout() {
    myName = playerNameInput.value || "Anonymous";
    if (!myName) {
        alert("Please enter a name first.");
        return;
    }
    sendJson({ action: "join_queue", name: myName });
}

export function cancelQueue() {
    sendJson({ action: "leave_queue" });
}

export function stopGame() {
    sendJson({ action: "stop_game" });
}

export function addScore(points) {
    sendJson({ action: "add_score", score: points });
}

export function selectTank(id) {
    document.querySelectorAll('.tank-card').forEach(card => {
        card.classList.remove('selected');
        const icon = card.querySelector('.check-icon');
        if (icon) icon.classList.add('opacity-0');
    });

    const selectedCard = document.getElementById(`tank-${id}`);
    if (selectedCard) {
        selectedCard.classList.add('selected');
        const icon = selectedCard.querySelector('.check-icon');
        if (icon) icon.classList.remove('opacity-0');
    }

    let name = "Vanguard";
    if (id === 'interceptor') name = "Interceptor";
    if (id === 'juggernaut') name = "Juggernaut";
    selectedLoadout = { id, name };
}

export function handleMatchFound(timeoutSeconds) {
    const modal = document.getElementById('loadout-modal');
    const timerElem = document.getElementById('loadout-timer');

    // Reset Button State
    const deployBtn = document.getElementById('deploy-btn');
    if (deployBtn) {
        deployBtn.disabled = false;
        deployBtn.innerText = currentMode === 'ranked' ? "PAY 0.1 SOL & DEPLOY" : "DEPLOY UNIT";
    }

    modal.classList.add('active');

    let timeLeft = timeoutSeconds;
    timerElem.textContent = timeLeft;

    if (confirmationTimerInterval) clearInterval(confirmationTimerInterval);

    confirmationTimerInterval = setInterval(() => {
        timeLeft--;
        timerElem.textContent = timeLeft;
        if (timeLeft <= 0) {
            clearInterval(confirmationTimerInterval);
            closeLoadout();
        }
    }, 1000);
}

export function closeLoadout() {
    const modal = document.getElementById('loadout-modal');
    if (modal) {
        modal.classList.remove('active');
    }
    if (confirmationTimerInterval) clearInterval(confirmationTimerInterval);
}
window.closeLoadout = closeLoadout;

// Wrapper for wallet confirm to pass current mode
// Main Loadout Confirmation Logic
export async function confirmLoadoutWrapper() {
    console.log("Confirming loadout for mode:", currentMode);

    if (currentMode === 'ranked') {
        const wallet = getUserWallet();
        if (!wallet) {
            alert("Please connect your wallet first!");
            connectWallet();
            return;
        }

        const button = document.getElementById('deploy-btn');
        let originalText = "DEPLOY UNIT";

        if (button) {
            originalText = button.innerText;
            button.disabled = true;
            button.innerText = "Processing Transaction...";
        }

        try {
            // Process Payment
            const signature = await processTransaction();

            if (button) button.innerText = "Verifying...";

            closeLoadout();

            // Join Queue with Signature
            sendJson({
                action: "confirm_match",
                loadout: selectedLoadout,
                mode: 'ranked',
                signature: signature,
                publicKey: wallet.toString()
            });

        } catch (err) {
            console.error("Deploy failed", err);
            alert("Deployment Failed: " + err.message);
            if (button) {
                button.disabled = false;
                button.innerText = originalText;
            }
        }
    } else {
        // Casual Mode
        closeLoadout();
        sendJson({
            action: "confirm_match",
            loadout: selectedLoadout,
            mode: 'casual'
        });
    }
}

export function showGameOver(stats) {
    const modal = document.getElementById('game-over-modal');
    document.getElementById('go-score').textContent = stats.score;
    document.getElementById('go-distance').textContent = stats.distance;
    document.getElementById('go-shots').textContent = stats.shots;
    document.getElementById('go-enemies').textContent = stats.enemies;

    modal.style.visibility = 'visible';
    modal.style.opacity = '1';
    modal.style.pointerEvents = 'auto';
    modal.style.transform = 'scale(1)';
}

export function closeGameOver() {
    const modal = document.getElementById('game-over-modal');
    modal.style.opacity = '0';
    modal.style.pointerEvents = 'none';
    modal.style.transform = 'scale(0.95)';
    setTimeout(() => {
        modal.style.visibility = 'hidden';
    }, 400);
}
export function abortLoadout() {
    console.log("User aborted loadout selection.");
    cancelQueue();
    closeLoadout();
}
window.abortLoadout = abortLoadout;

// Initialize UI Listeners
(function initListeners() {
    const modal = document.getElementById('loadout-modal');
    if (modal) {
        // Backdrop click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                abortLoadout();
            }
        });

        // Close button click (first button in modal)
        const closeBtn = modal.querySelector('button');
        if (closeBtn) {
            closeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                abortLoadout();
            });
        }
    }
})();
