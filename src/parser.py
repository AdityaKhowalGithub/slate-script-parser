import PyPDF2
import re

#this method takes the pdf and turns it into plain text so that the parser can do its thing
def extract_text_from_pdf(pdf_path):
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ''
        for page in pdf_reader.pages:
            text += page.extract_text()
    return text

#parser
def parse_screenplay(script, title):
    scenes = []
    characters = {}
    current_scene = None
    current_characters = set()
    dialogue_interactions = {}
    lines = script.split("\n")
    scene_pattern = re.compile(r"^\s*(INT\.|EXT\.)")
    character_pattern = re.compile(r"^[A-Z][A-Z\s]+$")
    dialogue_pattern = re.compile(r"^\s{10,}")
    current_character = None
    for line in lines:
        # Identify new scenes
        if scene_pattern.match(line):
            if current_scene:
                current_scene["characters"] = list(current_characters)
                scenes.append(current_scene)
            current_scene = {
                "scene_number": len(scenes) + 1,
                "location": line.strip(),
                "characters": [],
            }
            current_characters = set()
        # Identify characters and their dialogues
        elif character_pattern.match(line.strip()) and not line.strip().endswith(":"):
            current_character = line.strip()
            if current_character not in characters:
                characters[current_character] = {
                    "name": current_character,
                    "dialogue_lines": 0,
                    "scenes": [],
                }
            characters[current_character]["scenes"].append(len(scenes) + 1)
            current_characters.add(current_character)
        elif dialogue_pattern.match(line) and current_character:
            characters[current_character]["dialogue_lines"] += 1
            for other_character in current_characters:
                if other_character != current_character:
                    if current_character not in dialogue_interactions:
                        dialogue_interactions[current_character] = {}
                    if other_character not in dialogue_interactions[current_character]:
                        dialogue_interactions[current_character][other_character] = 0
                    dialogue_interactions[current_character][other_character] += 1
    # Append the last scene
    if current_scene:
        current_scene["characters"] = list(current_characters)
        scenes.append(current_scene)
    # Convert characters dict to list
    characters_list = [v for v in characters.values()]
    return {
        "screenplay": {
            "title": title,  # Now uses the passed-in title parameter
            "characters": characters_list,
            "scenes": scenes,
            "dialogue_interactions": dialogue_interactions,
        }
    }

# Use the extracted text with the screenplay parser
pdf_path = 'your_screenplay.pdf'
script_content = extract_text_from_pdf(pdf_path)
screenplay_data = parse_screenplay(script_content)