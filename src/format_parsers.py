from abc import ABC, abstractmethod
import re
from typing import List, Tuple, Optional, Set, Dict
from datetime import timedelta
import os
from functools import lru_cache
import json
from dotenv import load_dotenv
import requests
from azure.core.credentials import AzureKeyCredential
import time
import uuid
from azure.storage.blob import BlobServiceClient
import logging

from models import (
    ParsedScript,
    Scene,
    Character,
    TimeOfDay,
    SceneType,
    CrewRequirement
)

load_dotenv()  # Load environment variables from .env

logger = logging.getLogger(__name__)

class ScriptParser(ABC):
    """Abstract base class for script parsers."""
    
    @abstractmethod
    def parse(self, content: str, title: str) -> ParsedScript:
        """Parse the script content and return a ParsedScript object."""
        pass

    def _estimate_duration(self, line_count: int, page_count: float) -> timedelta:
        """Estimate scene filming duration based on industry standards.
        Currently, it assumes a multiplier of 3 minutes per page.
        """
        multiplier = 3  # minutes per page, adjust as needed
        base_minutes = max(0.5, page_count * multiplier)
        return timedelta(minutes=base_minutes)

class LocalRegexParser(ScriptParser):
    """
    A more strict LocalRegexParser focusing on:
      - Better punctuation removal.
      - Stricter uppercase ratio checks.
      - Blocking specific words / phrases (like 'BY', 'THE END') more thoroughly.
      - Trying to avoid false positives (like "comm)", "keyboard.", etc.).
    """

    # Known words or phrases commonly found in scripts but not character names
    BLOCKED_WORDS = {
        "INT", "EXT", "CUT", "FADE", "DISSOLVE", "VOICE",
        "TO:", "ANGLE", "TITLE", "OVER", "BY", "END",
        "THE END", "SCENE", "CONTINUED", "TRANSITION",
        "CREDITS", "CREDIT", "SCRIPT"
    }

    # Regex pattern to strip typical punctuation from the start/end of lines
    # Including parentheses, quotes, punctuation, dashes, etc.
    PUNCTUATION_STRIP = r"""[\?\!\:\.\,\(\)'"''""\-]+"""

    def parse(self, content: str, title: str) -> ParsedScript:
        script = ParsedScript(title=title, format_type="standard")

        lines = content.split("\n")
        current_scene = None
        scene_buffer: List[str] = []
        active_character = None

        for original_line in lines:
            stripped_line = original_line.strip()
            if not stripped_line:
                continue

            # SCENE HEADING CHECK
            if self._is_scene_heading(stripped_line):
                # Finalize previous scene if present
                if current_scene:
                    self._process_scene(current_scene, scene_buffer, script)
                    scene_buffer = []

                current_scene = Scene(
                    id=len(script.scenes) + 1,
                    title=f"Scene {len(script.scenes) + 1}",
                    scene_type=self._extract_scene_type(stripped_line),
                    location=self._extract_location(stripped_line),
                    time_of_day=self._extract_time(stripped_line),
                )
                active_character = None
                scene_buffer.append(stripped_line)
                continue

            # CHARACTER NAME CHECK
            if current_scene and self._is_character_candidate(stripped_line):
                cleaned_name = self._clean_character_name(stripped_line)
                if cleaned_name:
                    logger.debug(f"Recognized character name '{cleaned_name}' from line: {original_line}")
                    active_character = cleaned_name
                    # Ensure character in dictionary
                    if active_character not in script.characters:
                        script.characters[active_character] = Character(name=active_character)
                    # Record the appearance if not already in this scene
                    char_obj = script.characters[active_character]
                    if current_scene.id not in char_obj.scene_appearances:
                        char_obj.scene_appearances.append(current_scene.id)
                        current_scene.characters.append(char_obj)
                else:
                    logger.debug(f"Rejected line as character name: {original_line}")
                    active_character = None
            else:
                active_character = None

            # Always add the line to the current scene buffer if in a scene
            if current_scene:
                scene_buffer.append(stripped_line)
                # If we found a valid character above, increment their line count
                if active_character:
                    script.characters[active_character].total_lines += 1

        # Finalize last scene
        if current_scene and scene_buffer:
            self._process_scene(current_scene, scene_buffer, script)

        return script

    def _is_scene_heading(self, line: str) -> bool:
        """
        Check if it starts with typical scene heading keywords (INT, EXT, INT/EXT, etc.).
        """
        pattern = r"^\s*(INT\.|EXT\.|INT/EXT\.|INT/EXT|INT|EXT)"
        return bool(re.match(pattern, line, re.IGNORECASE))

    def _is_character_candidate(self, line: str) -> bool:
        """
        Initial quick check to see if line could be a character name:
          1. Not too many words (<= 5).
          2. Contains at least some alphabetic chars.
          3. Does not contain certain blocked words or transitions.
        Further cleaning in _clean_character_name will finalize validity.
        """
        words = line.split()
        if len(words) > 5:
            return False

        if any(bword in line.upper() for bword in self.BLOCKED_WORDS):
            return False

        # Must have at least 2 alpha characters
        alpha_count = sum(1 for c in line if c.isalpha())
        if alpha_count < 2:
            return False

        return True

    def _clean_character_name(self, line: str) -> str:
        """
        Strip punctuation, parentheses, and evaluate uppercase ratio.
        Return a fully uppercase name if it passes all checks, else empty string.
        """
        # Remove leading/trailing punctuation
        line = re.sub(f"^{self.PUNCTUATION_STRIP}", "", line)
        line = re.sub(f"{self.PUNCTUATION_STRIP}$", "", line)
        # Remove internal parentheses content entirely (like (O.S.), (V.O.), etc.)
        line = re.sub(r"\(.*?\)", "", line).strip()

        if not line:
            return ""

        # If line EXACTLY matches or partially matches any blocked word, skip
        # e.g. "THE END" -> skip
        if line.upper() in self.BLOCKED_WORDS:
            return ""

        # Convert to uppercase
        upper_line = line.upper()

        # Now remove again any trailing punctuation that might have re-surfaced
        upper_line = re.sub(f"^{self.PUNCTUATION_STRIP}", "", upper_line)
        upper_line = re.sub(f"{self.PUNCTUATION_STRIP}$", "", upper_line).strip()

        # If still empty, skip
        if not upper_line:
            return ""

        # Check uppercase ratio
        alpha_count = sum(1 for c in upper_line if c.isalpha())
        uppercase_count = sum(1 for c in upper_line if c.isalpha() and c.isupper())
        if alpha_count == 0:
            return ""

        uppercase_ratio = uppercase_count / alpha_count

        # Additional skip if the name is ironically one of the blocked words
        if upper_line in self.BLOCKED_WORDS:
            return ""

        # If line has 2+ words and is less than 80% uppercase, skip it
        # Single-word character lines are common, so a single word can pass more easily
        word_count = len(upper_line.split())
        if word_count > 1 and uppercase_ratio < 0.8:
            return ""

        # Example final check: length limit to avoid huge lines as names
        if len(upper_line) > 40:
            return ""

        return upper_line

    def _extract_scene_type(self, scene_text: str) -> SceneType:
        """
        Infer scene type from the heading (INT, EXT, INT/EXT).
        """
        text_up = scene_text.upper()
        if "INT." in text_up:
            return SceneType.INTERIOR
        elif "EXT." in text_up:
            return SceneType.EXTERIOR
        elif "INT/EXT." in text_up or "INT/EXT" in text_up:
            return SceneType.INTERIOR_EXTERIOR
        return SceneType.UNKNOWN

    def _extract_location(self, scene_text: str) -> str:
        """
        Remove INT/EXT prefix and any trailing time-of-day info after a dash.
        """
        location_part = re.sub(r"^(INT\.|EXT\.|INT/EXT\.|INT/EXT)\s*", "", scene_text, flags=re.IGNORECASE)
        # If there's a dash, we assume what's after might be time info
        if "-" in location_part:
            location_part = location_part.split("-", 1)[0]
        return location_part.strip()

    def _extract_time(self, scene_text: str) -> TimeOfDay:
        """
        Extract time-of-day from the part after a dash (e.g., DAY, NIGHT).
        """
        if "-" not in scene_text:
            return TimeOfDay.UNKNOWN
        time_part = scene_text.split("-", 1)[1].strip().upper()
        mapping = {
            "MORNING": TimeOfDay.MORNING,
            "DAY": TimeOfDay.DAY,
            "AFTERNOON": TimeOfDay.AFTERNOON,
            "EVENING": TimeOfDay.EVENING,
            "NIGHT": TimeOfDay.NIGHT,
            "DAWN": TimeOfDay.DAWN,
            "DUSK": TimeOfDay.DUSK,
        }
        return mapping.get(time_part, TimeOfDay.UNKNOWN)

    def _process_scene(self, scene: Scene, scene_buffer: List[str], script: ParsedScript):
        """
        Finalize the scene's line_count, page_count, etc. then add it to the script.
        """
        scene.line_count = len(scene_buffer)
        scene.raw_text = "\n".join(scene_buffer)
        scene.page_count = scene.line_count / 55.0  # approximate lines per page
        scene.estimated_duration = self._estimate_duration(scene.line_count, scene.page_count)
        script.scenes.append(scene) 