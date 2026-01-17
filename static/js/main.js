import { connect, resetWatchdog, sendBinary } from './network.js';
import { updateInputState, controllerState } from './input.js';
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
    closeGameOver
} from './ui.js';
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
            }
        } catch (e) {
            console.error("Failed to parse JSON", e);
        }
    } else {
        // Assume Binary (Blob or ArrayBuffer)
        if (event.data instanceof Blob) {
            const url = URL.createObjectURL(event.data);
            videoFeed.onload = () => URL.revokeObjectURL(url);
            videoFeed.src = url;

            // Hide overlay on frame receive
            videoOverlay.classList.add('hidden');

            // Reset Watchdog
            resetWatchdog(() => {
                videoOverlay.classList.remove('hidden');
            });
        }
    }
}

function onClose() {
    setConnectionState(false);
    videoOverlay.classList.remove('hidden');
    // Watchdog cleared by network.js calling connect again
}

function updateLoop() {
    updateInputState(setConnectionState);

    // Send control data ONLY if it is my turn
    if (getIsMyTurn()) {
        sendBinary(controllerState);
    }
    requestAnimationFrame(updateLoop);
}

// Start Connection
connect(onOpen, onMessage, onClose);
