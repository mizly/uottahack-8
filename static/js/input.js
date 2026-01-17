// Keyboard State
const keys = {
    w: false, s: false, a: false, d: false,
    ArrowUp: false, ArrowDown: false, ArrowLeft: false, ArrowRight: false,
    Space: false, Shift: false,
    '1': false, '2': false, '3': false, '4': false, '5': false,
    '6': false, '7': false, '8': false, '9': false, '0': false
};

// Controller State: 6 Analog, 2 Button Bytes (16 bits)
export const controllerState = new Uint8Array(8);
for (let i = 0; i < 4; i++) controllerState[i] = 127;

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

let lastGpStatus = false;

export function updateInputState(setConnectionStateCallback) {
    const gamepads = navigator.getGamepads();
    let gp = null;

    // Find first active gamepad
    for (const g of gamepads) {
        if (g && g.connected) {
            gp = g;
            break;
        }
    }

    // Debug logging for controller connection (throttle logs)
    if (gp && !lastGpStatus) {
        console.log("Gamepad connected:", gp.id);
        lastGpStatus = true;
        if (setConnectionStateCallback) setConnectionStateCallback(true);
    } else if (!gp && lastGpStatus) {
        console.log("Gamepad disconnected");
        lastGpStatus = false;
    }

    if (gp) {
        // Safe access to axes
        const axis0 = gp.axes[0] || 0;
        const axis1 = gp.axes[1] || 0;
        const axis2 = gp.axes[2] || 0;
        const axis3 = gp.axes[3] || 0;

        controllerState[0] = Math.floor(((axis0 + 1) / 2) * 255);
        controllerState[1] = Math.floor(((axis1 + 1) / 2) * 255);
        controllerState[2] = Math.floor(((axis2 + 1) / 2) * 255);
        controllerState[3] = Math.floor(((axis3 + 1) / 2) * 255);

        // Triggers often mapped to buttons 6/7
        const btn6 = gp.buttons[6];
        const btn7 = gp.buttons[7];

        // Handle analog triggers (value) or digital buttons (pressed)
        controllerState[4] = (btn6 && typeof btn6.value === 'number') ? Math.floor(btn6.value * 255) : (btn6 && btn6.pressed ? 255 : 0);
        controllerState[5] = (btn7 && typeof btn7.value === 'number') ? Math.floor(btn7.value * 255) : (btn7 && btn7.pressed ? 255 : 0);

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
