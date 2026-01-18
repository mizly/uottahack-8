// HUD Management Module

// Cache DOM elements
let hudOverlay = null;
let crosshair = null;
let ammoCount = null;
let maxAmmoDisplay = null;
let speedVal = null;
let speedBar = null;
let muzzleFlash = null;

// State
let currentAmmo = 0;
let maxAmmo = 0;
let currentSpeed = 0;

export function initHUD() {
    hudOverlay = document.getElementById('hud-overlay');
    crosshair = document.querySelector('.hud-crosshair');
    ammoCount = document.getElementById('hud-ammo-count');
    maxAmmoDisplay = document.getElementById('hud-max-ammo');
    speedVal = document.getElementById('hud-speed-val');
    speedBar = document.getElementById('hud-speed-bar-fill');
    muzzleFlash = document.querySelector('.muzzle-flash');
}

export function updateHUD(gameState, inputState) {
    if (!hudOverlay) return;

    // Visibility: Only show if game is active AND I am the player
    // (Actual visibility toggle is handled in ui.js based on role, but we can double check)

    // 1. Update Ammo
    if (gameState.ammo !== undefined) {
        currentAmmo = gameState.ammo;
        maxAmmo = gameState.max_ammo || 30; // Default

        if (ammoCount) {
            // Animate if changed?
            ammoCount.textContent = currentAmmo.toString().padStart(2, '0');
            if (currentAmmo <= 5) ammoCount.classList.add('text-red-500');
            else ammoCount.classList.remove('text-red-500');
        }
        if (maxAmmoDisplay) maxAmmoDisplay.textContent = `/ ${maxAmmo}`;
    }

    // 2. Simulate Speedometer based on Input
    // We don't have real speed telemetry, but we know if the user is pressing 'W' (Forward)
    // inputState.axes[1] is -127 to 127. Close to -127 is Forward (usually, or + dependent on mapping)
    // Let's assume standard tank controls: Left Stick Y (axes[1])

    // Mapping: 0-255 range from earlier logs, center 127. 
    // < 127 is decreasing (Forward?), > 127 is increasing (Backward?)
    // Let's assume deviation from 127 is speed

    const forwardInput = (inputState.length !== undefined && inputState[1] !== undefined)
        ? Math.abs(inputState[1] - 127)
        : (inputState.axes ? Math.abs((inputState.axes[1] || 0) * 127) : 0);

    const turnInput = (inputState.length !== undefined && inputState[0] !== undefined)
        ? Math.abs(inputState[0] - 127)
        : (inputState.axes ? Math.abs((inputState.axes[0] || 0) * 127) : 0);
    const targetSpeed = Math.min((forwardInput + turnInput) / 1.2, 100); // 0-100 scale estimate

    // Smooth interpolation
    currentSpeed += (targetSpeed - currentSpeed) * 0.1;

    if (speedVal) speedVal.textContent = Math.floor(currentSpeed);
    if (speedBar) speedBar.style.width = `${Math.min(currentSpeed, 100)}%`;
}

export function triggerFireVFX() {
    if (muzzleFlash) {
        // Reset animation
        muzzleFlash.classList.remove('active');
        void muzzleFlash.offsetWidth; // Force reflow
        muzzleFlash.classList.add('active');

        // Screenshake?
        const container = document.querySelector('.video-container');
        if (container) {
            container.animate([
                { transform: 'translate(0,0)' },
                { transform: 'translate(-2px, 2px)' },
                { transform: 'translate(1px, -1px)' },
                { transform: 'translate(0,0)' }
            ], {
                duration: 100,
                iterations: 1
            });
        }
    }
}
