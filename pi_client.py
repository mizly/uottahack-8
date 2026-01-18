import asyncio
import websockets
import cv2
import numpy as np
import time
import struct
import ssl
import subprocess
import os
import sys

# Configuration
SERVER_URL = "ws://localhost:8000/ws/pi"
# SERVER_URL = "wss://uottahack-8-327580bc1291.herokuapp.com/ws/pi"

# Camera Commands to try for QNX fallback
# We prioritize the custom streamer which dumps raw RGBA
QNX_COMMANDS = [
    ["./camera_streamer"], 
    ["./camera_example3_viewfinder"]
]

async def receive_controls(websocket):
    print("Listening for controls...")
    try:
        while True:
            data = await websocket.recv()
            if isinstance(data, bytes) and len(data) == 8:
                # Analog (6) + Buttons (2)
                # analog = [b for b in data[:6]]
                # buttons = int.from_bytes(data[6:], byteorder='little')
                pass
    except websockets.exceptions.ConnectionClosed:
        print("\nConnection closed (Receive)")
    except Exception as e:
        print(f"\nError in receive_controls: {e}")

async def send_video(websocket):
    print("Starting Video Stream Initialization...")
    
    # --- METHOD 1: OpenCV Standard ---
    cap = cv2.VideoCapture(0)
    # Check if opened successfully
    if cap.isOpened():
        print("-> Using OpenCV Camera (Method 1)")
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("OpenCV stream ended.")
                    break
                
                # Resize if needed to 640x480 to match everything else
                if frame.shape[1] != 640 or frame.shape[0] != 480:
                    frame = cv2.resize(frame, (640, 480))

                # Compress to JPEG
                _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                
                # Timestamp (ms, double)
                timestamp = time.time() * 1000
                packed_time = struct.pack('<d', timestamp)
                
                await websocket.send(packed_time + buffer.tobytes())
                await asyncio.sleep(0.001) # Yield slightly
        except Exception as e:
            print(f"OpenCV Error: {e}")
        finally:
            cap.release()
            print("OpenCV released. Attempting fallback...")
    else:
        print("-> OpenCV capture failed to open.")

    # --- METHOD 2: QNX Native Subprocess ---
    print("-> Trying QNX Native Fallback (Method 2)")
    cmd = None
    for c in QNX_COMMANDS:
        if os.path.exists(c[0]):
            cmd = c
            break
            
    if cmd:
        print(f"-> Found binary: {cmd[0]}")
        process = None
        try:
            # Start C process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=sys.stderr, # Pass stderr through to console
                bufsize=0 # Unbuffered
            )
            
            while True:
                # Read Header (24 bytes)
                # double timestamp (8), uint32 size (4), uint32 width (4), uint32 height (4), uint32 format (4)
                header_data = await asyncio.to_thread(process.stdout.read, 24)
                if not header_data or len(header_data) != 24:
                    print("End of stream or error reading header. (Process exited?)")
                    break
                    
                timestamp_s, size, width, height, fmt = struct.unpack('<dIIII', header_data)
                
                # Validation
                if size == 0 or width == 0 or height == 0:
                    print(f"Invalid frame header: size={size} {width}x{height}")
                    continue

                # Read Payload
                payload_data = await asyncio.to_thread(process.stdout.read, size)
                if not payload_data or len(payload_data) != size:
                    print(f"Incomplete frame payload. Expected {size}, got {len(payload_data) if payload_data else 0}")
                    break
                
                # Convert to numpy array
                frame = None
                
                # Format 1: CAMERA_FRAMETYPE_NV12
                if fmt == 1: 
                    # NV12 is YUV420sp (Y + interleaved UV)
                    # Total size should be width * height * 1.5
                    expected_size = int(width * height * 1.5)
                    if size == expected_size:
                         yuv = np.frombuffer(payload_data, dtype=np.uint8)
                         yuv = yuv.reshape((int(height * 1.5), width))
                         frame = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_NV12)
                    else:
                        print(f"NV12 Size mismatch. Exp {expected_size}, Got {size}")
                        
                # Format 2: CAMERA_FRAMETYPE_RGB8888 (Actually probably BGR or BGRA)
                elif fmt == 2:
                     expected_size = width * height * 4
                     if size == expected_size:
                         raw = np.frombuffer(payload_data, dtype=np.uint8)
                         raw = raw.reshape((height, width, 4))
                         frame = cv2.cvtColor(raw, cv2.COLOR_RGBA2BGR)
                     else:
                        print(f"RGB8888 Size mismatch. Exp {expected_size}, Got {size}")

                # Format 3: CAMERA_FRAMETYPE_RGB888
                elif fmt == 3:
                     expected_size = width * height * 3
                     if size == expected_size:
                         raw = np.frombuffer(payload_data, dtype=np.uint8)
                         raw = raw.reshape((height, width, 3))
                         frame = raw # Assume RGB/BGR matches
                     else:
                        print(f"RGB888 Size mismatch. Exp {expected_size}, Got {size}")

                # Format 31: CAMERA_FRAMETYPE_BGR8888
                elif fmt == 31:
                     expected_size = width * height * 4
                     if size == expected_size:
                         raw = np.frombuffer(payload_data, dtype=np.uint8)
                         raw = raw.reshape((height, width, 4))
                         frame = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
                     else:
                        print(f"BGR8888 Size mismatch. Exp {expected_size}, Got {size}")

                else:
                    print(f"Unknown/Unsupported format: {fmt}. Playing noise.")
                
                if frame is None:
                    # Fallback noise
                    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
                    cv2.putText(frame, f"fmt={fmt}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

                # Compress and Send
                _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                
                # Repack timestamp for server (ms)
                # C code sends seconds (double)
                pack_timestamp = timestamp_s * 1000.0
                packed_time = struct.pack('<d', pack_timestamp)
                
                await websocket.send(packed_time + buffer.tobytes())
                
        except Exception as e:
            print(f"QNX Subprocess Error: {e}")
        finally:
            if process:
                process.terminate()
                process.wait()
    else:
        print("-> No QNX binary found.")

    # --- METHOD 3: Generated Noise ---
    print("-> All methods failed. Streaming Noise (Method 3)")
    try:
        while True:
            # Generate random noise
            frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            # Add Overlay
            cv2.putText(frame, "NO SIGNAL", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
            current_time = f"{time.time():.1f}"
            cv2.putText(frame, current_time, (50, 290), cv2.FONT_HERSHEY_SIMPLEX, 1, (200, 200, 200), 2)
            
            _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            timestamp = time.time() * 1000
            packed_time = struct.pack('<d', timestamp)
            await websocket.send(packed_time + buffer.tobytes())
            
            # Limit to ~30 FPS
            await asyncio.sleep(0.033) 
    except Exception as e:
        print(f"Noise Gen Error: {e}")

async def main():
    print(f"Connecting to {SERVER_URL}...")
    
    ssl_context = None
    if SERVER_URL.startswith("wss"):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.load_verify_locations("cacert.pem")
    
    async with websockets.connect(SERVER_URL, ssl=ssl_context) as websocket:
        print("Connected!")
        await asyncio.gather(
            receive_controls(websocket),
            send_video(websocket)
        )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")