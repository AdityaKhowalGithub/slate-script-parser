from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from datetime import timedelta

class SceneType(Enum):
    INTERIOR = "INT"
    EXTERIOR = "EXT"
    INTERIOR_EXTERIOR = "INT/EXT"
    UNKNOWN = "UNKNOWN"

class TimeOfDay(Enum):
    MORNING = "MORNING"
    DAY = "DAY"
    AFTERNOON = "AFTERNOON"
    EVENING = "EVENING"
    NIGHT = "NIGHT"
    DAWN = "DAWN"
    DUSK = "DUSK"
    CONTINUOUS = "CONTINUOUS"
    LATER = "LATER"
    MOMENTS_LATER = "MOMENTS_LATER"
    SAME_TIME = "SAME_TIME"
    UNKNOWN = "UNKNOWN"

@dataclass
class Character:
    name: str
    scene_appearances: List[int] = field(default_factory=list)
    total_lines: int = 0

@dataclass
class Scene:
    id: int
    title: str
    scene_type: SceneType
    location: str
    time_of_day: TimeOfDay
    characters: List[Character] = field(default_factory=list)
    line_count: int = 0
    page_count: float = 0.0
    start_page: float = 0.0  # Page number where scene starts
    end_page: float = 0.0    # Page number where scene ends
    raw_text: str = ""
    description: str = ""  # New field for scene description
    estimated_duration: timedelta = field(default_factory=lambda: timedelta())

@dataclass
class ParsedScript:
    title: str
    format_type: str = "standard"
    scenes: List[Scene] = field(default_factory=list)
    characters: dict = field(default_factory=dict)  # Map of character name to Character object
    total_pages: float = 0.0  # Total script page count 