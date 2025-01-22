from flask import Flask, request, jsonify
import tempfile
import os
from parser import parse_screenplay, extract_text_from_pdf

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "message": "Welcome to the Script Parser API. Use POST /parse-script/ to upload and parse a script."
    })

@app.route('/parse-script/', methods=['POST'])
def parse_script():
    """
    Upload a script file (PDF) and get parsed information including:
    - Scenes
    - Characters
    - Scene locations
    - Line counts
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
        
    if not file.filename.endswith('.pdf'):
        return jsonify({"error": "Only PDF files are supported"}), 400

    # Create a temporary file to store the uploaded PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
        file.save(tmp_file.name)
        
        try:
            # Extract text from PDF
            script_content = extract_text_from_pdf(tmp_file.name)
            
            # Parse the screenplay
            screenplay_data = parse_screenplay(
                script_content, 
                title=os.path.splitext(file.filename)[0]
            )
            
            # Add some additional statistics
            stats = {
                "total_scenes": len(screenplay_data["screenplay"]["scenes"]),
                "total_characters": len(screenplay_data["screenplay"]["all_characters"]),
                "character_scene_count": {}
            }
            
            # Count scenes per character
            for character in screenplay_data["screenplay"]["all_characters"]:
                scene_count = sum(
                    1 for scene in screenplay_data["screenplay"]["scenes"] 
                    if character in scene["characters"]
                )
                stats["character_scene_count"][character] = scene_count
            
            screenplay_data["statistics"] = stats
            
            return jsonify(screenplay_data)
            
        finally:
            # Clean up the temporary file
            os.unlink(tmp_file.name)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000) 