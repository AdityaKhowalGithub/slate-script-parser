import PyPDF2
import re
import pdfplumber

def extract_text_from_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

#parser
def parse_screenplay(script, title):
    scenes = []
    all_characters = set()
    current_scene = None
    current_characters = set()
    lines = script.split("\n")
    scene_pattern = re.compile(r'^\s*(\d+\.\s*)?(INT\.|EXT\.)')
    character_pattern = re.compile(r"^[A-Z][A-Z\s]+$")
    current_character = None
    line_count = 0

    for line in lines:
        # Identify new scenes
        if scene_pattern.match(line):
            if current_scene:
                current_scene["characters"] = list(current_characters)
                current_scene["line_count"] = line_count
                scenes.append(current_scene)

            current_scene = {
                "scene_number": len(scenes) + 1,
                "location": line.strip(),
                "characters": [],
                "line_count": 0,
            }
            current_characters = set()
            line_count = 0  # Reset line counter for the new scene
        
        # Increment line count if within a scene
        if current_scene:
            line_count += 1

        # Identify characters
        if character_pattern.match(line.strip()) and not line.strip().endswith(":"):
            current_character = line.strip()
            current_characters.add(current_character)
            all_characters.add(current_character)

    # Append the last scene
    if current_scene:
        current_scene["characters"] = list(current_characters)
        current_scene["line_count"] = line_count
        scenes.append(current_scene)

    return {
        "screenplay": {
            "title": title,
            "scenes": scenes,
            "all_characters": sorted(list(all_characters))
        }
    }

# Use the extracted text with the screenplay parser
pdf_path = './Naatyam.pdf'
script_content = extract_text_from_pdf(pdf_path)
screenplay_data = parse_screenplay(script_content, "naatyam")
print("Scenes:")
for scene in screenplay_data["screenplay"]["scenes"]:
    print(f"Scene {scene['scene_number']}: {scene['location']}")
    print("Characters:", scene['characters'])
    print("Line Count:", scene['line_count'])
    print()

print("\nAll Characters:")
print(screenplay_data["screenplay"]["all_characters"])
