import uvicorn
import json
import asyncio
import time
from dataclasses import dataclass, field, asdict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from typing import List, Optional, Dict

app = FastAPI()

@dataclass
class GameState:
    is_active: bool = False
    start_time: float = 0
    score: int = 0
    player_name: str = "Anonymous"
    game_duration: int = 60  # seconds

# Global Leaderboard
leaderboard: List[Dict] = []

class ConnectionManager:
    def __init__(self):
        self.client_ws: Optional[WebSocket] = None
        self.pi_ws: Optional[WebSocket] = None
        self.game_state = GameState()

    async def connect(self, websocket: WebSocket, client_type: str):
        await websocket.accept()
        if client_type == "client":
            self.client_ws = websocket
            print("Web Client Connected")
            # Send initial state
            await self.broadcast_game_update()
        elif client_type == "pi":
            self.pi_ws = websocket
            print("Pi Client Connected")

    def disconnect(self, client_type: str):
        if client_type == "client":
            self.client_ws = None
            print("Web Client Disconnected")
        elif client_type == "pi":
            self.pi_ws = None
            print("Pi Client Disconnected")

    async def broadcast_to_pi(self, message: bytes):
        if self.pi_ws:
            await self.pi_ws.send_bytes(message)

    async def broadcast_to_client(self, message: bytes):
        if self.client_ws:
            await self.client_ws.send_bytes(message)
    
    async def broadcast_game_update(self):
        """Send current game state and leaderboard to web client"""
        if self.client_ws:
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
                "leaderboard": sorted(leaderboard, key=lambda x: x['score'], reverse=True)[:10]
            }
            await self.client_ws.send_text(json.dumps(payload))

    async def start_game(self, name: str):
        self.game_state.is_active = True
        self.game_state.start_time = time.time()
        self.game_state.score = 0
        self.game_state.player_name = name or "Anonymous"
        print(f"Game Started for {self.game_state.player_name}")
        await self.broadcast_game_update()
        # Start timer loop
        asyncio.create_task(self.game_timer())

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
            
            await self.broadcast_game_update()

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
    with open("static/index.html", "r") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws/{client_type}")
async def websocket_endpoint(websocket: WebSocket, client_type: str):
    await manager.connect(websocket, client_type)
    try:
        while True:
            if client_type == "client":
                # Handle mixed content (Binary for controls, Text for JSON commands)
                message = await websocket.receive()
                
                if "bytes" in message:
                    data = message["bytes"]
                    # Forward control data to Pi
                    if len(data) == 8:
                        # Optional: Parse stats here if needed
                        pass
                    await manager.broadcast_to_pi(data)
                    
                elif "text" in message:
                    data = json.loads(message["text"])
                    action = data.get("action")
                    
                    if action == "start_game":
                        await manager.start_game(data.get("name", "Player"))
                    elif action == "add_score":
                        await manager.add_score(data.get("score", 0))

            elif client_type == "pi":
                # Pi only needs to send video bytes
                data = await websocket.receive_bytes()
                await manager.broadcast_to_client(data)
                
    except WebSocketDisconnect:
        manager.disconnect(client_type)
    except Exception as e:
        print(f"Error in {client_type}: {e}")
        manager.disconnect(client_type)

if __name__ == "__main__":
    print("Server starting. Access the web interface at: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
