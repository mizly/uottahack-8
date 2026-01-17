const videoFeed = document.getElementById('video-feed');
const statusDiv = document.getElementById('status');
const wsUrl = `ws://${window.location.host}/ws/client`;
let socket = null;

// Controller State: 6 Analog, 2 Button Bytes (16 bits)
// Analog 0-3 (Joysticks): Default 127
// Analog 4-5 (Triggers): Default 0
// Bytes 6-7 (Buttons): Default 0
const controllerState = new Uint8Array(8);
for (let i = 0; i < 4; i++) controllerState[i] = 127;
controllerState[4] = 0;
controllerState[5] = 0;
controllerState[6] = 0;
controllerState[7] = 0;

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
    socket.binaryType = "blob";

    socket.onopen = () => {
        statusDiv.textContent = "Connected";
        statusDiv.style.color = "#4f4";
        requestAnimationFrame(updateLoop);
    };

    socket.onmessage = (event) => {
        // Assume blob is image data (MJPEG frame)
        const url = URL.createObjectURL(event.data);
        videoFeed.onload = () => URL.revokeObjectURL(url);
        videoFeed.src = url;
    };

    socket.onclose = () => {
        statusDiv.textContent = "Disconnected (Retrying...)";
        statusDiv.style.color = "#f44";
        setTimeout(connect, 2000);
    };

    socket.onerror = (err) => {
        console.error("Socket error", err);
        socket.close();
    }
}

// Keyboard Listeners
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
    const gp = gamepads[0]; // Use first gamepad

    if (gp) {
        // Analog 0: Left Stick X
        controllerState[0] = Math.floor(((gp.axes[0] + 1) / 2) * 255);
        // Analog 1: Left Stick Y
        controllerState[1] = Math.floor(((gp.axes[1] + 1) / 2) * 255);
        // Analog 2: Right Stick X
        controllerState[2] = Math.floor(((gp.axes[2] + 1) / 2) * 255);
        // Analog 3: Right Stick Y
        controllerState[3] = Math.floor(((gp.axes[3] + 1) / 2) * 255);

        // Analog 4: Left Trigger (Button 6)
        controllerState[4] = (gp.buttons[6]) ? Math.floor(gp.buttons[6].value * 255) : 0;

        // Analog 5: Right Trigger (Button 7)
        controllerState[5] = (gp.buttons[7]) ? Math.floor(gp.buttons[7].value * 255) : 0;

        // Buttons (map standard buttons to bits if they exist)
        let b = 0;
        for (let i = 0; i < 16; i++) {
            if (gp.buttons[i] && gp.buttons[i].pressed) b |= (1 << i);
        }
        controllerState[6] = b & 0xFF;        // Low byte
        controllerState[7] = (b >> 8) & 0xFF; // High byte

    } else {
        // Keyboard Emulation

        // Byte 0: A/D (Analog 0)
        if (keys.a) controllerState[0] = 0;
        else if (keys.d) controllerState[0] = 255;
        else controllerState[0] = 127;

        // Byte 1: W/S (Analog 1)
        if (keys.w) controllerState[1] = 0;
        else if (keys.s) controllerState[1] = 255;
        else controllerState[1] = 127;

        // Byte 2: Left/Right Arrows (Analog 2)
        if (keys.ArrowLeft) controllerState[2] = 0;
        else if (keys.ArrowRight) controllerState[2] = 255;
        else controllerState[2] = 127;

        // Byte 3: Up/Down Arrows (Analog 3)
        if (keys.ArrowUp) controllerState[3] = 0;
        else if (keys.ArrowDown) controllerState[3] = 255;
        else controllerState[3] = 127;

        // Byte 4: Left Trigger (Shift)
        controllerState[4] = keys.Shift ? 255 : 0; // Digital 0/255 for trigger

        // Byte 5: Right Trigger (Space)
        controllerState[5] = keys.Space ? 255 : 0; // Digital 0/255 for trigger

        // Bytes 6-7: Digital Buttons (16 bits)
        // Keys 1-9, 0 -> Bits 0-9
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

        controllerState[6] = b & 0xFF;        // Low byte
        controllerState[7] = (b >> 8) & 0xFF; // High byte
    }
}

function updateLoop() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        updateState();
        socket.send(controllerState);
    }
    requestAnimationFrame(updateLoop);
}

connect();
