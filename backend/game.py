import json
import os
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional

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
    # Ranked Mode
    is_ranked: bool = False
    player_key: Optional[str] = None
