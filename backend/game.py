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
    
    # Ammo State
    ammo: int = 30
    max_ammo: int = 30
    last_fire_time: float = 0

    def init_game(self, name: str, mode: str, p_class: str, key: str = None):
        self.is_active = True
        self.start_time = time.time()
        self.score = 0
        self.player_name = name
        self.is_ranked = (mode == 'ranked')
        self.player_key = key
        self.player_class = p_class
        
        # Init Ammo
        if p_class == 'interceptor':
            self.max_ammo = 60
        elif p_class == 'juggernaut':
            self.max_ammo = 10
        else:
            self.max_ammo = 30
        self.ammo = self.max_ammo

    def fire_ammo(self) -> bool:
        """Returns True if a shot was fired successfully (ammo > 0 and not on cooldown)."""
        now = time.time()
        # Cooldown Logic
        cooldown = 0.5
        if self.player_class == 'interceptor': cooldown = 0.2
        if self.player_class == 'juggernaut': cooldown = 1.0
        
        if now - self.last_fire_time < cooldown:
            return False
            
        if self.ammo > 0:
            self.ammo -= 1
            self.last_fire_time = now
            return True
        return False
