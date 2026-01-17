import asyncio
import websockets
import cv2
import numpy as np
import time

SERVER_URL = "ws://localhost:8000/ws/pi"
#SERVER_URL = "wss://uottahack-8-327580bc1291.herokuapp.com/ws/pi"

# Camera Setup (Try index 0, else 1, else None)
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Warning: No webcam found. Streaming Generated Noise.")
    cap = None

async def receive_controls(websocket):
    print("Listening for controls...")
    try:
        while True:
            data = await websocket.recv()
            if isinstance(data, bytes):
                # Expecting 8 bytes
                if len(data) == 8:
                    # Parse Analog Controls (0-5)
                    analog = [b for b in data[:6]]
                    # Parse Digital Buttons (6-7) - interpreted as uint16
                    buttons = int.from_bytes(data[6:], byteorder='little')
                    
                    # Print status
                    #print(f"\rReceived: Analog={analog} Buttons={buttons:016b}   ", end="", flush=True)
                #else:
                    #print(f"\rReceived {len(data)} bytes (Unknown format)", end="", flush=True)
    except websockets.exceptions.ConnectionClosed:
        print("\nConnection closed (Receive)")

async def send_video(websocket):
    print("Starting Video Stream...")
    try:
        while True:
            if cap:
                ret, frame = cap.read()
                if not ret:
                    # If camera fails, fallback to noise
                    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            else:
                # Generate Noise Frame
                frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
                # Add text
                cv2.putText(frame, f"Simulated Pi: {time.time()}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            # Compress to JPEG
            _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            
            # Send via WebSocket
            await websocket.send(buffer.tobytes())
            
            # Limit FPS ~30
            await asyncio.sleep(0.033)
            
    except websockets.exceptions.ConnectionClosed:
        print("\nConnection closed (Send)")

async def main():
    print(f"Connecting to {SERVER_URL}...")
    async with websockets.connect(SERVER_URL) as websocket:
        print("Connected!")
        # Run receive and send loops concurrently
        await asyncio.gather(
            receive_controls(websocket),
            send_video(websocket)
        )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
        if cap: cap.release()
