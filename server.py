import os
import uvicorn
import json
import cv2
import numpy as np
import asyncio
import time
from dataclasses import dataclass, field, asdict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from typing import List, Optional, Dict

app = FastAPI()

LEADERBOARD_FILE = "leaderboard.json"

def load_leaderboard():
    if os.path.exists(LEADERBOARD_FILE):
        try:
            with open(LEADERBOARD_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_leaderboard(data):
    with open(LEADERBOARD_FILE, "w") as f:
        json.dump(data, f)

# Global State
leaderboard: List[Dict] = load_leaderboard()

@dataclass
class GameState:
    is_active: bool = False
    start_time: float = 0
    score: int = 0
    player_name: str = "Anonymous"
    player_class: str = "Vanguard"
    game_duration: int = 60  # seconds

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = [] # All connected clients
        self.pi_ws: Optional[WebSocket] = None
        self.game_state = GameState()
        
        # Queue System
        # List of {"name": str, "ws": WebSocket}
        self.waiting_queue: List[Dict] = []
        self.current_player_ws: Optional[WebSocket] = None
        
        # Confirmation System
        self.confirming_player_ws: Optional[WebSocket] = None
        self.confirming_player_data: Optional[Dict] = None
        self.confirmation_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket, client_type: str):
        await websocket.accept()
        if client_type == "client":
            self.active_connections.append(websocket)
            print("Web Client Connected")
            await self.broadcast_game_update()
        elif client_type == "pi":
            self.pi_ws = websocket
            print("Pi Client Connected")

    def disconnect(self, websocket: WebSocket, client_type: str):
        if client_type == "client":
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            
            # Remove from queue if present
            self.waiting_queue = [p for p in self.waiting_queue if p["ws"] != websocket]
            
            # If current player disconnects, end game or pass turn
            if websocket == self.current_player_ws:
                print("Current player disconnected!")
                asyncio.create_task(self.end_game())
            
            # If confirming player disconnects
            if websocket == self.confirming_player_ws:
                print("Confirming player disconnected!")
                self.confirming_player_ws = None
                self.confirming_player_data = None
                if self.confirmation_task:
                    self.confirmation_task.cancel()
                asyncio.create_task(self.try_start_next_game())
                
            print("Web Client Disconnected")
            
        elif client_type == "pi":
            self.pi_ws = None
            print("Pi Client Disconnected")

    async def broadcast_to_pi(self, message: bytes):
        if self.pi_ws:
            await self.pi_ws.send_bytes(message)

    async def broadcast_to_clients(self, message: bytes):
        # Broadcast video to ALL connected clients (spectators included)
        for connection in self.active_connections:
            try:
                await connection.send_bytes(message)
            except:
                pass
    
    async def broadcast_game_update(self):
        """Send current game state, queue, and leaderboard to ALL clients"""
        
        # Calculate time left
        time_left = 0
        if self.game_state.is_active:
            elapsed = time.time() - self.game_state.start_time
            time_left = max(0, self.game_state.game_duration - int(elapsed))
            
            if time_left == 0:
                await self.end_game()
                return

        payload = {
            "type": "game_state",
            "active": self.game_state.is_active,
            "time_left": time_left,
            "score": self.game_state.score,
            "player": self.game_state.player_name,
            "queue": [p["name"] for p in self.waiting_queue],
            "leaderboard": sorted(leaderboard, key=lambda x: x['score'], reverse=True)[:10]
        }
        
        json_payload = json.dumps(payload)
        
        for connection in self.active_connections:
            try:
                # Personalize the update? (e.g. "is_turn": True)
                # For now, send same state, frontend checks name match or just implies it
                await connection.send_text(json_payload)
            except:
                pass

    async def join_queue(self, websocket: WebSocket, name: str):
        # Check if already in queue
        for p in self.waiting_queue:
            if p["ws"] == websocket:
                return # Already in queue

        entry = {
            "name": name or "Anonymous", 
            "ws": websocket
        }
        self.waiting_queue.append(entry)
        await self.broadcast_game_update()
        
        # If game is not active and no one is playing, try to start
        if not self.game_state.is_active and self.current_player_ws is None and self.confirming_player_ws is None:
            await self.try_start_next_game()

    async def leave_queue(self, websocket: WebSocket):
        # Remove from wait queue if there
        self.waiting_queue = [p for p in self.waiting_queue if p["ws"] != websocket]
        
        # Also check if they are the one currently confirming
        if websocket == self.confirming_player_ws:
            print(f"Player {self.confirming_player_data['name']} cancelled during confirmation.")
            self.confirming_player_ws = None
            self.confirming_player_data = None
            if self.confirmation_task:
                self.confirmation_task.cancel()
            
            # They cancelled, so we should look for the next person
            await self.broadcast_game_update()
            await self.try_start_next_game()
            return

        await self.broadcast_game_update()

    async def try_start_next_game(self):
        # If we are already confirming someone or playing, don't start
        if self.game_state.is_active or self.confirming_player_ws:
            return

        if self.waiting_queue:
            next_player = self.waiting_queue.pop(0)
            self.confirming_player_ws = next_player["ws"]
            self.confirming_player_data = next_player
            
            # Send match found event to specific player
            try:
                await self.confirming_player_ws.send_text(json.dumps({
                    "type": "match_found",
                    "timeout": 30
                }))
                
                # Start timeout task
                self.confirmation_task = asyncio.create_task(self.confirmation_timeout())
                print(f"Match found for {next_player['name']}, waiting for confirmation...")
            except:
                # If sending fails, they likely disconnected. Try next.
                print("Failed to contact candidate, moving to next...")
                self.confirming_player_ws = None
                await self.try_start_next_game()
        else:
            self.current_player_ws = None
            
    async def confirmation_timeout(self):
        try:
            await asyncio.sleep(30)
            # Timeout happened
            if self.confirming_player_ws:
                print(f"Confirmation timed out for {self.confirming_player_data['name']}")
                # Notify them they missed it?
                try:
                    await self.confirming_player_ws.send_text(json.dumps({"type": "match_timeout"}))
                except:
                    pass
                    
                self.confirming_player_ws = None
                self.confirming_player_data = None
                
                # IMPORTANT: Broadcast so the user's UI resets (removes "Abort" button)
                await self.broadcast_game_update()
                
                await self.try_start_next_game()
        except asyncio.CancelledError:
            pass

    async def confirm_match(self, websocket: WebSocket, loadout: dict):
        if websocket == self.confirming_player_ws:
            if self.confirmation_task:
                self.confirmation_task.cancel()
            
            # Start Game
            self.current_player_ws = websocket
            self.confirming_player_ws = None
            
            self.game_state.is_active = True
            self.game_state.start_time = time.time()
            self.game_state.score = 0
            self.game_state.player_name = self.confirming_player_data["name"]
            self.game_state.player_class = loadout.get("name", "Vanguard")
            
            print(f"Game Started for {self.game_state.player_name} with loadout {loadout.get('name')}")
            await self.broadcast_game_update()
            
            asyncio.create_task(self.game_timer())

    async def end_game(self):
        if self.game_state.is_active:
            self.game_state.is_active = False
            print(f"Game Over! Final Score: {self.game_state.score}")
            
            # Save to leaderboard
            leaderboard.append({
                "name": self.game_state.player_name,
                "score": self.game_state.score,
                "class": self.game_state.player_class,
                "date": time.strftime("%Y-%m-%d %H:%M")
            })
            save_leaderboard(leaderboard)
            
            self.current_player_ws = None
            await self.broadcast_game_update()
            
            # Wait a bit then start next
            await asyncio.sleep(3)
            await self.try_start_next_game()

    async def add_score(self, points: int):
        if self.game_state.is_active:
            self.game_state.score += points
            await self.broadcast_game_update()

    async def game_timer(self):
        while self.game_state.is_active:
            await self.broadcast_game_update()
            await asyncio.sleep(1)

manager = ConnectionManager()

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get():
    return FileResponse("static/index.html")

@app.websocket("/ws/{client_type}")
async def websocket_endpoint(websocket: WebSocket, client_type: str):
    await manager.connect(websocket, client_type)
    try:
        while True:
            if client_type == "client":
                # Handle mixed content
                message = await websocket.receive()
                
                if "bytes" in message:
                    data = message["bytes"]
                    # ONLY forward controls if this is the current player
                    if manager.current_player_ws == websocket and manager.game_state.is_active:
                        await manager.broadcast_to_pi(data)
                    
                elif "text" in message:
                    data = json.loads(message["text"])
                    action = data.get("action")
                    
                    if action == "join_queue":
                        await manager.join_queue(
                            websocket, 
                            data.get("name", "Player")
                        )
                    elif action == "leave_queue":
                        await manager.leave_queue(websocket)
                    elif action == "confirm_match":
                        await manager.confirm_match(
                            websocket,
                            data.get("loadout")
                        )
                    elif action == "stop_game":
                        # Only current player can stop
                        if manager.current_player_ws == websocket:
                            await manager.end_game()
                    elif action == "add_score":
                        # In real app, this comes from Pi, but for dev we allow client sim
                        # Allow sim only if playing
                        if manager.current_player_ws == websocket:
                            await manager.add_score(data.get("score", 0))

            elif client_type == "pi":
                # Pi sends video bytes
                data = await websocket.receive_bytes()
                
                # 1. Forward raw video to clients
                await manager.broadcast_to_clients(data)
                
                # 2. Server-side CV processing
                try:
                    # Convert bytes to numpy array
                    nparr = np.frombuffer(data, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        # Detect QR Codes
                        detector = cv2.QRCodeDetector()
                        retval, decoded_info, points, _ = detector.detectAndDecodeMulti(frame)
                        
                        qr_results = []
                        if retval:
                            points = points.astype(int)
                            for i, text in enumerate(decoded_info):
                                if text:
                                    # Convert numpy int32 to python int for JSON serialization
                                    bbox = points[i].tolist() 
                                    qr_results.append({
                                        "text": text,
                                        "bbox": bbox
                                    })
                        
                        # Broadcast detections (even if empty, to clear previous)
                        # Only broadcast if we have active clients? or just always.
                        # Always sending might saturate network if 30fps?
                        # Let's send it.
                        json_payload = json.dumps({
                            "type": "qr_detected",
                            "data": qr_results
                        })
                        
                        for connection in manager.active_connections:
                            try:
                                await connection.send_text(json_payload)
                            except:
                                pass
                                
                except Exception as e:
                     print(f"CV Error: {e}")
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, client_type)
    except Exception as e:
        print(f"Error in {client_type}: {e}")
        # manager.disconnect(websocket, client_type) # Already handled usually

if __name__ == "__main__":
    print("Server starting. Access at: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
