# Script Parser API

A Flask API that parses movie/TV scripts (PDF) and extracts information about scenes, characters, and more.

## Features
- Extract scenes and their locations
- Identify characters in each scene
- Count lines per scene
- Generate overall script statistics

## API Endpoints

### POST /parse-script/
Upload a script file (PDF) to parse it.

Example:
```bash
curl -X POST -F "file=@your_script.pdf" https://your-api-url/parse-script/
```

## Quick Deploy
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)
