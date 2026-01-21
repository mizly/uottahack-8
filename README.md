# UOttaHack 8 Best Hardware Hack - GURT (Ground Unit Response Tank)

[Devpost](https://devpost.com/software/ground-unit-response-tank-g-u-r-t) | 
[gurt.tech](https://gurt.tech) (Robot is currently decommissioned so website will not work D: rest in piece gurt)

![Gurt and the enemies](/static/images/thumb.jpg)
## Features
- **Real-time Video Feed**: Low latency streaming from Pi using a **custom-built QNX camera driver** (optimized from ~3fps to being able to run consistent 30fps).
- **Low Latency Control**: WebSocket-based control loop.
- **Hardware Integration**: Real-world hardware control with Raspberry Pi 4 and Arduino.
- **Two Game Modes**:
    - **Casual**: Free to play.
    - **Ranked**: Pay 0.1 SOL Entry Fee -> Win -> Get 0.18 SOL Payout.
- **Leaderboard**: Track top pilots.

This project implements a real-time remote control system with video streaming using WebSockets. It consists of a central FastAPI server, a web-based client for control, and a hardware client running on a Raspberry Pi 4.

## Hardware Architecture

Our system uses a dual-controller architecture for reliability and performance:
1. **Raspberry Pi 4 (Main Controller)**:
   - OS: **QNX 8** (Unix-based RTOS).
   - Responsibilities: Runs the Python client (`pi_client.py`), handles WebSocket communication, and streams video.
   - **Custom Camera Driver**: To overcome QNX's default limitations, we developed a native camera driver that boosted frame rates from a stuttering **3 FPS to a smooth 30 FPS**. Code adapted from [camera_example3_viewfinder](https://gitlab.com/qnx/projects/camera-projects/applications/camera_example3_viewfinder)
2. **Arduino (Motor Controller)**:
   - Responsibilities: Receives serial commands from the Pi to control the physical motors of the robot.
   - Logic: Located in `turning.ino`.

## Prerequisites

- Python 3.8+
- Hardware setup (optional, simulation supported):
  - Raspberry Pi 4 with QNX 8
  - Arduino (for motor control)
  - Webcam / Camera Module

## Setup

1.  **Clone the repository**:
    ```bash
    git clone <repository_url>
    cd uottahack-8
    ```

2.  **Create and activate a virtual environment**:
    ```bash
    # Windows
    python -m venv venv
    .\venv\Scripts\activate

    # macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4. **Solana Devnet Setup**:
   The server acts as the "House" and needs a wallet to hold entry fees and pay out winnings.
   - Start the server (step below).
   - Look for the `[SOLANA] House Wallet Public Key` in the terminal output.
   - **Send Devnet SOL to this address** so it has funds to pay out winners!
   - You can get Devnet SOL from [faucet.solana.com](https://faucet.solana.com/).

## Running the Project

### 1. Start the Server (Cloud/Laptop)

This starts the central communication hub.

```bash
python server.py
```

Open your browser and navigate to [http://localhost:8000](http://localhost:8000).

### 2. Start the Pi Client (On QNX 8 / Raspberry Pi)

This runs on the **Raspberry Pi 4**. It connects to the server, receives control commands, and streams video using our custom QNX driver.

```bash
python pi_client.py
```

*Note: You can also run this on your laptop for testing; it will fallback to your webcam.*

## Usage

1.  Ensure both the **Server** and **Pi Client** are running.
2.  Open the web interface ([http://localhost:8000](http://localhost:8000)).
3.  The web interface sends control data to the server.
4.  The server relays these controls to the `pi_client.py`.
5.  The `pi_client.py` forwards motor controls to the Arduino and streams video back.

## Troubleshooting

-   **Port 8000 already in use**: Edit `server.py` and change the port in `uvicorn.run(..., port=8000)`.
-   **No Webcam**: The `pi_client.py` will automatically fall back to generating visual noise if no webcam is detected.
-   **Connection Refused**: Ensure the server is running before starting the client.
