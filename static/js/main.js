import { connect, resetWatchdog, sendBinary, sendPing } from './network.js?v=2';
import { updateInputState, controllerState } from './input.js?v=14';
import { drawQRCodes } from './cv.js';
import {
    updateGameState,
    handleMatchFound,
    showGameOver,
    closeLoadout,
    videoFeed,
    videoOverlay,
    setConnectionState,
    getIsMyTurn,
    setMode,
    selectTank,
    confirmLoadoutWrapper,
    requestLoadout,
    cancelQueue,
    stopGame,
    addScore,
    closeGameOver,
    dismissQueueModal, // Added
    updatePingDisplay
} from './ui.js?v=19';
import { connectWallet } from './wallet.js';

// Expose functions to global scope for HTML event handlers
window.setMode = setMode;
window.selectTank = selectTank;
window.confirmLoadout = confirmLoadoutWrapper;
window.requestLoadout = requestLoadout;
window.cancelQueue = cancelQueue;
window.stopGame = stopGame;
window.addScore = addScore;
window.closeGameOver = closeGameOver;
window.connectWallet = connectWallet;
window.closeLoadout = closeLoadout;
window.dismissQueueModal = dismissQueueModal; // Added

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

function onOpen() {
    setConnectionState(true);
    // Start Watchdog immediately to show "Media Offline" if no frames arrive
    resetWatchdog(() => {
        videoOverlay.classList.remove('hidden');
        updatePingDisplay(null);
    });
    requestAnimationFrame(updateLoop);
}

function onMessage(event) {
    if (typeof event.data === 'string') {
        // JSON Game State Update
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'game_state') {
                updateGameState(data);
            } else if (data.type === 'match_found') {
                handleMatchFound(data.timeout);
            } else if (data.type === 'match_timeout') {
                closeLoadout();
                alert("Match confirmation timed out!");
            } else if (data.type === 'game_over') {
                showGameOver(data.stats);
            } else if (data.type === 'qr_detected') {
                drawQRCodes(data.data);
            } else if (data.type === 'pong') {
                // We no longer update HUD ping from websocket RTT 
                // to avoid flickering NA state when media is offline.
                // const latency = Date.now() - data.timestamp;
                // updatePingDisplay(latency);
            }
        } catch (e) {
            console.error("Failed to parse JSON", e);
        }
    } else {
        // Assume Binary (Blob or ArrayBuffer)
        if (event.data instanceof Blob) {
            // New Format: [8 bytes timestamp][JPEG Data]
            if (event.data.size > 8) {
                const timestampBlob = event.data.slice(0, 8);
                const imageBlob = event.data.slice(8);

                // Read timestamp (Async)
                timestampBlob.arrayBuffer().then(buffer => {
                    const view = new DataView(buffer);
                    const serverTime = view.getFloat64(0, true); // Little Endian
                    const latency = Date.now() - serverTime;
                    updatePingDisplay(latency);
                }).catch(e => console.error("Timestamp read error", e));

                const url = URL.createObjectURL(imageBlob);
                videoFeed.onload = () => URL.revokeObjectURL(url);
                videoFeed.src = url;
            } else {
                // Fallback for old format or noise
                const url = URL.createObjectURL(event.data);
                videoFeed.onload = () => URL.revokeObjectURL(url);
                videoFeed.src = url;
            }

            // Hide overlay on frame receive
            videoOverlay.classList.add('hidden');

            // Reset Watchdog
            resetWatchdog(() => {
                videoOverlay.classList.remove('hidden');
                updatePingDisplay(null);
            });
        }
    }
}

function onClose() {
    setConnectionState(false);
    videoOverlay.classList.remove('hidden');
    updatePingDisplay(null);
    // Watchdog cleared by network.js calling connect again
}

let lastPingTime = 0;
function updateLoop() {
    updateInputState(setConnectionState);

    // Send control data ONLY if it is my turn
    // if (getIsMyTurn()) {
    if (true) {
        sendBinary(controllerState);
    }

    // Send Ping every 1s
    const now = Date.now();
    if (now - lastPingTime > 1000) {
        sendPing();
        lastPingTime = now;
    }

    requestAnimationFrame(updateLoop);
}

// Start Connection
connect(onOpen, onMessage, onClose);
