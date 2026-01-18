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
import serial

# Configuration
SERVER_URL = "ws://localhost:8000/ws/pi"
#SERVER_URL = "wss://uottahack-8-327580bc1291.herokuapp.com/ws/pi"

SERIAL_PORT = "/dev/ser1"
BAUD_RATE = 115200

# Camera Commands to try for QNX fallback
# We prioritize the custom streamer which dumps raw RGBA
QNX_COMMANDS = [
    ["./camera_streamer"], 
    ["./camera_example3_viewfinder"]
]

# State for throttling
latest_control_data = None
current_ser = None

async def serial_transmitter():
    global latest_control_data, current_ser
    last_sent_data = None
    print("Serial transmitter task started.")
    
    try:
        while True:
            if current_ser and current_ser.is_open:
                # Send controls
                if latest_control_data and latest_control_data != last_sent_data:
                    try:
                        def write_and_flush(data):
                            current_ser.write(data)
                            current_ser.flush()
                        await asyncio.to_thread(write_and_flush, latest_control_data)
                        last_sent_data = latest_control_data
                    except Exception as e:
                        print(f"Serial write error: {e}")
            
            # Run at ~50Hz (20ms)
            await asyncio.sleep(0.02)
    except asyncio.CancelledError:
        print("Serial transmitter task stopping...")

async def receive_controls(websocket):
    global latest_control_data, current_ser
    print("Listening for controls...")
    
    try:
        # Open serial with settings to prevent Arduino auto-reset
        current_ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0)
        current_ser.setDTR(False) 
        print(f"Serial port {SERIAL_PORT} opened. Waiting for Arduino boot...")
        await asyncio.sleep(1.5) # Allow Arduino to initialize
        current_ser.reset_input_buffer()
        current_ser.reset_output_buffer()
        print("Serial ready.")
    except Exception as e:
        print(f"Failed to open serial port: {e}")
        current_ser = None

    last_print_time = 0
    try:
        while True:
            data = await websocket.recv()
            if isinstance(data, bytes) and len(data) == 8:
                # 1. Unpack browser data (Unsigned 8 bytes)
                # Browser format: [UX, UY, RX, RY, LT, RT, B_LOW, B_HIGH]
                u_lx, u_ly, u_rx, u_ry, u_lt, u_rt = data[:6]
                raw_btns = int.from_bytes(data[6:], byteorder='little')
                
                # 2. Scale to Signed (-127 to 127) and Constrain
                # Browser is 0-255, we want -127 to 127
                def scale(val):
                    return max(-127, min(127, val - 127))

                lx = scale(u_lx)
                ly = scale(u_ly)
                rx = scale(u_rx)
                ry = scale(u_ry)
                lt = scale(u_lt)
                rt = scale(u_rt)
                
                # 3. Re-pack in Big Endian Signed format (>bbbbbbH)
                new_packet = struct.pack(">bbbbbbH", lx, ly, rx, ry, lt, rt, raw_btns)
                
                # Update global state for transmitter task
                latest_control_data = new_packet
                
                # Throttle printing to 10Hz
                current_time = time.time()
                if current_time - last_print_time > 0.1:
                    print(f"\rMapped: L({lx:4},{ly:4}) R({rx:4},{ry:4}) T({lt:4},{rt:4}) B:{raw_btns:016b}   ", end="", flush=True)
                    last_print_time = current_time

    except websockets.exceptions.ConnectionClosed:
        print("\nConnection closed (Receive)")
    except Exception as e:
        print(f"\nError in receive_controls: {e}")
    finally:
        if current_ser:
            current_ser.close()

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

                # Resize BEFORE compression if too large
                if frame.shape[1] > 640:
                    scale_ratio = 640.0 / frame.shape[1]
                    new_height = int(frame.shape[0] * scale_ratio)
                    frame = cv2.resize(frame, (640, new_height))

                # Compress and Send
                _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                
                # Use current system time for latency calculation (Epoch ms)
                # The camera timestamp is likely monotonic and not comparable to browser Date.now()
                timestamp = time.time() * 1000.0
                packed_time = struct.pack('<d', timestamp)
                
                await websocket.send(packed_time + buffer.tobytes())
                
        except asyncio.CancelledError:
             print("Video stream task cancelled.")
        except Exception as e:
            print(f"QNX Subprocess Error: {e}")
        finally:
            if process:
                print("Terminating QNX camera process...")
                process.terminate()
                try:
                    # Give it a second to die gracefully
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    print("Force killing QNX camera process...")
                    process.kill()
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
            send_video(websocket),
            serial_transmitter()
        )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
