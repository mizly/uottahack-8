import json
import os
import time
import random
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

from .tracker import Tracker

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
    
    # Enemies & Tracking
    enemies: List[Dict] = field(default_factory=list)
    tracker: Tracker = field(default_factory=Tracker)

    def init_game(self, name: str, mode: str, p_class: str, key: str = None):
        self.is_active = True
        self.start_time = time.time()
        self.score = 0
        self.player_name = name
        self.is_ranked = (mode == 'ranked')
        self.player_key = key
        self.player_class = p_class
        
        # Reset Tracker
        self.tracker = Tracker()
        
        # Init Ammo (+50% increase)
        if p_class == 'interceptor':
            self.max_ammo = 90 # 60 * 1.5
        elif p_class == 'juggernaut':
            self.max_ammo = 15 # 10 * 1.5
        else:
            self.max_ammo = 45 # 30 * 1.5
        self.ammo = self.max_ammo
        
        # Init Enemies
        self.enemies = []
        callsigns = ["ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO", "FOXTROT"]
        for i in range(6):
            hp = random.randint(60, 150)
            self.enemies.append({
                "id": i,
                "name": callsigns[i], # This matches QR text
                "hp": hp,
                "max_hp": hp
            })

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
        
    def attempt_shot(self) -> Dict:
        """
        Fires a shot AND checks for targets.
        Returns dict with keys: 'fired' (bool), 'hits' (list of damaged enemy names)
        """
        result = {'fired': False, 'hits': []}
        
        if self.fire_ammo():
            result['fired'] = True
            
            # Check for targets in crosshair
            # Threshold 60px radius from center (approx 10% of width)
            targets = self.tracker.get_crosshair_targets(threshold=60)
            
            # Define Damage per class
            damage = 25
            if self.player_class == 'juggernaut': damage = 60
            elif self.player_class == 'interceptor': damage = 10
            
            callsigns = ["ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO", "FOXTROT"]
            
            for t in targets:
                raw_id = t['id']
                target_name = raw_id
                
                # Try to map enemy_N to Call Signs
                # e.g. "enemy_1" -> "ALPHA" (index 0)
                # "enemy_2" -> "BRAVO" (index 1)
                lower_id = raw_id.lower()
                if "enemy_" in lower_id:
                    try:
                        # Extract number
                        parts = lower_id.split('_')
                        if len(parts) > 1:
                            idx = int(parts[1]) - 1 # enemy_1 -> index 0
                            if 0 <= idx < len(callsigns):
                                target_name = callsigns[idx]
                    except:
                        pass
                
                # Find enemy object
                enemy = next((e for e in self.enemies if e['name'] == target_name), None)
                
                # Fallback: Check if raw_id matches directly (case insensitive?)
                if not enemy:
                     enemy = next((e for e in self.enemies if e['name'].lower() == target_name.lower()), None)

                if enemy and enemy['hp'] > 0:
                    self.apply_damage(enemy, damage)
                    result['hits'].append(enemy['name']) # Return the Game Name (ALPHA), not the QR text
                    
        return result

    def apply_damage(self, enemy, damage):
        enemy['hp'] = max(0, enemy['hp'] - damage)
        print(f"HIT {enemy['name']} for {damage} dmg! Remaining: {enemy['hp']}")
        
        if enemy['hp'] == 0:
            # Kill Bonus
            self.score += 100
            print(f"DESTROYED {enemy['name']}!")
            
            # Check if all enemies are dead
            if all(e['hp'] == 0 for e in self.enemies):
                print("Squad Wipe! Respawning enemies and refilling ammo...")
                # Refill Ammo
                self.ammo = self.max_ammo
                
                for e in self.enemies:
                    # Randomize HP on respawn? Let's use the same logic as init
                    respawn_hp = random.randint(60, 150)
                    e['hp'] = respawn_hp
                    e['max_hp'] = respawn_hp

