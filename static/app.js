const videoFeed = document.getElementById('video-feed');
const connectionStatus = document.getElementById('connection-status');
const timerDisplay = document.getElementById('timer-display');
const scoreDisplay = document.getElementById('score-display');
const leaderboardBody = document.getElementById('leaderboard-body');
const startPanel = document.getElementById('start-panel');
const gameActivePanel = document.getElementById('game-active-panel');
const playerNameInput = document.getElementById('player-name');

const wsUrl = `ws://${window.location.host}/ws/client`;
let socket = null;

// Controller State: 6 Analog, 2 Button Bytes (16 bits)
const controllerState = new Uint8Array(8);
for (let i = 0; i < 4; i++) controllerState[i] = 127;
controllerState[4] = 0;
controllerState[5] = 0;
controllerState[6] = 0;
controllerState[7] = 0;

// Landing Screen Logic
const enterBtn = document.getElementById('enter-btn');
if (enterBtn) {
    enterBtn.addEventListener('click', () => {
        const landingScreen = document.getElementById('landing-screen');
        const appContent = document.getElementById('app-content');

        // Animate out
        landingScreen.classList.add('hidden-screen');

        // Wait for animation slightly then show app
        setTimeout(() => {
            appContent.classList.add('active');

            // Trigger entry animations for children if needed, or rely on CSS cascade
            const animatedElements = document.querySelectorAll('.animate-fade-in');
            animatedElements.forEach((el, index) => {
                el.style.animationDelay = `${index * 0.1}s`;
                el.style.animationPlayState = 'running';
            });
        }, 500);
    });
}


// Keyboard State Tracking
const keys = {
    w: false, s: false, a: false, d: false,
    ArrowUp: false, ArrowDown: false, ArrowLeft: false, ArrowRight: false,
    Space: false, Shift: false,
    '1': false, '2': false, '3': false, '4': false, '5': false,
    '6': false, '7': false, '8': false, '9': false, '0': false
};

function connect() {
    socket = new WebSocket(wsUrl);
    // Important: Do NOT set binaryType = "blob" globally if we want to easily distinguish text frames.
    // However, binaryType = "blob" is standard for mixed content usually, 
    // but default "blob" makes text frames arrive as strings? No, "blob" makes EVERYTHING blobs if not specified? 
    // Actually, WebSocket default is 'blob' usually. Let's handle 'message' event carefully.
    // Wait, if binaryType is 'blob', text frames are still strings? 
    // Correction: In JS WebSocket, if binaryType is 'blob', binary frames are Blobs, text frames are strings.
    // So we can check typeof data.

    socket.onopen = () => {
        setConnectionState(true);
        requestAnimationFrame(updateLoop);
    };

    socket.onmessage = (event) => {
        if (typeof event.data === 'string') {
            // JSON Game State Update
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'game_state') {
                    updateGameState(data);
                }
            } catch (e) {
                console.error("Failed to parse JSON", e);
            }
        } else if (event.data instanceof Blob) {
            // Video Frame
            const url = URL.createObjectURL(event.data);
            videoFeed.onload = () => URL.revokeObjectURL(url);
            videoFeed.src = url;
        }
    };

    socket.onclose = () => {
        setConnectionState(false);
        setTimeout(connect, 2000);
    };

    socket.onerror = (err) => {
        console.error("Socket error", err);
        socket.close();
    }
}

function setConnectionState(connected) {
    if (connected) {
        connectionStatus.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-ios-green shadow-[0_0_8px_rgba(48,209,88,0.6)]"></span><span class="text-ios-green">Online</span>';
    } else {
        connectionStatus.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-ios-red animate-pulse"></span><span>Offline</span>';
    }
}

// Queue UI Elements
const queueInfo = document.getElementById('queue-info');
const queueCount = document.getElementById('queue-count');
const queueNames = document.getElementById('queue-names');
const joinBtn = document.getElementById('join-btn');
const statusDisplay = document.getElementById('status-display');
const playerStatus = document.getElementById('player-status');
const currentPilotName = document.getElementById('current-pilot-name');
const stopBtn = document.getElementById('stop-btn');
const simControls = document.getElementById('sim-controls'); // Debug controls

let myName = "";
let isMyTurn = false;

// ... (socket connection logic same as before, updateGameState changes)

function updateGameState(state) {
    // Timer & Score
    timerDisplay.textContent = state.time_left;
    scoreDisplay.textContent = state.score;
    currentPilotName.textContent = state.player || "None"; // Who is playing?

    // Check if it's MY turn
    isMyTurn = (state.active && state.player === myName);

    // Update Player Status UI
    statusDisplay.classList.remove('hidden');
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
    // Game Mode UI
    // Always update button state based on queue presence
    if (state.queue.includes(myName)) {
        joinBtn.textContent = "Standby...";
        joinBtn.disabled = true;
        joinBtn.classList.add('opacity-50', 'cursor-not-allowed');
        playerNameInput.disabled = true;
    } else {
        joinBtn.textContent = "Initialize Uplink";
        joinBtn.disabled = false;
        joinBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        playerNameInput.disabled = false;
    }

    if (state.active) {
        gameActivePanel.classList.remove('hidden');

        // Show start panel (join queue) unless we are currently playing
        if (isMyTurn) {
            startPanel.classList.add('hidden');
            playerNameInput.disabled = true;
        } else {
            startPanel.classList.remove('hidden');
        }
    } else {
        // Waiting Lobby
        startPanel.classList.remove('hidden');
        gameActivePanel.classList.add('hidden');
    }

    // Update Queue Info
    if (state.queue.length > 0) {
        queueInfo.classList.remove('hidden');
        queueCount.textContent = state.queue.length;
        // Show first 3 names
        queueNames.textContent = state.queue.slice(0, 3).join(', ') + (state.queue.length > 3 ? '...' : '');
    } else {
        queueInfo.classList.add('hidden');
    }

    // Leaderboard
    renderLeaderboard(state.leaderboard);
}

function renderLeaderboard(data) {
    if (!data || data.length === 0) {
        leaderboardBody.innerHTML = '<tr class="text-gray-500 italic"><td colspan="3" class="py-4 text-center">No records yet</td></tr>';
        return;
    }

    leaderboardBody.innerHTML = data.map((entry, index) => `
        <tr class="hover:bg-white/5 transition-colors border-b border-white/5 last:border-0">
            <td class="py-3 pl-3 text-white/30 font-mono text-xs w-8">${String(index + 1).padStart(2, '0')}</td>
            <td class="py-3 text-white/80 font-medium text-sm">${entry.name}</td>
            <td class="py-3 pr-3 text-right text-ios-blue font-semibold text-sm">${entry.score}</td>
        </tr>
    `).join('');
}

// ----- LOADOUT LOGIC -----
let selectedLoadout = { id: 'vanguard', name: 'Vanguard' };

window.requestLoadout = () => {
    myName = playerNameInput.value || "Anonymous";
    if (!myName) {
        alert("Please enter a name first.");
        return;
    }
    // Open Modal
    const modal = document.getElementById('loadout-modal');
    modal.classList.add('active');
};

window.closeLoadout = () => {
    const modal = document.getElementById('loadout-modal');
    modal.classList.remove('active');
};

window.selectTank = (id) => {
    // UI Update
    document.querySelectorAll('.tank-card').forEach(card => {
        card.classList.remove('selected');
        // card.querySelector('.check-icon').classList.add('opacity-0'); // Simply toggle class on parent logic
        const icon = card.querySelector('.check-icon');
        if (icon) icon.classList.add('opacity-0');
    });

    const selectedCard = document.getElementById(`tank-${id}`);
    if (selectedCard) {
        selectedCard.classList.add('selected');
        const icon = selectedCard.querySelector('.check-icon');
        if (icon) icon.classList.remove('opacity-0');
    }

    // Data Update
    let name = "Vanguard";
    if (id === 'interceptor') name = "Interceptor";
    if (id === 'juggernaut') name = "Juggernaut";

    selectedLoadout = { id, name };
};

window.confirmLoadout = () => {
    closeLoadout();
    // Send join request with loadout
    sendJson({
        action: "join_queue",
        name: myName,
        loadout: selectedLoadout
    });
};

// Deprecated direct join, kept for legacy or quick-start if needed
window.joinQueue = () => {
    // Redirect to loadout flow
    window.requestLoadout();
};

window.stopGame = () => {
    sendJson({ action: "stop_game" });
};

window.addScore = (points) => {
    sendJson({ action: "add_score", score: points });
};

function sendJson(payload) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(payload));
    }
}

// ----- INPUT HANDLING -----

window.addEventListener('keydown', (e) => {
    if (keys.hasOwnProperty(e.key) || keys.hasOwnProperty(e.code) || e.key === " ") {
        keys[e.key === " " ? "Space" : e.key] = true;
    }
});
window.addEventListener('keyup', (e) => {
    if (keys.hasOwnProperty(e.key) || keys.hasOwnProperty(e.code) || e.key === " ") {
        keys[e.key === " " ? "Space" : e.key] = false;
    }
});

function updateState() {
    const gamepads = navigator.getGamepads();
    const gp = gamepads[0];

    if (gp) {
        controllerState[0] = Math.floor(((gp.axes[0] + 1) / 2) * 255);
        controllerState[1] = Math.floor(((gp.axes[1] + 1) / 2) * 255);
        controllerState[2] = Math.floor(((gp.axes[2] + 1) / 2) * 255);
        controllerState[3] = Math.floor(((gp.axes[3] + 1) / 2) * 255);
        controllerState[4] = (gp.buttons[6]) ? Math.floor(gp.buttons[6].value * 255) : 0;
        controllerState[5] = (gp.buttons[7]) ? Math.floor(gp.buttons[7].value * 255) : 0;

        let b = 0;
        for (let i = 0; i < 16; i++) {
            if (gp.buttons[i] && gp.buttons[i].pressed) b |= (1 << i);
        }
        controllerState[6] = b & 0xFF;
        controllerState[7] = (b >> 8) & 0xFF;

    } else {
        // Keyboard Emulation
        if (keys.a) controllerState[0] = 0;
        else if (keys.d) controllerState[0] = 255;
        else controllerState[0] = 127;

        if (keys.w) controllerState[1] = 0;
        else if (keys.s) controllerState[1] = 255;
        else controllerState[1] = 127;

        if (keys.ArrowLeft) controllerState[2] = 0;
        else if (keys.ArrowRight) controllerState[2] = 255;
        else controllerState[2] = 127;

        if (keys.ArrowUp) controllerState[3] = 0;
        else if (keys.ArrowDown) controllerState[3] = 255;
        else controllerState[3] = 127;

        controllerState[4] = keys.Shift ? 255 : 0;
        controllerState[5] = keys.Space ? 255 : 0;

        let b = 0;
        if (keys['1']) b |= (1 << 0);
        if (keys['2']) b |= (1 << 1);
        if (keys['3']) b |= (1 << 2);
        if (keys['4']) b |= (1 << 3);
        if (keys['5']) b |= (1 << 4);
        if (keys['6']) b |= (1 << 5);
        if (keys['7']) b |= (1 << 6);
        if (keys['8']) b |= (1 << 7);
        if (keys['9']) b |= (1 << 8);
        if (keys['0']) b |= (1 << 9);

        controllerState[6] = b & 0xFF;
        controllerState[7] = (b >> 8) & 0xFF;
    }
}

function updateLoop() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        updateState();
        // Send control data ONLY if it is my turn
        if (isMyTurn) {
            socket.send(controllerState);
        }
    }
    requestAnimationFrame(updateLoop);
}

connect();
