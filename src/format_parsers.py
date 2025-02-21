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

    # Standard screenplay formatting constants
    LINES_PER_PAGE = 55  # Standard screenplay format
    DIALOGUE_LINES_PER_PAGE = 45  # Dialogue takes more vertical space
    ACTION_LINES_PER_PAGE = 58    # Action blocks are more compact
    
    def parse(self, content: str, title: str) -> ParsedScript:
        script = ParsedScript(title=title, format_type="standard")
        
        lines = content.split("\n")
        current_scene = None
        scene_buffer: List[str] = []
        active_character = None
        current_page_count = 0.0

        for original_line in lines:
            stripped_line = original_line.strip()
            if not stripped_line:
                continue

            # SCENE HEADING CHECK
            if self._is_scene_heading(stripped_line):
                # Finalize previous scene if present
                if current_scene:
                    self._process_scene(current_scene, scene_buffer, script, current_page_count)
                    current_page_count += current_scene.page_count
                    scene_buffer = []

                current_scene = Scene(
                    id=len(script.scenes) + 1,
                    title=f"Scene {len(script.scenes) + 1}",
                    scene_type=self._extract_scene_type(stripped_line),
                    location=self._extract_location(stripped_line),
                    time_of_day=self._extract_time(stripped_line),
                    start_page=current_page_count
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
            self._process_scene(current_scene, scene_buffer, script, current_page_count)
            current_page_count += current_scene.page_count

        # Set total pages for the script
        script.total_pages = current_page_count
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
        Extract just the location part, removing:
        1. INT/EXT prefix
        2. Any time-of-day suffix
        Example: "INT. SPACE SHUTTLE COCKPIT - DAY" -> "SPACE SHUTTLE COCKPIT"
        """
        # First remove the INT/EXT prefix
        location_part = re.sub(r"^(INT\.|EXT\.|INT/EXT\.|INT/EXT)\s*", "", scene_text, flags=re.IGNORECASE)
        
        # Remove any time of day indicators that follow a dash
        if "-" in location_part:
            location_part = location_part.split("-")[0]
            
        # Clean up any remaining whitespace
        location_part = location_part.strip()
        
        return location_part

    def _extract_time(self, scene_text: str) -> TimeOfDay:
        """
        Extract time-of-day from the part after a dash (e.g., DAY, NIGHT, CONTINUOUS).
        Handles various time formats and special cases like CONTINUOUS or MOMENTS LATER.
        """
        # Standard time mapping
        mapping = {
            "MORNING": TimeOfDay.MORNING,
            "DAY": TimeOfDay.DAY,
            "AFTERNOON": TimeOfDay.AFTERNOON,
            "EVENING": TimeOfDay.EVENING,
            "NIGHT": TimeOfDay.NIGHT,
            "DAWN": TimeOfDay.DAWN,
            "DUSK": TimeOfDay.DUSK,
            "CONTINUOUS": TimeOfDay.CONTINUOUS,
            "LATER": TimeOfDay.LATER,
            "MOMENTS LATER": TimeOfDay.MOMENTS_LATER,
            "SAME TIME": TimeOfDay.SAME_TIME,
        }

        # If no dash, check for special cases in parentheses
        if "(" in scene_text and ")" in scene_text:
            paren_content = re.search(r'\((.*?)\)', scene_text)
            if paren_content:
                time_part = paren_content.group(1).strip().upper()
                # Check if parenthetical content matches any time indicator
                if time_part in mapping:
                    return mapping[time_part]
                # Handle variations of CONTINUOUS
                if "CONT" in time_part or time_part == "CONT'D":
                    return TimeOfDay.CONTINUOUS
                # Handle variations of LATER
                if "LATER" in time_part:
                    if "MOMENTS" in time_part or "MOMENT" in time_part:
                        return TimeOfDay.MOMENTS_LATER
                    return TimeOfDay.LATER
                if "SAME" in time_part and "TIME" in time_part:
                    return TimeOfDay.SAME_TIME

        # Check for time after dash
        if "-" in scene_text:
            time_part = scene_text.split("-", 1)[1].strip().upper()
            # Remove any parentheses
            time_part = re.sub(r'\(.*?\)', '', time_part).strip()
            
            # Direct mapping check
            if time_part in mapping:
                return mapping[time_part]
            
            # Handle variations
            if "CONT" in time_part or time_part == "CONT'D":
                return TimeOfDay.CONTINUOUS
            if "LATER" in time_part:
                if "MOMENTS" in time_part or "MOMENT" in time_part:
                    return TimeOfDay.MOMENTS_LATER
                return TimeOfDay.LATER
            if "SAME" in time_part and "TIME" in time_part:
                return TimeOfDay.SAME_TIME

        return TimeOfDay.UNKNOWN

    def _calculate_page_count(self, scene_buffer: List[str]) -> float:
        """
        Calculate page count more accurately based on line types:
        - Dialogue lines take more space
        - Action blocks are more compact
        - Scene headings and transitions count as action lines
        """
        dialogue_line_count = 0
        action_line_count = 0
        
        in_dialogue = False
        for line in scene_buffer:
            stripped = line.strip()
            
            # Skip empty lines
            if not stripped:
                continue
                
            # Check if this is a character name (all caps, not a scene heading)
            if re.match(r"^[A-Z][A-Z\s]+$", stripped) and not any(
                heading in stripped for heading in ["INT.", "EXT.", "INT/EXT"]
            ):
                in_dialogue = True
                dialogue_line_count += 1
                continue
            
            # If we're in dialogue, count as dialogue lines until empty line
            if in_dialogue:
                if not stripped:
                    in_dialogue = False
                else:
                    dialogue_line_count += 1
            else:
                action_line_count += 1
        
        # Calculate pages based on line type ratios
        dialogue_pages = dialogue_line_count / self.DIALOGUE_LINES_PER_PAGE
        action_pages = action_line_count / self.ACTION_LINES_PER_PAGE
        
        return round(dialogue_pages + action_pages, 2)

    def _process_scene(self, scene: Scene, scene_buffer: List[str], script: ParsedScript, current_page_count: float):
        """
        Finalize the scene's metrics including accurate page count and page ranges.
        """
        scene.line_count = len(scene_buffer)
        scene.raw_text = "\n".join(scene_buffer)
        
        # Calculate more accurate page count
        scene.page_count = self._calculate_page_count(scene_buffer)
        
        # Set page range
        scene.start_page = current_page_count
        scene.end_page = current_page_count + scene.page_count
        
        # Calculate estimated duration based on the new page count
        scene.estimated_duration = self._estimate_duration(scene.line_count, scene.page_count)
        
        script.scenes.append(scene) 