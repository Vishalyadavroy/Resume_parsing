"""
Link Extraction Module for Resume Parser
=========================================
Extracts and classifies hyperlinks from PDF files using PyMuPDF (fitz).
Categories: LinkedIn, GitHub, Project Links, Coding Profiles, Certifications, Others
"""

import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Try to import PyMuPDF
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF not available. PDF link extraction will be disabled.")


class LinkCategory(Enum):
    """Categories for classifying hyperlinks."""
    LINKEDIN = "linkedin"
    GITHUB = "github"
    PROJECT = "project"
    CODING_PROFILE = "coding_profile"
    CERTIFICATION = "certification"
    PORTFOLIO = "portfolio"
    OTHER = "other"


@dataclass
class ExtractedLink:
    """Represents an extracted hyperlink with metadata."""
    url: str
    category: LinkCategory
    platform: str = ""
    text_context: str = ""
    page_number: int = 0


@dataclass
class ClassifiedLinks:
    """Container for all classified links."""
    linkedin: List[str] = field(default_factory=list)
    github: List[str] = field(default_factory=list)
    project_links: List[Dict[str, str]] = field(default_factory=list)
    coding_profiles: List[Dict[str, str]] = field(default_factory=list)
    certifications: List[Dict[str, str]] = field(default_factory=list)
    portfolio_links: List[str] = field(default_factory=list)
    other_links: List[str] = field(default_factory=list)


# Platform patterns for link classification
LINKEDIN_PATTERNS = [
    r'(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+',
    r'(?:https?://)?(?:www\.)?linkedin\.com/company/[\w-]+',
]

GITHUB_PATTERNS = [
    r'(?:https?://)?(?:www\.)?github\.com/[\w-]+',
    r'(?:https?://)?(?:www\.)?github\.com/[\w-]+/[\w-]+',  # Repos
]

CODING_PLATFORMS = {
    'leetcode': r'(?:https?://)?(?:www\.)?leetcode\.com/([\w-]+)',
    'hackerrank': r'(?:https?://)?(?:www\.)?hackerrank\.com/([\w-]+)',
    'codeforces': r'(?:https?://)?(?:www\.)?codeforces\.com/profile/([\w-]+)',
    'codechef': r'(?:https?://)?(?:www\.)?codechef\.com/users/([\w-]+)',
    'hackerearth': r'(?:https?://)?(?:www\.)?hackerearth\.com/[@\w-]+',
    'spoj': r'(?:https?://)?(?:www\.)?spoj\.com/users/([\w-]+)',
    'topcoder': r'(?:https?://)?(?:www\.)?topcoder\.com/members/([\w-]+)',
    'geeksforgeeks': r'(?:https?://)?(?:www\.)?geeksforgeeks\.org/user/([\w-]+)',
    'kaggle': r'(?:https?://)?(?:www\.)?kaggle\.com/([\w-]+)',
    'dev.to': r'(?:https?://)?(?:www\.)?dev\.to/([\w-]+)',
    'medium': r'(?:https?://)?(?:www\.)?medium\.com/@([\w-]+)',
}

CERTIFICATION_PLATFORMS = {
    'coursera': r'(?:https?://)?(?:www\.)?coursera\.org',
    'udemy': r'(?:https?://)?(?:www\.)?udemy\.com',
    'edx': r'(?:https?://)?(?:www\.)?edx\.org',
    'skillshare': r'(?:https?://)?(?:www\.)?skillshare\.com',
    'linkedin_learning': r'(?:https?://)?(?:www\.)?linkedin\.com/learning',
    'google_skillshop': r'(?:https?://)?skillshop\.withgoogle\.com',
    'aws_training': r'(?:https?://)?(?:www\.)?aws\.amazon\.com/training',
    'microsoft_learn': r'(?:https?://)?(?:www\.)?learn\.microsoft\.com',
    'pluralsight': r'(?:https?://)?(?:www\.)?pluralsight\.com',
    'datacamp': r'(?:https?://)?(?:www\.)?datacamp\.com',
    'codecademy': r'(?:https?://)?(?:www\.)?codecademy\.com',
}

PROJECT_HOSTING_PATTERNS = [
    r'(?:https?://)?(?:www\.)?vercel\.app',
    r'(?:https?://)?(?:www\.)?netlify\.app',
    r'(?:https?://)?(?:www\.)?herokuapp\.com',
    r'(?:https?://)?(?:www\.)?firebaseapp\.com',
    r'(?:https?://)?(?:www\.)?pages\.dev',
    r'(?:https?://)?(?:www\.)?github\.io',
    r'(?:https?://)?(?:www\.)?gitlab\.io',
]

PORTFOLIO_PATTERNS = [
    r'(?:https?://)?(?:www\.)?[\w-]+\.(dev|me|io|portfolio|tech)',
]


def extract_links_from_pdf(file_path: str) -> List[ExtractedLink]:
    """
    Extract all hyperlinks from a PDF file using PyMuPDF.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        List of ExtractedLink objects with URL and metadata
    """
    if not PYMUPDF_AVAILABLE:
        logger.warning("PyMuPDF not available, skipping PDF link extraction")
        return []
    
    extracted_links = []
    seen_urls = set()  # Track URLs to avoid duplicates
    
    try:
        doc = fitz.open(file_path)
        
        for page_num, page in enumerate(doc):
            # Method 1: Extract from PDF link annotations
            links = page.get_links()
            
            for link in links:
                url = link.get('uri', '')
                if not url:
                    continue
                
                # Normalize URL
                url = url.strip()
                if url.lower().startswith('mailto:'):
                    continue  # Skip email links
                
                # Get surrounding text context
                text_context = ""
                if 'rect' in link:
                    rect = link['rect']
                    # Expand rect slightly to get context
                    expanded_rect = fitz.Rect(
                        rect.x0 - 50,
                        rect.y0 - 20,
                        rect.x1 + 50,
                        rect.y1 + 20
                    )
                    text_context = page.get_text("text", clip=expanded_rect)
                
                # Classify the link
                category, platform = classify_link(url)
                
                if url not in seen_urls:
                    seen_urls.add(url)
                    extracted_link = ExtractedLink(
                        url=url,
                        category=category,
                        platform=platform,
                        text_context=text_context.strip(),
                        page_number=page_num + 1
                    )
                    extracted_links.append(extracted_link)
            
            # Method 2: Extract URLs from page text (fallback for text-based links)
            page_text = page.get_text("text")
            text_based_links = extract_urls_from_text(page_text)
            
            for url in text_based_links:
                if url not in seen_urls:
                    seen_urls.add(url)
                    category, platform = classify_link(url)
                    extracted_link = ExtractedLink(
                        url=url,
                        category=category,
                        platform=platform,
                        text_context="",
                        page_number=page_num + 1
                    )
                    extracted_links.append(extracted_link)
        
        doc.close()
        logger.info(f"Extracted {len(extracted_links)} links from PDF (annotations + text fallback)")
        
    except Exception as e:
        logger.error(f"Error extracting links from PDF: {e}")
    
    return extracted_links


def extract_urls_from_text(text: str) -> List[str]:
    """
    Extract all URLs from plain text using regex.
    
    Args:
        text: Plain text content
        
    Returns:
        List of URLs found in the text
    """
    # Comprehensive URL pattern
    url_patterns = [
        # Standard URLs with http/https
        r'https?://[^\s<>"{}|\\^`\[\]]+',
        # URLs without protocol (www.domain.com)
        r'(?:^|\s)www\.[a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z0-9][-a-zA-Z0-9]*)+[^\s<>"{}|\\^`\[\]]*',
    ]
    
    urls = []
    seen = set()
    
    for pattern in url_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Clean up the URL
            url = match.strip()
            if url.startswith('www.'):
                url = 'https://' + url
            
            # Remove trailing punctuation
            url = url.rstrip('.,;:!?)')
            
            # Skip invalid URLs
            if len(url) < 10:  # Minimum URL length
                continue
            
            # Skip mailto links
            if url.lower().startswith('mailto:'):
                continue
            
            # Skip image/file extensions
            skip_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.pdf', '.doc', '.docx']
            if any(url.lower().endswith(ext) for ext in skip_extensions):
                continue
            
            if url not in seen:
                seen.add(url)
                urls.append(url)
    
    return urls


def classify_link(url: str) -> tuple[LinkCategory, str]:
    """
    Classify a URL into a category.
    
    Args:
        url: The URL to classify
        
    Returns:
        Tuple of (LinkCategory, platform_name)
    """
    url_lower = url.lower()
    
    # Check LinkedIn
    for pattern in LINKEDIN_PATTERNS:
        if re.search(pattern, url_lower):
            return LinkCategory.LINKEDIN, "LinkedIn"
    
    # Check GitHub
    for pattern in GITHUB_PATTERNS:
        if re.search(pattern, url_lower):
            return LinkCategory.GITHUB, "GitHub"
    
    # Check coding platforms
    for platform, pattern in CODING_PLATFORMS.items():
        if re.search(pattern, url_lower):
            return LinkCategory.CODING_PROFILE, platform.replace('_', ' ').title()
    
    # Check certification platforms
    for platform, pattern in CERTIFICATION_PLATFORMS.items():
        if re.search(pattern, url_lower):
            return LinkCategory.CERTIFICATION, platform.replace('_', ' ').title()
    
    # Check project hosting
    for pattern in PROJECT_HOSTING_PATTERNS:
        if re.search(pattern, url_lower):
            return LinkCategory.PROJECT, "Project Demo"
    
    # Check portfolio
    for pattern in PORTFOLIO_PATTERNS:
        if re.search(pattern, url_lower):
            return LinkCategory.PORTFOLIO, "Portfolio"
    
    return LinkCategory.OTHER, "Other"


def extract_username_from_url(url: str, platform: str) -> str:
    """
    Extract username from a profile URL.
    
    Args:
        url: The profile URL
        platform: The platform name
        
    Returns:
        Extracted username or empty string
    """
    url_lower = url.lower()
    
    # Platform-specific extraction
    for platform_key, pattern in CODING_PLATFORMS.items():
        if platform_key in platform.lower().replace(' ', '_'):
            match = re.search(pattern, url_lower)
            if match:
                return match.group(1)
    
    # GitHub username extraction
    if 'github' in url_lower:
        match = re.search(r'github\.com/([\w-]+)', url_lower)
        if match:
            return match.group(1)
    
    return ""


def classify_all_links(links: List[ExtractedLink]) -> ClassifiedLinks:
    """
    Classify all extracted links into categories.
    
    Args:
        links: List of ExtractedLink objects
        
    Returns:
        ClassifiedLinks object with categorized links
    """
    classified = ClassifiedLinks()
    
    for link in links:
        url = link.url
        
        # Skip invalid URLs
        if not url or not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        if link.category == LinkCategory.LINKEDIN:
            if url not in classified.linkedin:
                classified.linkedin.append(url)
                
        elif link.category == LinkCategory.GITHUB:
            if url not in classified.github:
                # Check if it's a repo (project) vs profile
                parts = url.rstrip('/').split('/')
                if len(parts) > 4:  # github.com/username/repo
                    classified.project_links.append({
                        'url': url,
                        'platform': 'GitHub',
                        'context': link.text_context
                    })
                else:  # github.com/username
                    if url not in classified.github:
                        classified.github.append(url)
                        
        elif link.category == LinkCategory.CODING_PROFILE:
            username = extract_username_from_url(url, link.platform)
            classified.coding_profiles.append({
                'platform': link.platform,
                'username': username,
                'url': url
            })
            
        elif link.category == LinkCategory.CERTIFICATION:
            classified.certifications.append({
                'platform': link.platform,
                'url': url,
                'context': link.text_context
            })
            
        elif link.category == LinkCategory.PROJECT:
            classified.project_links.append({
                'url': url,
                'platform': link.platform,
                'context': link.text_context
            })
            
        elif link.category == LinkCategory.PORTFOLIO:
            if url not in classified.portfolio_links:
                classified.portfolio_links.append(url)
                
        else:
            if url not in classified.other_links:
                classified.other_links.append(url)
    
    return classified


def extract_links_with_metadata(file_path: str) -> Dict[str, Any]:
    """
    Extract and classify all links from a PDF file.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Dictionary with classified links ready for merging with resume data
    """
    # Extract raw links
    raw_links = extract_links_from_pdf(file_path)
    
    # Classify links
    classified = classify_all_links(raw_links)
    
    # Convert to dictionary
    result = {
        'linkedin': classified.linkedin,
        'github': classified.github,
        'project_links': classified.project_links,
        'coding_profiles': [
            {
                'platform': cp['platform'],
                'username': cp['username'],
                'link': cp['url']
            } for cp in classified.coding_profiles
        ],
        'certifications_from_links': classified.certifications,
        'portfolio_links': classified.portfolio_links,
        'other_links': classified.other_links
    }
    
    logger.info(f"Classified links: {len(classified.linkedin)} LinkedIn, "
                f"{len(classified.github)} GitHub, "
                f"{len(classified.project_links)} Projects, "
                f"{len(classified.coding_profiles)} Coding Profiles")
    
    return result


def merge_links_with_resume_data(resume_data: dict, extracted_links: dict) -> dict:
    """
    Merge extracted links with resume data from LLM.
    LLM data takes priority, extracted links fill in gaps.
    
    Args:
        resume_data: Resume data from LLM parsing
        extracted_links: Links extracted from PDF
        
    Returns:
        Merged resume data dictionary
    """
    # Helper to ensure list
    def ensure_list(val):
        if not val:
            return []
        if isinstance(val, str):
            return [val] if val else []
        return list(val)
    
    # Merge LinkedIn links
    existing_linkedin = set(ensure_list(resume_data.get('linkedin', [])))
    for link in extracted_links.get('linkedin', []):
        if link not in existing_linkedin:
            resume_data.setdefault('linkedin', []).append(link)
    
    # Merge GitHub links
    existing_github = set(ensure_list(resume_data.get('github', [])))
    for link in extracted_links.get('github', []):
        if link not in existing_github:
            resume_data.setdefault('github', []).append(link)
    
    # Merge coding profiles into miscellaneous
    misc = resume_data.setdefault('miscellaneous', {})
    existing_profiles = misc.setdefault('coding_profiles', [])
    existing_profile_urls = {p.get('link', '') for p in existing_profiles}
    
    for profile in extracted_links.get('coding_profiles', []):
        if profile.get('link') not in existing_profile_urls:
            existing_profiles.append(profile)
    
    # Merge project links with projects
    existing_projects = resume_data.setdefault('projects', [])
    existing_project_urls = {p.get('link', '') for p in existing_projects if isinstance(p, dict)}
    
    for proj_link in extracted_links.get('project_links', []):
        url = proj_link.get('url', '')
        if url and url not in existing_project_urls:
            # Try to extract project name from context or URL
            context = proj_link.get('context', '')
            name = extract_project_name_from_context(context, url)
            existing_projects.append({
                'title': name,
                'link': url,
                'description': '',
                'technologies': []
            })
    
    # Add other links to miscellaneous
    other_links = extracted_links.get('other_links', [])
    portfolio_links = extracted_links.get('portfolio_links', [])
    
    misc.setdefault('other_links', []).extend(other_links)
    misc.setdefault('other_links', []).extend(portfolio_links)
    
    # Remove duplicates from other_links
    misc['other_links'] = list(set(misc.get('other_links', [])))
    
    return resume_data


def extract_project_name_from_context(context: str, url: str) -> str:
    """
    Try to extract project name from surrounding context or URL.
    
    Args:
        context: Text surrounding the link
        url: The project URL
        
    Returns:
        Extracted project name or "Project from link"
    """
    # Try to find project name in context
    # Look for common patterns like "Project: X", "Built X", "Developed X"
    patterns = [
        r'(?:project|built|developed|created|deployed)[:\s]+([A-Za-z][\w\s-]{2,30})',
        r'([A-Za-z][\w\s-]{2,20})\s*(?:project|app|application|website|site)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, context, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    # Try to extract from URL
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        if path and '/' in path:
            # Get the repo name from github.com/user/repo
            repo_name = path.split('/')[-1]
            return repo_name.replace('-', ' ').replace('_', ' ').title()
        elif path:
            return path.replace('-', ' ').replace('_', ' ').title()
    except:
        pass
    
    return "Project"


# Text-based link extraction for non-PDF files
def extract_links_from_text(text: str) -> Dict[str, Any]:
    """
    Extract links from plain text (for DOCX, TXT, etc).
    
    Args:
        text: Plain text content
        
    Returns:
        Dictionary with classified links
    """
    # URL pattern
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    
    extracted_links = []
    for url in urls:
        category, platform = classify_link(url)
        extracted_links.append(ExtractedLink(
            url=url,
            category=category,
            platform=platform,
            text_context="",
            page_number=0
        ))
    
    classified = classify_all_links(extracted_links)
    
    return {
        'linkedin': classified.linkedin,
        'github': classified.github,
        'project_links': classified.project_links,
        'coding_profiles': [
            {
                'platform': cp['platform'],
                'username': cp['username'],
                'link': cp['url']
            } for cp in classified.coding_profiles
        ],
        'certifications_from_links': classified.certifications,
        'portfolio_links': classified.portfolio_links,
        'other_links': classified.other_links
    }