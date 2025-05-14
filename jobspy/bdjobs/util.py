#util.py
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional, List, Dict, Any

from jobspy.model import Location, Country


def parse_location(location_text: str, country: str = "bangladesh") -> Location:
    """
    Parses location text into a Location object
    :param location_text: Location text from job listing
    :param country: Default country
    :return: Location object
    """
    parts = location_text.split(",")
    if len(parts) >= 2:
        city = parts[0].strip()
        state = parts[1].strip()
        return Location(
            city=city,
            state=state,
            country=Country.from_string(country)
        )
    else:
        return Location(
            city=location_text.strip(),
            country=Country.from_string(country)
        )


def parse_date(date_text: str) -> Optional[datetime]:
    """
    Parses date text into a datetime object
    :param date_text: Date text from job listing
    :return: datetime object or None if parsing fails
    """
    from .constant import date_formats
    
    try:
        # Clean up date text
        if "Deadline:" in date_text:
            date_text = date_text.replace("Deadline:", "").strip()
        
        # Try different date formats
        for fmt in date_formats:
            try:
                return datetime.strptime(date_text, fmt)
            except ValueError:
                continue
        
        return None
    except Exception:
        return None


def find_job_listings(soup: BeautifulSoup) -> List[Any]:
    """
    Finds job listing elements in the HTML
    :param soup: BeautifulSoup object
    :return: List of job card elements
    """
    from .constant import job_selectors
    
    # Try different selectors
    for selector in job_selectors:
        if "." in selector:
            tag_name, class_name = selector.split(".", 1)
            elements = soup.find_all(tag_name, class_=class_name)
            if elements and len(elements) > 0:
                return elements
    
    # If no selectors match, look for job detail links
    job_links = soup.find_all("a", href=lambda h: h and "jobdetail" in h.lower())
    if job_links:
        # Return parent elements of job links
        return [link.parent for link in job_links]
    
    return []


def is_job_remote(title: str, description: str = None, location: Location = None) -> bool:
    """
    Determines if a job is remote based on title, description, and location
    :param title: Job title
    :param description: Job description
    :param location: Job location
    :return: True if job is remote, False otherwise
    """
    remote_keywords = ["remote", "work from home", "wfh", "home based"]
    
    # Combine all text fields
    full_text = title.lower()
    if description:
        full_text += " " + description.lower()
    if location:
        full_text += " " + location.display_location().lower()
    
    # Check for remote keywords
    return any(keyword in full_text for keyword in remote_keywords)