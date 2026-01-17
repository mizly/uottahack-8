import os
import uvicorn
import json
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

    async def join_queue(self, websocket: WebSocket, name: str, loadout: dict = None):
        # Check if already in queue
        for p in self.waiting_queue:
            if p["ws"] == websocket:
                return # Already in queue

        entry = {
            "name": name or "Anonymous", 
            "ws": websocket,
            "loadout": loadout or {"id": "vanguard", "name": "Vanguard"} # Default
        }
        self.waiting_queue.append(entry)
        await self.broadcast_game_update()
        
        # If game is not active and no one is playing, try to start
        if not self.game_state.is_active and self.current_player_ws is None:
            await self.try_start_next_game()

    async def try_start_next_game(self):
        if self.waiting_queue:
            next_player = self.waiting_queue.pop(0)
            self.current_player_ws = next_player["ws"]
            
            # Start Game
            self.game_state.is_active = True
            self.game_state.start_time = time.time()
            self.game_state.score = 0
            self.game_state.player_name = next_player["name"]
            # Store loadout in game_state if needed (can add a field to GameState dataclass or just log it for now)
            print(f"Game Started for {self.game_state.player_name} with loadout {next_player['loadout'].get('name')}")
            
            print(f"Game Started for {self.game_state.player_name}")
            await self.broadcast_game_update()
            
            # Start timer loop if not already running (managed via check in broadcast)
            # Actually, we need a dedicated loop or just rely on ticks. 
            # Previous implementation created a task. Let's do that.
            asyncio.create_task(self.game_timer())
        else:
            self.current_player_ws = None

    async def end_game(self):
        if self.game_state.is_active:
            self.game_state.is_active = False
            print(f"Game Over! Final Score: {self.game_state.score}")
            
            # Save to leaderboard
            leaderboard.append({
                "name": self.game_state.player_name,
                "score": self.game_state.score,
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
                            data.get("name", "Player"),
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
                await manager.broadcast_to_clients(data)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, client_type)
    except Exception as e:
        print(f"Error in {client_type}: {e}")
        # manager.disconnect(websocket, client_type) # Already handled usually

if __name__ == "__main__":
    print("Server starting. Access at: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
