import json
import pdfplumber
from format_parsers import parse_screenplay

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file."""
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def test_parser(pdf_path, output_json_path=None):
    """Test the screenplay parser on a PDF file."""
    print(f"Extracting text from: {pdf_path}")
    
    # Extract text from PDF
    script_content = extract_text_from_pdf(pdf_path)
    
    print(f"Extracted {len(script_content)} characters of text.")
    
    # Parse the screenplay
    print("Parsing screenplay...")
    title = pdf_path.split("/")[-1].split(".")[0]  # Extract filename without extension
    screenplay_data = parse_screenplay(script_content, title)
    
    # Print some basic stats
    scenes = screenplay_data["screenplay"]["scenes"]
    characters = screenplay_data["screenplay"]["characters"]
    
    print(f"\nParsing results:")
    print(f"Title: {screenplay_data['screenplay']['title']}")
    print(f"Total pages: {screenplay_data['screenplay']['total_pages']}")
    print(f"Total scenes: {len(scenes)}")
    print(f"Total characters: {len(characters)}")
    
    # Print first few scenes
    print("\nFirst 3 scenes:")
    for scene in scenes[:3]:
        print(f"Scene {scene['scene_number']}: {scene['type']} - {scene['location']} - {scene['time_of_day']}")
        print(f"  Characters: {', '.join(scene['characters'])}")
        print(f"  Page: {scene['start_page']} - {scene['end_page']}")
    
    # Print top characters by line count
    print("\nTop 5 characters by line count:")
    sorted_chars = sorted(characters, key=lambda x: x['total_lines'], reverse=True)
    for char in sorted_chars[:5]:
        print(f"{char['name']}: {char['total_lines']} lines, appears in {len(char['scene_appearances'])} scenes")
    
    # Save to JSON if requested
    if output_json_path:
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(screenplay_data, f, indent=2)
        print(f"\nFull results saved to: {output_json_path}")

if __name__ == "__main__":
    # Replace with the path to your script PDF
    # pdf_path = "/Users/nikhildevisetty/Documents/SLATE/slate-script-parser/John-Wick-Chapter-4-Read-The-Screenplay.pdf"
    pdf_path = "/Users/nikhildevisetty/Documents/SLATE/slate-script-parser/Naatyam.pdf"
    # pdf_path = "/Users/nikhildevisetty/Documents/SLATE/slate-script-parser/The Big Lebowski.pdf"
    
    # Optional: save the results to a JSON file
    output_json = "johnwick-4.json"
    
    test_parser(pdf_path, output_json)