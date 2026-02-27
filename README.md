# Resume Parser API

A simple, production-ready API to extract structured data from resumes using OpenAI GPT models.

## Features

- **Single Endpoint**: One simple `/parse` endpoint
- **Multiple File Types**: PDF, DOCX, images, and text files
- **OCR Support**: Handles scanned PDFs and images
- **Clean JSON Output**: Structured data extraction

## Quick Start

### 1. Setup

```bash
# Activate virtual environment
venv\Scripts\activate

# Install dependencies (already done)
pip install -r requirements.txt
```

### 2. Configure API Key

Edit `.env` file:
```
OPENAI_API_KEY=your_actual_api_key_here
OPENAI_MODEL=gpt-4o
```

### 3. Run Server

```bash
python main.py
```

Server runs at: http://localhost:8000

## API Usage

### Parse Resumes

**POST** `/parse`

#### Using curl:
```bash
# Single file
curl -X POST "http://localhost:8000/parse" -F "files=@resume.pdf"

# Multiple files
curl -X POST "http://localhost:8000/parse" \
  -F "files=@resume1.pdf" \
  -F "files=@resume2.docx"
```

#### Using Postman (IMPORTANT - Follow Exactly):

1. **Set HTTP Method**: `POST`
2. **Set URL**: `http://localhost:8000/parse`
3. **Go to Body Tab**: Click on "Body"
4. **Select form-data**: Choose `form-data` option (NOT raw, NOT binary, NOT x-www-form-urlencoded)
5. **Add File Key**:
   - Key: Type `files`
   - **CRITICAL**: Click the dropdown arrow on the RIGHT side of the key field and select **File** (not Text)
   - Value: Click "Select Files" and choose your resume file
6. **Click Send**

**Common Mistakes:**
-  Using `raw` or `binary` body type → This causes 422 error
-  Not changing key type to `File` → This causes 422 error
-  Using wrong key name (must be `files`) → This causes 422 error

#### Using Swagger UI (Easiest Way):
1. Open `http://localhost:8000/docs` in browser
2. Click on `POST /parse`
3. Click "Try it out"
4. Click "Choose File" button
5. Select your file and click "Execute"

### Response Format

```json
{
  "results": [
    {
      "filename": "resume.pdf",
      "success": true,
      "data": {
        "name": "John Doe",
        "email": ["john@email.com"],
        "phone": ["+1234567890"],
        "linkedin": ["linkedin.com/in/johndoe"],
        "github": ["github.com/johndoe"],
        "education": [
          {
            "degree": "Bachelor of Science in Computer Science",
            "institution": "MIT",
            "year": "2018-2022"
          }
        ],
        "experience": [
          {
            "job_title": "Software Engineer",
            "company": "Google",
            "duration": "2022-Present",
            "description": "Developed microservices..."
          }
        ],
        "skills": ["Python", "JavaScript", "React"]
      },
      "error": null
    }
  ]
}
```

### Other Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API info |
| `/health` | GET | Check API health |
| `/docs` | GET | Swagger UI documentation |

## Supported File Types

- `.pdf` - PDF documents (text and scanned)
- `.docx` - Microsoft Word documents
- `.txt` - Plain text files
- `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff`, `.webp` - Images (OCR)

## Project Structure

```
Resume_parsing_project/
├── main.py           # Single file with all code
├── requirements.txt  # Dependencies
├── .env              # API key configuration
├── sample_resume.txt # Test file
└── venv/             # Virtual environment
```

## Testing

```bash
# Start server
python main.py

# Test with sample resume
curl -X POST "http://localhost:8000/parse" -F "files=@sample_resume.txt"
```

## Web Interface

Open http://localhost:8000/docs in your browser for interactive API documentation (Swagger UI).

## Error Handling

The API handles errors gracefully and returns them in the response:

```json
{
  "results": [
    {
      "filename": "resume.pdf",
      "success": false,
      "data": null,
      "error": "Error message here"
    }
  ]
}