"""
Simple Resume Parser API
========================
1. Extract raw text from PDF, DOCX, and scanned image PDFs
2. Extract hyperlinks from PDFs using PyMuPDF
3. Send extracted text to an LLM
4. Ask the LLM to return structured JSON
5. Merge extracted links with LLM data
6. Return clean JSON response via FastAPI
"""

import os
import json
import tempfile
import logging
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse 
from pydantic import BaseModel
from dotenv import load_dotenv

# Import link extraction module
from link_extractor import (
    extract_links_with_metadata,
    extract_links_from_text,
    merge_links_with_resume_data
)

# Import validation module
from validator import (
    validate_llm_output,
    sanitize_llm_output,
    generate_retry_prompt,
    ValidationResult
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============== PYDANTIC MODELS ==============

class Education(BaseModel):
    level: str = ""
    qualification: str = ""
    institution: str = ""
    location: Optional[str] = None
    percentage: str = ""
    year: str = ""


class Experience(BaseModel):
    job_title: str = ""
    company: str = ""
    duration: str = ""
    description: str = ""


class Project(BaseModel):
    """Model for project details."""
    title: str = ""
    description: str = ""
    technologies: List[str] = []
    link: str = ""


class Hobby(BaseModel):
    """Model for hobbies."""
    name: str = ""
    description: str = ""


class Certification(BaseModel):
    """Model for certifications."""
    name: str = ""
    issuer: str = ""
    date: str = ""
    link: str = ""


class CodingProfile(BaseModel):
    """Model for coding platform profiles."""
    platform: str = ""
    username: str = ""
    link: str = ""
    rating: str = ""


class Miscellaneous(BaseModel):
    """Model for miscellaneous information."""
    coding_profiles: List[CodingProfile] = []
    certifications: List[Certification] = []
    expertise: List[str] = []
    other_links: List[str] = []


class ResumeData(BaseModel):
    """Main resume data model with all fields."""
    name: str = ""
    email: List[str] = []
    phone: List[str] = []
    linkedin: List[str] = []
    github: List[str] = []
    education: List[Education] = []
    experience: List[Experience] = []
    skills: List[str] = []
    # New fields
    projects: List[Project] = []
    hobbies: List[Hobby] = []
    miscellaneous: Optional[Miscellaneous] = None
    
    @classmethod
    def from_dict(cls, data: dict):
        """Create ResumeData from dict with proper handling of empty values."""
        # Handle name field
        name = data.get('name', '') or ''
        if isinstance(name, list):
            name = name[0] if name else ''
        
        # Handle list fields
        def ensure_list(val):
            if val is None:
                return []
            if isinstance(val, str):
                return [val] if val else []
            if isinstance(val, list):
                return val
            return []
        
        email = ensure_list(data.get('email'))
        phone = ensure_list(data.get('phone'))
        linkedin = ensure_list(data.get('linkedin'))
        github = ensure_list(data.get('github'))
        skills = ensure_list(data.get('skills'))
        
        # Handle education
        education = []
        edu_data = data.get("education", [])

        if edu_data and isinstance(edu_data, list):
            for item in edu_data:
                if isinstance(item, dict):

                    # Get institution line and clean it
                    institution_line = str(item.get("institution", "")).replace("•", "").strip()

                    institution = institution_line
                    location = None

                    # Case 1: If comma present (most common format)
                    if "," in institution_line:
                        parts = [p.strip() for p in institution_line.split(",")]

                        if len(parts) >= 2:
                            institution = parts[0]
                            location = parts[-1]

                    # Case 2: If location already provided
                    if item.get("location"):
                        location = item.get("location")

                    education.append({
                        "level": str(item.get("level", "")),
                        "qualification": str(item.get("qualification", "")),
                        "institution": institution,
                        "location": location,
                        "percentage": str(item.get("percentage", "")),
                        "year": str(item.get("year", ""))
                    })
        
        # Handle experience
        experience = []
        exp_data = data.get('experience', [])
        if exp_data and isinstance(exp_data, list):
            for item in exp_data:
                if isinstance(item, dict):
                    experience.append({
                        'job_title': str(item.get('job_title', '')),
                        'company': str(item.get('company', '')),
                        'duration': str(item.get('duration', '')),
                        'description': str(item.get('description', ''))
                    })
        
        # Handle projects
        projects = []
        proj_data = data.get('projects', [])
        if proj_data and isinstance(proj_data, list):
            for item in proj_data:
                if isinstance(item, dict):
                    projects.append({
                        'title': str(item.get('title', '')),
                        'description': str(item.get('description', '')),
                        'technologies': ensure_list(item.get('technologies')),
                        'link': str(item.get('link', ''))
                    })
        
        # Handle hobbies
        hobbies = []
        hobby_data = data.get('hobbies', [])
        if hobby_data and isinstance(hobby_data, list):
            for item in hobby_data:
                if isinstance(item, dict):
                    hobbies.append({
                        'name': str(item.get('name', '')),
                        'description': str(item.get('description', ''))
                    })
        
        # Handle miscellaneous
        miscellaneous = None
        misc_data = data.get('miscellaneous')
        if misc_data and isinstance(misc_data, dict):
            # Coding profiles
            coding_profiles = []
            cp_data = misc_data.get('coding_profiles', [])
            if cp_data and isinstance(cp_data, list):
                for item in cp_data:
                    if isinstance(item, dict):
                        coding_profiles.append({
                            'platform': str(item.get('platform', '')),
                            'username': str(item.get('username', '')),
                            'link': str(item.get('link', '')),
                            'rating': str(item.get('rating', ''))
                        })
            
            # Certifications
            certifications = []
            cert_data = misc_data.get('certifications', [])
            if cert_data and isinstance(cert_data, list):
                for item in cert_data:
                    if isinstance(item, dict):
                        certifications.append({
                            'name': str(item.get('name', '')),
                            'issuer': str(item.get('issuer', '')),
                            'date': str(item.get('date', '')),
                            'link': str(item.get('link', ''))
                        })
            
            # Expertise
            expertise = ensure_list(misc_data.get('expertise'))
            
            # Other links
            other_links = ensure_list(misc_data.get('other_links'))
            
            miscellaneous = {
                'coding_profiles': coding_profiles,
                'certifications': certifications,
                'expertise': expertise,
                'other_links': other_links
            }
        
        return cls(
            name=str(name),
            email=email,
            phone=phone,
            linkedin=linkedin,
            github=github,
            education=education,
            experience=experience,
            skills=skills,
            projects=projects,
            hobbies=hobbies,
            miscellaneous=miscellaneous
        )


class ParseResult(BaseModel):
    filename: str
    success: bool
    data: Optional[ResumeData] = None
    error: Optional[str] = None


class ParseResponse(BaseModel):
    results: List[ParseResult]


# ============== TEXT EXTRACTION ==============

def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF using pdfplumber or OCR for scanned PDFs."""
    text = ""
    
    # Try pdfplumber first
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        logger.info(f"pdfplumber extracted {len(text.strip())} characters")
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}")
    
    # If no text found, try OCR (for scanned PDFs)
    if len(text.strip()) < 50:
        logger.info(f"Text length {len(text.strip())} < 50, triggering OCR fallback...")
        try:
            from pdf2image import convert_from_path
            import pytesseract
            from PIL import Image
            
            # Set tesseract path if configured
            tesseract_path = os.getenv("TESSERACT_PATH")
            if tesseract_path:
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
            
            logger.info("Converting PDF to images...")
            images = convert_from_path(file_path, dpi=300)
            logger.info(f"Converted to {len(images)} image(s)")
            
            text = ""
            for i, image in enumerate(images):
                ocr_text = pytesseract.image_to_string(image)
                text += ocr_text + "\n"
                logger.info(f"OCR on image {i+1}: extracted {len(ocr_text)} characters")
            
            logger.info(f"Total OCR extracted: {len(text.strip())} characters")
            logger.info("Used OCR for scanned PDF")
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
    else:
        logger.info(f"OCR NOT triggered (text length {len(text.strip())} >= 50)")
    
    return text.strip()


def extract_text_from_docx(file_path: str) -> str:
    """Extract text from DOCX file."""
    try:
        from docx import Document
        doc = Document(file_path)
        text = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text.append(paragraph.text)
        return "\n".join(text)
    except Exception as e:
        logger.error(f"DOCX extraction failed: {e}")
        return ""


def extract_text_from_image(file_path: str) -> str:
    """Extract text from image using OCR."""
    try:
        import pytesseract
        from PIL import Image
        
        # Set tesseract path if configured
        tesseract_path = os.getenv("TESSERACT_PATH")
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        
        image = Image.open(file_path)
        text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception as e:
        logger.error(f"Image OCR failed: {e}")
        return ""


def extract_text_from_txt(file_path: str) -> str:
    """Extract text from plain text file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Text file read failed: {e}")
        return ""


def extract_text(file_path: str) -> str:
    """Extract text from any supported file type."""
    ext = Path(file_path).suffix.lower()
    
    if ext == '.pdf':
        return extract_text_from_pdf(file_path)
    elif ext in ['.docx', '.doc']:
        return extract_text_from_docx(file_path)
    elif ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp']:
        return extract_text_from_image(file_path)
    elif ext == '.txt':
        return extract_text_from_txt(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


# ============== LLM INTEGRATION ==============

RESUME_PROMPT = """You are a resume parsing AI. Extract structured information from the resume text below.

Return ONLY valid JSON with this exact structure (no markdown, no explanations):

{{
  "name": "",
  "email": [],
  "phone": [],
  "linkedin": [],
  "github": [],
  "education": [{{"level": "", "qualification": "", "institution": "", "location": null, "percentage": "", "year": ""}}],
  "experience": [{{"job_title": "", "company": "", "duration": "", "description": ""}}],
  "skills": [],
  "projects": [{{"title": "", "description": "", "technologies": [], "link": ""}}],
  "hobbies": [{{"name": "", "description": ""}}],
  "miscellaneous": {{
    "coding_profiles": [{{"platform": "", "username": "", "link": "", "rating": ""}}],
    "certifications": [{{"name": "", "issuer": "", "date": "", "link": ""}}],
    "expertise": [],
    "other_links": []
  }}
}}

Rules:
- If a field is not found, return empty string, empty list, or null
- Extract text exactly as written in the resume
- Do not invent or summarize data
- Return multiple entries if available

Field-specific rules:
- For education, extract ALL education entries with:
  - level: Education level (e.g., "Undergraduate", "Postgraduate", "Diploma", "Senior Secondary", "Secondary", "High School", "PhD")
  - qualification: Full qualification name (e.g., "Bachelor of Technology in Computer Science")
  - institution: School/College/University name
  - location: City/State of institution, null if not mentioned
  - percentage: Percentage/CGPA if mentioned
  - year: Year of passing or duration

- For projects, extract ALL projects mentioned with:
  - title: Project name
  - description: Brief description of the project
  - technologies: List of technologies/tools used
  - link: Project demo or repository URL if mentioned

- For hobbies, extract hobbies/interests mentioned with:
  - name: Hobby name
  - description: Brief description if available

- For miscellaneous:
  - coding_profiles: Extract coding platform profiles (LeetCode, HackerRank, Codeforces, CodeChef, etc.) with platform name, username, link, and rating/rank if mentioned
  - certifications: Extract professional certifications with name, issuer (organization), date, and link if available
  - expertise: Extract areas of expertise or specializations mentioned
  - other_links: Any other relevant links not captured elsewhere

Resume Text:
----------------
{text}
----------------
"""


# ============== VALIDATION RETRY CONSTANTS ==============

MAX_VALIDATION_RETRIES = 3
VALIDATION_FAILURE_MESSAGE = "Resume has formatting/structure issue"


def _call_llm(client, model: str, prompt: str) -> dict:
    """
    Internal function to call OpenAI LLM with a prompt.
    
    Args:
        client: OpenAI client instance
        model: Model name to use
        prompt: The prompt to send
    
    Returns:
        Parsed JSON dictionary from LLM response
    
    Raises:
        Exception: If LLM call or JSON parsing fails
    """
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a precise resume parser. Return only valid JSON, no markdown formatting."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        response_format={"type": "json_object"}
    )
    
    result_text = response.choices[0].message.content
    logger.info(f"LLM Response length: {len(result_text)}")
    logger.debug(f"LLM Response: {result_text}")
    
    # Parse JSON response
    data = json.loads(result_text)
    logger.info(f"Parsed data keys: {list(data.keys())}")
    
    return data


def parse_with_llm(text: str) -> dict:
    """
    Send text to OpenAI LLM and get structured JSON response with validation retry.
    
    This function implements enterprise-level validation with retry mechanism:
    - Validates LLM output against expected Pydantic schema
    - Retries up to MAX_VALIDATION_RETRIES times if validation fails
    - Enhances retry prompts with validation error feedback
    - Returns None if all retries are exhausted
    
    Args:
        text: Resume text to parse
    
    Returns:
        dict: Parsed and validated resume data, or None if validation fails after all retries
    """
    from openai import OpenAI
    import traceback
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set in environment")
    
    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    
    # Store original text for retry prompt generation
    original_text = text
    current_prompt = RESUME_PROMPT.format(text=text)
    
    last_validation_result = None
    
    for attempt in range(1, MAX_VALIDATION_RETRIES + 1):
        try:
            logger.info(f"LLM attempt {attempt}/{MAX_VALIDATION_RETRIES}")
            
            # Call LLM
            data = _call_llm(client, model, current_prompt)
            
            # Sanitize the output (fix common issues like string instead of list)
            sanitized_data = sanitize_llm_output(data)
            
            # Validate the output against schema
            validation_result = validate_llm_output(sanitized_data, strict=True)
            last_validation_result = validation_result
            
            if validation_result.is_valid:
                logger.info(f"✓ Validation PASSED on attempt {attempt}/{MAX_VALIDATION_RETRIES}")
                return sanitized_data
            
            # Validation failed
            logger.warning(f"✗ Validation FAILED on attempt {attempt}/{MAX_VALIDATION_RETRIES}")
            logger.warning(f"Validation errors: {validation_result.get_error_summary()}")
            
            # If not the last attempt, prepare enhanced prompt with error feedback
            if attempt < MAX_VALIDATION_RETRIES:
                logger.info(f"Preparing retry prompt with validation error feedback...")
                current_prompt = RESUME_PROMPT.format(text=original_text)
                current_prompt = generate_retry_prompt(
                    original_prompt=current_prompt,
                    validation_result=validation_result,
                    attempt=attempt
                )
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error on attempt {attempt}: {e}")
            if attempt < MAX_VALIDATION_RETRIES:
                # Enhance prompt for JSON parsing error
                current_prompt = RESUME_PROMPT.format(text=original_text)
                current_prompt += f"""

═══════════════════════════════════════════════════════════════
⚠️ JSON PARSING ERROR - RETRY ATTEMPT {attempt}
═══════════════════════════════════════════════════════════════

Your previous response was not valid JSON. Error: {str(e)}

CRITICAL: Return ONLY valid JSON. No markdown, no code blocks, no explanations.
Start your response with {{ and end with }}
═══════════════════════════════════════════════════════════════
"""
            continue
            
        except Exception as e:
            logger.error(f"LLM call error on attempt {attempt}: {e}")
            logger.error(f"Full error traceback: {traceback.format_exc()}")
            if attempt == MAX_VALIDATION_RETRIES:
                raise
    
    # All retries exhausted - validation failed
    logger.error(f"All {MAX_VALIDATION_RETRIES} validation attempts exhausted")
    if last_validation_result:
        logger.error(f"Final validation errors:\n{last_validation_result.get_detailed_report()}")
    
    return None  # Signal that validation failed


# ============== FASTAPI APP ==============

app = FastAPI(
    title="Resume Parser API",
    description="Extract structured data from resumes using AI",
    version="2.0.0"
)

# Add CORS for web access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """API info"""
    return {
        "name": "Resume Parser API",
        "version": "2.0.0",
        "endpoint": "POST /parse - Upload resumes to parse",
        "supported_formats": [".pdf", ".docx", ".doc", ".txt", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"],
        "features": [
            "Basic info extraction (name, email, phone, LinkedIn, GitHub)",
            "Education, Experience, Skills parsing",
            "Project details with links",
            "Hobbies extraction",
            "Coding profiles (LeetCode, HackerRank, Codeforces, etc.)",
            "Certifications",
            "Areas of expertise",
            "PDF hyperlink extraction"
        ]
    }


@app.post("/parse", response_model=ParseResponse)
async def parse_resumes(files: List[UploadFile] = File(...)):
    """
    Parse one or more resume files and return structured JSON data.
    
    ## How to Use in Postman:
    1. Set method to **POST**
    2. URL: `http://localhost:8000/parse`
    3. Go to **Body** tab
    4. Select **form-data** (NOT raw, NOT binary)
    5. Key: `files` → Change type to **File** (click dropdown on the right of key)
    6. Value: Click **Select Files** and choose your PDF/DOCX/image
    
    ## How to Use in curl:
    ```bash
    curl -X POST "http://localhost:8000/parse" -F "files=@resume.pdf"
    ```
    
    ## Supported File Types:
    - PDF (.pdf)
    - Word (.docx, .doc)
    - Images (.png, .jpg, .jpeg, .bmp, .tiff, .webp)
    - Text (.txt)
    
    ## Returns:
    - name, email, phone, linkedin, github
    - education, experience, skills
    - projects (with links)
    - hobbies
    - miscellaneous (coding profiles, certifications, expertise, other links)
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    
    results = []
    
    for file in files:
        try:
            # Save uploaded file temporarily
            ext = Path(file.filename).suffix.lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                content = await file.read()
                tmp.write(content)
                tmp_path = tmp.name
            
            # Step 1: Extract text
            logger.info(f"Extracting text from: {file.filename}")
            text = extract_text(tmp_path)
            
            # Step 2: Extract links from PDF (if applicable)
            extracted_links = {}
            if ext == '.pdf':
                logger.info(f"Extracting links from PDF: {file.filename}")
                extracted_links = extract_links_with_metadata(tmp_path)
                logger.info(f"Extracted links: {extracted_links}")
            elif ext in ['.docx', '.doc', '.txt']:
                logger.info(f"Extracting links from text: {file.filename}")
                extracted_links = extract_links_from_text(text)
                logger.info(f"Extracted links: {extracted_links}")
            
            # Clean up temp file
            os.unlink(tmp_path)
            
            if not text.strip():
                results.append(ParseResult(
                    filename=file.filename,
                    success=False,
                    error="No text could be extracted"
                ))
                continue
            
            # Step 3: Send to LLM and get JSON with validation retry
            logger.info(f"Parsing with LLM: {file.filename}")
            data = parse_with_llm(text)
            
            # Step 4: Check if validation failed after all retries
            if data is None:
                logger.error(f"Validation failed for {file.filename} after {MAX_VALIDATION_RETRIES} retries")
                results.append(ParseResult(
                    filename=file.filename,
                    success=False,
                    error=VALIDATION_FAILURE_MESSAGE
                ))
                continue
            
            # Step 5: Merge extracted links with LLM data
            logger.info(f"Merging extracted links with LLM data")
            merged_data = merge_links_with_resume_data(data, extracted_links)
            
            # Step 6: Validate and create ResumeData
            resume_data = ResumeData.from_dict(merged_data)
            
            # Step 7: Return clean JSON
            results.append(ParseResult(
                filename=file.filename,
                success=True,
                data=resume_data
            ))
            
        except Exception as e:
            import traceback
            logger.error(f"Error processing {file.filename}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            results.append(ParseResult(
                filename=file.filename,
                success=False,
                error=str(e)
            ))
    
    return ParseResponse(results=results)


@app.get("/health")
async def health():
    """Check API health and OpenAI connection"""
    try:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return {"status": "error", "message": "OPENAI_API_KEY not set"}
        
        client = OpenAI(api_key=api_key)
        client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=1
        )
        return {"status": "healthy", "openai": "connected"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============== RUN SERVER ==============

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*50)
    print("Resume Parser API v2.0.0")
    print("="*50)
    print("\nAPI Documentation: http://localhost:8000/docs")
    print("Endpoint: POST http://localhost:8000/parse")
    print("\nFeatures:")
    print("  - Basic info (name, email, phone, LinkedIn, GitHub)")
    print("  - Education, Experience, Skills")
    print("  - Projects with links")
    print("  - Hobbies")
    print("  - Coding profiles (LeetCode, HackerRank, etc.)")
    print("  - Certifications")
    print("  - PDF hyperlink extraction")
    print("\nMake sure to set OPENAI_API_KEY in .env file")
    print("="*50 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)