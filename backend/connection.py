import asyncio
import json
import time
import random
from typing import List, Dict, Optional
from fastapi import WebSocket

from .game import GameState, leaderboard, save_leaderboard
from .solana import verify_transaction, payout, PAYOUT_AMOUNT, WIN_THRESHOLD
from .cv import process_frame_for_qr

TIMEOUT_CONFIRMATION = 120

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = [] # All connected clients
        self.pi_ws: Optional[WebSocket] = None
        self.game_state = GameState()
        self.frame_count = 0
        
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
        if not self.active_connections:
            return

        async def send_safe(ws):
            try:
                await ws.send_bytes(message)
                return None
            except:
                return ws # Return the websocket object if it failed

        # Run all sends concurrently
        results = await asyncio.gather(*[send_safe(ws) for ws in self.active_connections])
        
        # Cleanup failed connections
        for ws in results:
            if ws:
                try:
                    self.active_connections.remove(ws)
                except ValueError:
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
                    "timeout": TIMEOUT_CONFIRMATION
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
            await asyncio.sleep(TIMEOUT_CONFIRMATION)
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

    async def confirm_match(self, websocket: WebSocket, loadout: dict, mode: str = "casual", signature: str = None, player_key: str = None):
        if websocket == self.confirming_player_ws:
            # Ranked Verification
            if mode == "ranked":
                if not signature or not player_key:
                    print("Ranked mode selected but missing signature/key")
                    return # Or send error
                
                print(f"Verifying Ranked Entry for {self.confirming_player_data['name']}...")
                valid = await verify_transaction(signature, player_key)
                if not valid:
                    print("Invalid Transaction! Game aborted.")
                    # Cleanup to prevent stuck queue
                    if self.confirmation_task:
                        self.confirmation_task.cancel()
                    self.confirming_player_ws = None
                    self.confirming_player_data = None
                    
                    try:
                        await websocket.send_text(json.dumps({"type": "match_timeout"}))
                    except:
                        pass
                        
                    await self.broadcast_game_update()
                    await self.try_start_next_game()
                    return

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
            
            # Store Mode
            self.game_state.is_ranked = (mode == "ranked")
            self.game_state.player_key = player_key
            
            print(f"Game Started for {self.game_state.player_name} (Mode: {mode})")
            await self.broadcast_game_update()
            
            asyncio.create_task(self.game_timer())

    async def end_game(self):
        if self.game_state.is_active:
            self.game_state.is_active = False
            print(f"Game Over! Final Score: {self.game_state.score}")
            
            # Payout?
            if self.game_state.is_ranked and self.game_state.score >= WIN_THRESHOLD and self.game_state.player_key:
                print("RANKED WIN DETECTED! Processing Payout...")
                await payout(self.game_state.player_key, PAYOUT_AMOUNT)
            
            # Save to leaderboard
            leaderboard.append({
                "name": self.game_state.player_name,
                "score": self.game_state.score,
                "class": self.game_state.player_class,
                "date": time.strftime("%Y-%m-%d %H:%M"),
                "mode": "ranked" if self.game_state.is_ranked else "casual"
            })
            save_leaderboard(leaderboard)
            
            # Generate Dummy Stats for Demo
            final_stats = {
                "score": self.game_state.score,
                "distance": f"{random.randint(50, 500)}m",
                "shots": random.randint(10, 100),
                "enemies": random.randint(0, 15)
            }
            
            # 1. Notify the player specifically with game over stats
            if self.current_player_ws:
                try:
                    await self.current_player_ws.send_text(json.dumps({
                        "type": "game_over",
                        "stats": final_stats
                    }))
                except:
                    pass

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
            
    # ----- MESSAGE HANDLING -----
    
    async def process_client_message(self, websocket: WebSocket, message: dict):
        """Handle incoming messages from CLIENT"""
        # message is a dictionary from receive()
        
        if "bytes" in message:
            data = message["bytes"]
            # ONLY forward controls if this is the current player
            if self.current_player_ws == websocket and self.game_state.is_active:
                # Print control bytes for debugging
                if len(data) == 8:
                    analog = list(data[:6])
                    # Parse 16-bit buttons
                    buttons_int = int.from_bytes(data[6:], byteorder='little')
                    buttons_bin = f"{buttons_int:016b}"[::-1]
                    print(f"Control Data: Analog={analog} Buttons={buttons_bin}")

                await self.broadcast_to_pi(data)
            
        elif "text" in message:
            data = json.loads(message["text"])
            action = data.get("action")
            
            if action == "join_queue":
                await self.join_queue(
                    websocket, 
                    data.get("name", "Player")
                )
            elif action == "leave_queue":
                await self.leave_queue(websocket)
            elif action == "confirm_match":
                await self.confirm_match(
                    websocket,
                    data.get("loadout"),
                    data.get("mode", "casual"),
                    data.get("signature"),
                    data.get("publicKey")
                )
            elif action == "stop_game":
                # Only current player can stop
                if self.current_player_ws == websocket:
                    await self.end_game()
            elif action == "add_score":
                # In real app, this comes from Pi, but for dev we allow client sim
                # Allow sim only if playing
                if self.current_player_ws == websocket:
                    await self.add_score(data.get("score", 0))

    async def process_pi_message(self, websocket: WebSocket, message: dict):
        """Handle incoming messages from PI"""
        # message is a dictionary from receive()
        
        if "bytes" in message:
            data = message["bytes"]
            
            # Debug Print every 30 frames
            self.frame_count += 1
            if self.frame_count % 30 == 0:
                print(f"Server received video frame {self.frame_count} ({len(data)} bytes)")

            # 1. Forward raw video to clients
            await self.broadcast_to_clients(data)
            
            # 2. Server-side CV processing (Offloaded)
            try:
                # Process every 3rd frame (Offloaded to thread to prevent loop blocking)
                if self.frame_count % 3 == 0:
                    loop = asyncio.get_running_loop()
                    # Run blocking CV code in a thread pool
                    qr_results = await loop.run_in_executor(None, process_frame_for_qr, data)
                    
                    # Broadcast results (even if empty, to clear previous boxes)
                    json_payload = json.dumps({
                        "type": "qr_detected",
                        "data": qr_results
                    })
                    
                    # Broadcast to all clients
                    for connection in self.active_connections:
                        try:
                            await connection.send_text(json_payload)
                        except:
                            pass
                            
            except Exception as e:
                 print(f"CV Error: {e}")
        
        elif "text" in message:
            print(f"Warning: Received TEXT from Pi: {message['text']}")
