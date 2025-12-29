# app/api/juegos.py
from typing import Dict

# Almacén temporal para sesiones de juego (en producción usar Redis)
game_sessions: Dict[str, dict] = {}
