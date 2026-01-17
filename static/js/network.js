const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${protocol}//${window.location.host}/ws/client`;

export let socket = null;
let frameWatchdog = null;

export function connect(onOpen, onMessage, onClose) {
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        console.log("WS Connected");
        if (onOpen) onOpen();
    };

    socket.onmessage = (event) => {
        if (onMessage) onMessage(event);
    };

    socket.onclose = () => {
        if (onClose) onClose();
        if (frameWatchdog) clearTimeout(frameWatchdog);
        setTimeout(() => connect(onOpen, onMessage, onClose), 2000);
    };

    socket.onerror = (err) => {
        console.error("Socket error", err);
        socket.close();
    };
}

export function sendJson(payload) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(payload));
    }
}

export function sendBinary(data) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(data);
    }
}

export function resetWatchdog(callback, timeoutMs = 3000) {
    if (frameWatchdog) clearTimeout(frameWatchdog);
    frameWatchdog = setTimeout(callback, timeoutMs);
}

export function clearWatchdog() {
    if (frameWatchdog) clearTimeout(frameWatchdog);
}
