import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from typing import List, Optional

app = FastAPI()

class ConnectionManager:
    def __init__(self):
        self.client_ws: Optional[WebSocket] = None
        self.pi_ws: Optional[WebSocket] = None

    async def connect(self, websocket: WebSocket, client_type: str):
        await websocket.accept()
        if client_type == "client":
            self.client_ws = websocket
            print("Web Client Connected")
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
            data = await websocket.receive_bytes()
            # If data comes from client, send to pi (Control Data)
            if client_type == "client":
                # Print control bytes for debugging
                if len(data) == 8:
                    analog = list(data[:6])
                    # Parse 16-bit buttons
                    buttons_int = int.from_bytes(data[6:], byteorder='little')
                    buttons_bin = f"{buttons_int:016b}"[::-1]
                    #print(f"Control Data: Analog={analog} Buttons={buttons_bin} Raw={list(data)}")
                    print(f"Control Data: Analog={analog} Buttons={buttons_bin}")
                elif len(data) < 20:  # Only print small control packets
                    print(f"Control Data: {list(data)}")
                await manager.broadcast_to_pi(data)
            
            # If data comes from pi, send to client (Video Data)
            elif client_type == "pi":
                # print(f"Video Frame Size: {len(data)}") # Optional: Uncomment to see video traffic
                await manager.broadcast_to_client(data)
                
    except WebSocketDisconnect:
        manager.disconnect(client_type)
    except Exception as e:
        print(f"Error in {client_type}: {e}")
        manager.disconnect(client_type)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
