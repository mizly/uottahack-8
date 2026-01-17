// Native resolution of the video stream (Pi default)
const NATIVE_WIDTH = 640;
const NATIVE_HEIGHT = 480;

const qrCanvas = document.getElementById('qr-canvas');
const ctx = qrCanvas ? qrCanvas.getContext('2d') : null;

export function drawQRCodes(detections) {
    if (!ctx || !qrCanvas) return;

    // Clear previous drawings
    ctx.clearRect(0, 0, qrCanvas.width, qrCanvas.height);

    // Allow canvas size to match display size for correct coordinate mapping
    if (qrCanvas.width !== qrCanvas.offsetWidth || qrCanvas.height !== qrCanvas.offsetHeight) {
        qrCanvas.width = qrCanvas.offsetWidth;
        qrCanvas.height = qrCanvas.offsetHeight;
    }

    if (!detections || detections.length === 0) return;

    // Scale factors
    const scaleX = qrCanvas.width / NATIVE_WIDTH;
    const scaleY = qrCanvas.height / NATIVE_HEIGHT;

    detections.forEach(qr => {
        const points = qr.bbox;
        if (!points || points.length !== 4) return;

        ctx.beginPath();

        ctx.strokeStyle = '#30d158'; // iOS Green
        ctx.lineWidth = 3;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';

        // Move to first point
        ctx.moveTo(points[0][0] * scaleX, points[0][1] * scaleY);

        // Draw lines
        for (let i = 1; i < 4; i++) {
            ctx.lineTo(points[i][0] * scaleX, points[i][1] * scaleY);
        }

        // Close loop
        ctx.closePath();
        ctx.stroke();

        // Draw Text
        const textX = points[0][0] * scaleX;
        const textY = (points[0][1] * scaleY) - 10;

        ctx.font = 'bold 14px "SF Mono", monospace';
        ctx.fillStyle = '#30d158';
        ctx.shadowColor = 'rgba(0,0,0,0.8)';
        ctx.shadowBlur = 4;
        ctx.fillText(qr.text, textX, textY);
    });
}
