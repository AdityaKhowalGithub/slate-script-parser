import PyPDF2
import re
import pdfplumber
import json

def extract_text_from_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def parse_screenplay(script, title):
    scenes = []
    all_characters = set()
    current_scene = None
    current_characters = set()
    lines = script.split("\n")
    scene_pattern = re.compile(r'^\s*(\d+\.\s*)?(INT\.|EXT\.|INT/EXT\.)')
    character_pattern = re.compile(r"^[A-Z][A-Z\s]+$")
    current_character = None
    line_count = 0
    current_page_count = 0.0
    
    # Constants for page calculation
    DIALOGUE_LINES_PER_PAGE = 45
    ACTION_LINES_PER_PAGE = 58

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

    scene_buffer = []
    for line in lines:
        # Identify new scenes
        if scene_pattern.match(line):
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
                current_page_count += page_count
                scene_buffer = []

            # Extract scene components
            location_text = line.strip()
            scene_type = "INTERIOR" if "INT." in location_text.upper() else "EXTERIOR" if "EXT." in location_text.upper() else "INTERIOR_EXTERIOR"
            
            # Remove scene number if present
            if re.match(r'^\d+\.', location_text):
                location_text = re.sub(r'^\d+\.\s*', '', location_text)
            
            # Extract time of day
            time_of_day = extract_time(location_text)
            
            # Clean up location
            clean_location = re.sub(r'^(INT\.|EXT\.|INT/EXT\.)\s*', '', location_text)
            if "-" in clean_location:
                clean_location = clean_location.split("-")[0]
            clean_location = re.sub(r'\(.*?\)', '', clean_location)
            clean_location = clean_location.strip()
            
            current_scene = {
                "scene_number": len(scenes) + 1,
                "type": scene_type,
                "location": clean_location,
                "time_of_day": time_of_day,
                "raw_heading": line.strip(),
                "characters": [],
                "line_count": 0,
                "page_count": 0.0,
                "start_page": current_page_count,
                "end_page": 0.0,
            }
            current_characters = set()
            line_count = 0
            
        # Add line to scene buffer
        if current_scene:
            scene_buffer.append(line)
            line_count += 1

        # Identify characters
        if character_pattern.match(line.strip()) and not line.strip().endswith(":"):
            current_character = line.strip()
            current_characters.add(current_character)
            all_characters.add(current_character)

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
        current_page_count += page_count

    return {
        "screenplay": {
            "title": title,
            "scenes": scenes,
            "all_characters": sorted(list(all_characters)),
            "total_pages": round(current_page_count, 2)
        }
    }

def screenplay_to_json(screenplay_data, output_file):
    with open(output_file, 'w', encoding='utf-8') as json_file:
        json.dump(screenplay_data, json_file, indent=4, ensure_ascii=False)