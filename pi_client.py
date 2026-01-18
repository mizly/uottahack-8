import asyncio
import websockets
import cv2
import numpy as np
import time

import struct
import ssl

SERVER_URL = "ws://localhost:8000/ws/pi"
#SERVER_URL = "wss://uottahack-8-327580bc1291.herokuapp.com/ws/pi"

# Camera Setup (Try index 0, else 1, else None)
cap = cv2.VideoCapture(0)
# cap = None
if cap and not cap.isOpened():
    print("Warning: No webcam found. Streaming Generated Noise.")
    cap = None

async def receive_controls(websocket):
    print("Listening for controls...")
    try:
        while True:
            # print("Waiting for data...")
            data = await websocket.recv()
            # print(f"Got data type: {type(data)}")
            if isinstance(data, bytes):
                # Expecting 8 bytes
                if len(data) == 8:
                    # Parse Analog Controls (0-5)
                    analog = [b for b in data[:6]]
                    # Parse Digital Buttons (6-7) - interpreted as uint16
                    buttons = int.from_bytes(data[6:], byteorder='little')
                    
                    # Print status
                    #print(f"Received: Analog={analog} Buttons={buttons:016b}")
                #else:
                    #print(f"Received {len(data)} bytes (Unknown format)")
    except websockets.exceptions.ConnectionClosed:
        print("\nConnection closed (Receive)")
    except Exception as e:
        print(f"\nError in receive_controls: {e}")

async def send_video(websocket):
    print("Starting Video Stream...")
    try:
        while True:
            if cap:
                # Clear buffer to get the latest frame
                for _ in range(5):
                    cap.grab()
                ret, frame = cap.read()
                if not ret:
                    # If camera fails, fallback to noise
                    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            else:
                # Generate Noise Frame
                frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
                # Add text
                cv2.putText(frame, f"Gurt Pi: {time.time()}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            # Compress to JPEG
            _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            
            # Prepend Timestamp (double, 8 bytes)
            timestamp = time.time() * 1000 # ms
            packed_time = struct.pack('<d', timestamp)
            
            # Send via WebSocket
            await websocket.send(packed_time + buffer.tobytes())
            
            # Limit FPS ~30
            await asyncio.sleep(0.033)
            
    except websockets.exceptions.ConnectionClosed:
        print("\nConnection closed (Send)")

async def main():
    print(f"Connecting to {SERVER_URL}...")
    
    ssl_context = None
    if SERVER_URL.startswith("wss"):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.load_verify_locations("cacert.pem")
    
    async with websockets.connect(SERVER_URL, ssl=ssl_context) as websocket:
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
