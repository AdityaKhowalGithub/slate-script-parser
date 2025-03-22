import re
import json
from typing import Dict, Any, List, Set

def extract_text_from_pdf(pdf_path):
    """
    Extract text from a PDF file.
    This function is included here for consistency but is defined in the API.
    """
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def parse_screenplay(script, title):
    """
    Parse screenplay text into structured data.
    Two-pass approach:
    1. First pass: Identify scenes and dialogue characters
    2. Second pass: Look for already-identified characters in action text
    
    Args:
        script: The text content of the screenplay
        title: The title of the screenplay
        
    Returns:
        Dictionary containing the structured screenplay data
    """
    # Regex patterns
    scene_pattern = re.compile(r'^\s*(\d+\.\s*)?(INT\.|EXT\.|INT/EXT\.|INT/EXT)')
    character_pattern = re.compile(r"^[A-Z][A-Z\s]+$")
    
    # Blocked words for character detection - expanded list
    BLOCKED_WORDS = {
        # Scene elements
        "INT", "EXT", "CUT", "FADE", "DISSOLVE", "VOICE", "TITLE",
        "TO:", "ANGLE", "TITLE", "OVER", "BY", "END", "CONT'D", 
        "THE END", "SCENE", "CONTINUED", "TRANSITION", "FLASHBACK",
        "CREDITS", "CREDIT", "SCRIPT", "FADE IN", "FADE OUT",
        "DISSOLVE TO", "CUT TO", "SMASH CUT", "INTERCUT", "SUPER",
        "MONTAGE", "SERIES OF SHOTS", "BACK TO SCENE", "PRELAP",
        "TREATMENT", "SCREENPLAY",
        
        # Technical directions
        "ANGLE ON", "CLOSE ON", "CLOSE UP", "WIDE ON", "PAN TO", "TRACK",
        "CAMERA", "DOLLY", "SLOW MOTION", "TIME LAPSE", "AERIAL VIEW",
        "POV", "POINT OF VIEW", "SPLIT SCREEN", "MUSIC", "SOUND", "BLACK",
        "BLACKNESS", "DARKNESS", "LIGHT", "HOLD", "CONTINUOUS", "TRACKING",
        "MOVING", "FOLLOWING", "BACK TO", "SAME TIME", "LATER", "FLASHBACK",
        "FLASH CUT", "BLUR", "FOCUS", "FOREGROUND", "BACKGROUND",
        "OPENING", "CLOSING", "PREVIOUSLY", "SUBTITLE", "MESSAGE", "WE SEE",
        "WE HEAR", "SERIES OF", "ESTABLISHING", "SHOT OF", "DREAM SEQUENCE",
        "AWAIT INSTRUCTIONS"
        
        # Common production elements
        "PRESENT", "PRESENTS", "PRODUCTION", "PRODUCED", "DIRECTED",
        "WRITTEN", "STARRING", "CAST", "CREW", "PRODUCER", "DIRECTOR",
        "WRITER", "PRODUCTIONS", "PICTURES", "STUDIO", "PRESENTS", 
        "SUPER", "CHYRON", "TITLE CARD",
        
        # Generic terms often in all caps
        "NOTE", "IMPORTANT", "WARNING", "CAUTION", "NOTICE", "ATTENTION",
        "HELLO", "HEY", "YES", "NO", "WAIT", "STOP", "GO", "LOOK", "LISTEN"
    }
    
    # Common character name misspellings and variations
    CHARACTER_ALIASES = {
        # Add other known character variations here
    }
    
    # Words that indicate non-character elements even if they look like character cues
    TECHNICAL_PHRASES = [
        "WIDE ON", "ANGLE ON", "CUT TO", "FADE IN", "FADE OUT", "DISSOLVE TO",
        "SMASH CUT", "PRELAP", "HOLD IN", "BACK TO", "CLOSE ON", "CLOSE UP",
        "PAN TO", "TRACK TO", "DOLLY IN", "SLOW MOTION", "TIME LAPSE", "AERIAL VIEW",
        "POINT OF VIEW", "SPLIT SCREEN", "MONTAGE", "SERIES OF", "FOLLOWING",
        "SAME TIME", "LATER", "CONTINUOUS", "PREVIOUSLY", "WE SEE", "WE HEAR",
        "ANGLE OF", "VIEW OF", "IN BLACK", "SHOT OF", "DREAM SEQUENCE"
    ]
    
    # Time of day mapping
    time_mapping = {
        "MORNING": "MORNING",
        "DAY": "DAY",
        "AFTERNOON": "AFTERNOON",
        "EVENING": "EVENING",
        "NIGHT": "NIGHT",
        "DAWN": "DAWN",
        "DUSK": "DUSK",
        "CONTINUOUS": "CONTINUOUS",
        "LATER": "LATER",
        "MOMENTS LATER": "MOMENTS_LATER",
        "SAME TIME": "SAME_TIME"
    }
    
    # Constants for page calculation
    DIALOGUE_LINES_PER_PAGE = 45
    ACTION_LINES_PER_PAGE = 58
    
    #-----------------------------------------------------------------------
    # Helper functions
    #-----------------------------------------------------------------------
    
    def is_character_name(line):
        """
        Determine if a line is a valid character name.
        More aggressive filtering to avoid technical directions and scene elements.
        """
        stripped = line.strip()
        
        # Too many words
        if len(stripped.split()) > 5:
            return False
        
        # Contains any blocked words
        for word in BLOCKED_WORDS:
            if word in stripped.upper():
                # Special case: if the blocked word is a substring but not a full match,
                # continue checking (e.g., "INTERIOR" shouldn't match "INTERIOR DESIGNER")
                if word != stripped.upper() and not re.search(r'\b' + word + r'\b', stripped.upper()):
                    continue
                return False
        
        # Not enough alpha characters
        alpha_count = sum(1 for c in stripped if c.isalpha())
        if alpha_count < 2:
            return False
            
        # Must match character pattern (all caps) but allow for some parenthetical content
        base_name = re.sub(r"\(.*?\)", "", stripped).strip()
        if not character_pattern.match(base_name):
            return False
            
        # Clean parenthetical elements like (O.S.) or (V.O.)
        clean_name = re.sub(r"\(.*?\)", "", stripped).strip()
        if not clean_name:
            return False
        
        # Check if it looks like a scene heading despite passing other checks
        if scene_pattern.match(clean_name):
            return False
            
        # Check for technical phrases that might be mistaken for character names
        for phrase in TECHNICAL_PHRASES:
            if clean_name.startswith(phrase) or clean_name.endswith(phrase) or phrase in clean_name:
                return False
                
        # Exclude generic instructions that are often in all caps
        if clean_name in ["MUSIC", "SOUND", "BLACK", "CONTINUOUS", "SAME", "LATER", 
                         "INSTRUCTIONS", "AWAIT", "GATHER", "HOLD", "PRESENTS"]:
            return False
                
        # Exclude phrases that contain common technical terms
        if any(term in clean_name for term in ["PRESENTS", "IN BLACK", "PRODUCTION", "MUSIC", "SOUND", 
                                              "FADE", "CUT", "DISSOLVE", "TRACK", "PAN", "WIDE"]):
            return False
        
        # This appears to be a valid character name
        return True

    def normalize_character_name(name):
        """
        Normalize character names to handle variations and misspellings.
        """
        # Remove any parenthetical elements
        clean_name = re.sub(r"\(.*?\)", "", name).strip()
        
        # Use alias mapping if available
        if clean_name in CHARACTER_ALIASES:
            return CHARACTER_ALIASES[clean_name]
        
        return clean_name
    
    def extract_time(text):
        """Helper function to extract time of day from scene heading"""
        # Check parentheses first
        if "(" in text and ")" in text:
            paren_match = re.search(r'\((.*?)\)', text)
            if paren_match:
                time_part = paren_match.group(1).strip().upper()
                # Direct mapping check
                if time_part in time_mapping:
                    return time_mapping[time_part]
                # Handle variations
                if "CONT" in time_part or time_part == "CONT'D":
                    return "CONTINUOUS"
                if "LATER" in time_part:
                    return "MOMENTS_LATER" if "MOMENTS" in time_part else "LATER"
                if "SAME" in time_part and "TIME" in time_part:
                    return "SAME_TIME"

        # Check after dash
        if "-" in text:
            time_part = text.split("-", 1)[1].strip().upper()
            # Remove any parentheses
            time_part = re.sub(r'\(.*?\)', '', time_part).strip()
            
            # Direct mapping check
            if time_part in time_mapping:
                return time_mapping[time_part]
            
            # Handle variations
            if "CONT" in time_part or time_part == "CONT'D":
                return "CONTINUOUS"
            if "LATER" in time_part:
                return "MOMENTS_LATER" if "MOMENTS" in time_part else "LATER"
            if "SAME" in time_part and "TIME" in time_part:
                return "SAME_TIME"
        
        return "UNKNOWN"

    def calculate_page_count(scene_lines):
        """Calculate page count based on line types"""
        dialogue_lines = 0
        action_lines = 0
        in_dialogue = False
        
        for line in scene_lines:
            stripped = line.strip()
            if not stripped:
                continue
                
            # Check if this is a character name
            if character_pattern.match(stripped) and not scene_pattern.match(stripped):
                in_dialogue = True
                dialogue_lines += 1
                continue
                
            # Count dialogue or action lines
            if in_dialogue:
                if not stripped:
                    in_dialogue = False
                else:
                    dialogue_lines += 1
            else:
                action_lines += 1
        
        # Calculate pages based on line type ratios
        dialogue_pages = dialogue_lines / DIALOGUE_LINES_PER_PAGE
        action_pages = action_lines / ACTION_LINES_PER_PAGE
        return round(dialogue_pages + action_pages, 2)
    
    #-----------------------------------------------------------------------
    # First pass: Identify scenes and dialogue characters
    #-----------------------------------------------------------------------
    lines = script.split('\n')
    scenes = []
    scene_buffers = []  # Store raw text for each scene
    all_characters = set()  # All characters found in dialogue
    
    current_scene = None
    current_characters = set()
    scene_buffer = []
    line_count = 0
    current_page_count = 0.0
    in_first_scene = False  # Flag to track if we've found the first scene yet
    
    for line in lines:
        stripped_line = line.strip()
        
        # Identify new scenes
        if scene_pattern.match(stripped_line):
            # Process previous scene
            if current_scene:
                current_scene["characters"] = list(current_characters)
                current_scene["line_count"] = line_count
                
                # Calculate page metrics
                page_count = calculate_page_count(scene_buffer)
                current_scene["page_count"] = page_count
                current_scene["start_page"] = current_page_count
                current_scene["end_page"] = current_page_count + page_count
                
                scenes.append(current_scene)
                scene_buffers.append(scene_buffer)
                current_page_count += page_count
                scene_buffer = []

            # Extract scene components
            location_text = stripped_line
            scene_type = "INTERIOR" if "INT." in location_text.upper() and "INT/EXT" not in location_text.upper() else \
                       "EXTERIOR" if "EXT." in location_text.upper() and "INT/EXT" not in location_text.upper() else \
                       "INTERIOR_EXTERIOR"
            
            # Remove scene number if present
            if re.match(r'^\d+\.', location_text):
                location_text = re.sub(r'^\d+\.\s*', '', location_text)
            
            # Extract time of day
            time_of_day = extract_time(location_text)
            
            # Clean up location
            clean_location = re.sub(r'^(INT\.|EXT\.|INT/EXT\.|INT/EXT)\s*', '', location_text)
            if "-" in clean_location:
                clean_location = clean_location.split("-")[0]
            clean_location = re.sub(r'\(.*?\)', '', clean_location)
            clean_location = clean_location.strip()
            
            current_scene = {
                "scene_number": len(scenes) + 1,
                "type": scene_type,
                "location": clean_location,
                "time_of_day": time_of_day,
                "raw_heading": stripped_line,
                "characters": [],
                "line_count": 0,
                "page_count": 0.0,
                "start_page": current_page_count,
                "end_page": 0.0,
            }
            current_characters = set()
            line_count = 0
            in_first_scene = True
            
        # Add line to scene buffer
        if current_scene:
            scene_buffer.append(line)
            line_count += 1

        # Identify characters from dialogue - but only after we've found the first scene
        if in_first_scene and is_character_name(stripped_line):
            # Clean and normalize the character name
            clean_name = normalize_character_name(stripped_line)
            current_characters.add(clean_name)
            all_characters.add(clean_name)

    # Process the last scene
    if current_scene:
        current_scene["characters"] = list(current_characters)
        current_scene["line_count"] = line_count
        
        # Calculate page metrics for last scene
        page_count = calculate_page_count(scene_buffer)
        current_scene["page_count"] = page_count
        current_scene["start_page"] = current_page_count
        current_scene["end_page"] = current_page_count + page_count
        
        scenes.append(current_scene)
        scene_buffers.append(scene_buffer)
        current_page_count += page_count
    
    # Normalize character list to remove duplicates and misspellings
    normalized_characters = set()
    for character in all_characters:
        normalized_characters.add(normalize_character_name(character))
    all_characters = normalized_characters
    
    #-----------------------------------------------------------------------
    # Second pass: Look for already-identified characters in action description
    #-----------------------------------------------------------------------
    
    # Build a list of all characters found in dialogue
    character_list = list(all_characters)
    
    # For each scene, scan the action text for known character names
    for i, (scene, buffer) in enumerate(zip(scenes, scene_buffers)):
        # Convert to normalized character names
        scene_characters = set(normalize_character_name(char) for char in scene["characters"])
        scene_text = " ".join(buffer)  # Join all lines for easier text search
        
        # Check each known character to see if they're mentioned
        for character in character_list:
            # Skip if character is already in this scene
            if character in scene_characters:
                continue
                
            # Look for exact character name (need to be careful with partial matches)
            # We use word boundaries to avoid partial matches
            if re.search(r'\b' + re.escape(character) + r'\b', scene_text):
                scene_characters.add(character)
        
        # Update the scene with any newly found characters
        scenes[i]["characters"] = list(scene_characters)
    
    #-----------------------------------------------------------------------
    # Calculate character statistics
    #-----------------------------------------------------------------------
    character_stats = []
    for character in sorted(list(all_characters)):
        # Count scenes per character
        scene_appearances = []
        line_count = 0
        
        for scene_idx, scene in enumerate(scenes):
            normalized_scene_chars = [normalize_character_name(char) for char in scene["characters"]]
            if character in normalized_scene_chars:
                scene_appearances.append(scene_idx + 1)  # 1-based scene numbers
        
        # Count lines (approximate)
        for buffer in scene_buffers:
            for line_idx, line in enumerate(buffer):
                normalized_line = normalize_character_name(line.strip())
                if normalized_line == character:
                    line_count += 1  # Count the character cue
                    # Count the lines of dialogue that follow
                    dialogue_count = 0
                    for following_line in buffer[line_idx+1:]:
                        if not following_line.strip():
                            continue
                        if is_character_name(following_line):
                            break
                        dialogue_count += 1
                    line_count += dialogue_count
        
        character_stats.append({
            "name": character,
            "scene_appearances": scene_appearances,
            "total_lines": max(1, line_count)  # Ensure at least 1 line
        })
    
    return {
        "screenplay": {
            "title": title,
            "scenes": scenes,
            "characters": character_stats,
            "all_characters": sorted(list(all_characters)),
            "total_pages": round(current_page_count, 2)
        }
    }

def screenplay_to_json(screenplay_data, output_file):
    """
    Save screenplay data to a JSON file.
    
    Args:
        screenplay_data: The parsed screenplay data
        output_file: Path to save the JSON file
    """
    with open(output_file, 'w', encoding='utf-8') as json_file:
        json.dump(screenplay_data, json_file, indent=4, ensure_ascii=False)

def debug_parse(script, title=None, verbose=True):
    """
    Parse a screenplay with debugging information.
    
    Args:
        script: Script text content
        title: Script title (defaults to "Debug Script")
        verbose: Whether to print detailed information
        
    Returns:
        The parsed screenplay data
    """
    if title is None:
        title = "Debug Script"
        
    if verbose:
        print(f"Parsing script: {title}")
        print(f"Script length: {len(script)} characters")
        
    # Track what we find
    scene_headings = []
    dialogue_characters = []
    rejected_characters = []
    
    # Use patterns from parse_screenplay
    scene_pattern = re.compile(r'^\s*(\d+\.\s*)?(INT\.|EXT\.|INT/EXT\.|INT/EXT)')
    character_pattern = re.compile(r"^[A-Z][A-Z\s]+$")
    
    # First pass - identify scenes and dialogue characters
    lines = script.split("\n")
    in_scene = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
            
        # Check for scene heading
        if scene_pattern.match(stripped):
            if verbose:
                print(f"Line {i+1}: Scene heading found: {stripped}")
            scene_headings.append((i+1, stripped))
            in_scene = True
            
        # Only look for characters within scenes
        if not in_scene:
            continue
            
        # Character detection
        clean_name = re.sub(r"\(.*?\)", "", stripped).strip()
        if character_pattern.match(clean_name):
            if len(clean_name.split()) <= 5 and len(clean_name) <= 40:
                from format_parsers import is_character_name
                if is_character_name(stripped):
                    if verbose:
                        print(f"Line {i+1}: Character found: {stripped}")
                    dialogue_characters.append((i+1, stripped))
                else:
                    if verbose:
                        print(f"Line {i+1}: Rejected as character: {stripped}")
                    rejected_characters.append((i+1, stripped))
    
    if verbose:
        print(f"\nFound {len(scene_headings)} scene headings")
        print(f"Found {len(dialogue_characters)} dialogue character cues")
        print(f"Rejected {len(rejected_characters)} false character cues")
        
    # Parse the full screenplay
    result = parse_screenplay(script, title)
    
    if verbose:
        print(f"\nParsed {len(result['screenplay']['scenes'])} scenes")
        print(f"Parsed {len(result['screenplay']['all_characters'])} characters")
        
        # Print scene summary
        print("\nScene Summary:")
        for i, scene in enumerate(result['screenplay']['scenes']):
            print(f"Scene {i+1}: {scene['type']} - {scene['location']} - {scene['time_of_day']}")
            print(f"  Characters: {', '.join(scene['characters'])}")
            print(f"  Lines: {scene['line_count']}, Pages: {scene['page_count']:.2f}")
            
        # Print character summary
        print("\nCharacter Summary:")
        for char in result['screenplay']['characters']:
            print(f"{char['name']}: {len(char['scene_appearances'])} scenes, {char['total_lines']} lines")
            
    return result

def detect_character_issues(screenplay_data):
    """
    Analyze a parsed screenplay for potential character detection issues.
    
    Args:
        screenplay_data: The parsed screenplay data
        
    Returns:
        Dictionary with issue analysis
    """
    characters = screenplay_data["screenplay"]["all_characters"]
    scenes = screenplay_data["screenplay"]["scenes"]
    
    # Potentially problematic character names
    suspicious_terms = [
        "WIDE", "ANGLE", "CLOSE", "PAN", "TRACK", "DOLLY", "MOTION", "LAPSE",
        "VIEW", "BLACK", "SOUND", "MUSIC", "MONTAGE", "SERIES", "SHOTS",
        "SAME", "LATER", "CONTINUOUS", "FADE", "CUT", "DISSOLVE", "SMASH",
        "PRELAP", "HOLD", "BACK", "INSTRUCTIONS", "GATHER", "PRESENTS"
    ]
    
    potential_problems = []
    
    # Check for suspicious character names
    for character in characters:
        for term in suspicious_terms:
            if term in character:
                potential_problems.append({
                    "character": character,
                    "issue": f"Contains suspicious term '{term}'",
                    "recommendation": "May be a camera direction or technical instruction"
                })
                break
                
        # Check for very rare appearances
        char_scenes = 0
        for scene in scenes:
            if character in scene["characters"]:
                char_scenes += 1
        
        if char_scenes <= 1:
            potential_problems.append({
                "character": character,
                "issue": f"Only appears in {char_scenes} scene",
                "recommendation": "May be a misdetected camera direction or minor character"
            })
    
    # Check for similar character names that might be the same character
    for i, char1 in enumerate(characters):
        for char2 in characters[i+1:]:
            # Skip identical names
            if char1 == char2:
                continue
                
            # Check for common variations
            if char1 in char2 or char2 in char1:
                potential_problems.append({
                    "character": f"{char1} / {char2}",
                    "issue": "Similar character names",
                    "recommendation": "May be variations of the same character"
                })
                
            # Check for common misspellings
            elif (char1.replace("IE", "Y") == char2) or (char2.replace("IE", "Y") == char1):
                potential_problems.append({
                    "character": f"{char1} / {char2}",
                    "issue": "Possible spelling variation",
                    "recommendation": "May be misspellings of the same character"
                })
    
    return {
        "total_characters": len(characters),
        "potential_issues": len(potential_problems),
        "issues": potential_problems
    }