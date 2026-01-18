import { sendJson } from './network.js?v=2';
import { processTransaction, connectWallet, getUserWallet } from './wallet.js';
import { initHUD, updateHUD } from './hud.js?v=16';
import { controllerState } from './input.js?v=14';

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
export let selectedLoadout = { id: 'vanguard', name: 'Big Gurt' };
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

// Audio Logic
const customNotificationSound = new Audio('/static/audio/notification.mp3');
const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

function playNotificationSound() {
    // Try playing the custom file first
    const playPromise = customNotificationSound.play();

    if (playPromise !== undefined) {
        playPromise.catch(error => {
            console.log("Custom audio file not found or failed, using synth fallback.");
            playSynthBeep();
        });
    }
}

function playSynthBeep() {
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();

    oscillator.type = 'sine';
    oscillator.frequency.setValueAtTime(880, audioCtx.currentTime); // A5
    oscillator.frequency.exponentialRampToValueAtTime(440, audioCtx.currentTime + 0.5); // Drop to A4

    gainNode.gain.setValueAtTime(0.5, audioCtx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.5);

    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);

    oscillator.start();
    oscillator.stop(audioCtx.currentTime + 0.5);
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
        // Clear Title
        document.title = "gurt.tech";
    } else {
        // Am I in queue?
        const position = state.queue.indexOf(myName);
        const queueModal = document.getElementById('queue-modal');
        const loadoutModal = document.getElementById('loadout-modal');
        const isConfirming = loadoutModal && loadoutModal.classList.contains('active');

        if (position !== -1) {
            playerStatus.textContent = `LINED UP #${position + 1}`;
            playerStatus.className = "text-[10px] font-bold tracking-wide uppercase text-ios-yellow bg-ios-yellow/10 px-2 py-0.5 rounded-full";

            // ETA Calculation: (Position) * 60s + Time Left
            let etaSeconds = (position * 60);
            if (state.active) etaSeconds += state.time_left;
            else etaSeconds += 60; // Next game start buffer

            // Formatting
            const mins = Math.floor(etaSeconds / 60);
            const secs = etaSeconds % 60;
            const etaString = `${mins}:${secs.toString().padStart(2, '0')}`;

            // Only update title/modal if we are NOT in the confirmation phase
            if (!isConfirming) {
                document.title = `(${etaString}) Gurt Waiting...`;

                // Show Modal IF not already in match confirmation and newly joined (implied by existence in queue but no match found yet)
                // Logic: If I am in queue, and not confirming (handled by handleMatchFound closing this), show it.
                // But we don't want it to pop up if we just closed it manually? 
                // The user said "if you start up a game... show a modal".
                // Let's control it via class.

                // Show Modal IF not already in match confirmation and newly joined
                // Use explicit check for dismissal flag
                const isDismissed = localStorage.getItem('queue_modal_dismissed') === 'true';

                if (queueModal && queueModal.classList.contains('hidden') && !isDismissed) {
                    if (position > 0 || (position === 0 && state.active)) {
                        queueModal.classList.remove('hidden');
                    }
                }

                // Update ETA text in modal
                const etaDisplay = document.getElementById('queue-eta');
                if (etaDisplay) etaDisplay.textContent = etaString;
            }
            // NOTE: If isConfirming, we do NOTHING to title here, letting handleMatchFound control it.

        } else {
            playerStatus.textContent = "SPECTATING";
            playerStatus.className = "text-[10px] font-bold tracking-wide uppercase text-white/50 bg-white/10 px-2 py-0.5 rounded-full";
            // Hide Queue Modal if not in queue
            if (queueModal) queueModal.classList.add('hidden');
            if (!isConfirming) document.title = "GURT // Ground Unit Response Tank";
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

    // Update HUD
    const hudOverlay = document.getElementById('hud-overlay');
    const enemyPanel = document.getElementById('hud-enemy-panel');
    if (hudOverlay) {
        if (state.active) {
            hudOverlay.classList.remove('opacity-0');
            if (enemyPanel) enemyPanel.classList.remove('opacity-0');
            updateHUD(state, controllerState);
        } else {
            hudOverlay.classList.add('opacity-0');
            if (enemyPanel) enemyPanel.classList.add('opacity-0');
        }
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

export function updatePingDisplay(latency) {
    const pingEl = document.getElementById('hud-ping');
    if (pingEl) {
        const val = pingEl.querySelector('.value');
        if (!val) return;

        if (latency === null || latency === undefined) {
            val.textContent = "NA";
            val.className = "value font-mono text-xl tracking-widest text-white/20";
            return;
        }

        const value = Math.round(Math.max(0, latency));
        val.textContent = `${value}ms`;

        // Color Logic
        let colorClass = 'text-ios-green';
        if (value >= 100 && value < 200) {
            colorClass = 'text-ios-yellow';
        } else if (value >= 200) {
            colorClass = 'text-ios-red';
        }

        val.className = `value font-mono text-xl tracking-widest ${colorClass}`;
    }
}

function renderLeaderboard(data) {
    if (!leaderboardBody) return;
    if (!data || data.length === 0) {
        leaderboardBody.innerHTML = '<tr class="text-white/10 italic"><td colspan="3" class="py-8 text-center text-[10px] tracking-[0.3em] uppercase font-black">No gurts found</td></tr>';
        return;
    }

    leaderboardBody.innerHTML = data.map((entry, index) => {
        const rawClass = entry.class || 'vanguard';
        const className = rawClass.toLowerCase();
        let icon = '🛡️';
        let styleClass = 'text-blue-400 bg-blue-500/10 border-blue-500/20';

        if (className === 'interceptor') {
            icon = '⚡';
            styleClass = 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20';
        } else if (className === 'juggernaut') {
            icon = '🦍';
            styleClass = 'text-red-400 bg-red-500/10 border-red-500/20';
        }

        const names = { 'vanguard': 'BIG GURT', 'interceptor': 'FAST GURT', 'juggernaut': 'ANGRY GURT' };
        const displayName = names[className] || 'GURT';

        return `
        <tr class="hover:bg-white/5 transition-colors border-b border-white/5 last:border-0">
            <td class="py-3 pl-3 text-white/30 font-mono text-xs w-8">${String(index + 1).padStart(2, '0')}</td>
            <td class="py-3 text-white/80 font-medium text-sm">${entry.name}</td>
            <td class="py-3 text-right">
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[10px] font-medium uppercase tracking-wider ${styleClass}">
                    <span class="text-xs">${icon}</span>
                    <span class="hidden sm:inline">${displayName}</span>
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

    // Unlock Audio Context on user interaction (resume context)
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
    // Try to unlock custom sound (play/pause) to allow it later
    customNotificationSound.play().then(() => {
        customNotificationSound.pause();
        customNotificationSound.currentTime = 0;
    }).catch(() => { }); // Ignore initial failure if file missing

    // Explicitly un-dismiss modal on new request
    localStorage.removeItem('queue_modal_dismissed');
    sendJson({ action: "join_queue", name: myName });
}

export function cancelQueue() {
    sendJson({ action: "leave_queue" });
}

export function dismissQueueModal() {
    const modal = document.getElementById('queue-modal');
    if (modal) {
        modal.classList.add('hidden');
        localStorage.setItem('queue_modal_dismissed', 'true');
    }
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

    const names = { 'vanguard': 'Big Gurt', 'interceptor': 'Fast Gurt', 'juggernaut': 'Angry Gurt' };
    selectedLoadout = { id, name: names[id] };
}

export function handleMatchFound(timeoutSeconds) {
    const modal = document.getElementById('loadout-modal');
    const timerElem = document.getElementById('loadout-timer');
    const queueModal = document.getElementById('queue-modal');

    // Hide Queue Modal
    if (queueModal) queueModal.classList.add('hidden');

    // Play Sound
    try {
        playNotificationSound();
    } catch (e) { console.warn("Audio play failed", e); }

    // Update Title
    document.title = "GURT ALERT!";

    // Reset Button State
    const deployBtn = document.getElementById('deploy-btn');
    if (deployBtn) {
        deployBtn.disabled = false;
        deployBtn.innerText = currentMode === 'ranked' ? "PAY 0.1 SOL & GURT" : "GURT DEPLOY";
    }

    if (modal) modal.classList.add('active');

    let timeLeft = timeoutSeconds;
    if (timerElem) timerElem.textContent = timeLeft;

    if (confirmationTimerInterval) clearInterval(confirmationTimerInterval);

    confirmationTimerInterval = setInterval(() => {
        timeLeft--;
        if (timerElem) timerElem.textContent = timeLeft;
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
        let originalText = "GURT DEPLOY";

        if (button) {
            originalText = button.innerText;
            button.disabled = true;
            button.innerText = "Taking your money...";
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
    initHUD();
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
