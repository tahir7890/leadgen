"""Lead data normalization, deduplication, and cleaning."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

EMAIL_RE = re.compile(r"^([^\s@]+)?@[^\s@]+\.[^\s@]+$", re.I)
PHONE_CLEAN_RE = re.compile(r"[^\d\+\-\(\)\s]")


def normalize_domain(domain: str) -> str:
    """Strip protocol, www, and path from a domain string."""
    d = (
        domain.strip()
        .lower()
        .replace("https://", "")
        .replace("http://", "")
        .replace("www.", "")
    )
    return d.split("/")[0].split("?")[0].strip(".")


def normalize_email(value: Any) -> Optional[str]:
    """Validate and normalize an email address."""
    if not value:
        return None
    if not isinstance(value, str):
        value = str(value)
    e = value.strip().lower()
    # Remove common junk
    if e.startswith("mailto:"):
        e = e[7:]
    if not e or "@" not in e:
        return None
    return e if EMAIL_RE.match(e) else None


def normalize_phone(value: Any) -> Optional[str]:
    """Normalize and validate a phone number."""
    if not value:
        return None
    if not isinstance(value, str):
        value = str(value)
    phone = value.strip()
    if phone.startswith("tel:"):
        phone = phone[4:]
    phone = phone.strip()
    # Remove non-phone characters except +, -, (, ), spaces, digits
    cleaned = PHONE_CLEAN_RE.sub("", phone).strip()
    # Accept masked phone numbers or short hints from RocketReach
    if not cleaned:
        return None
    return cleaned


def normalize_linkedin(value: Any) -> Optional[str]:
    """Validate and normalize a LinkedIn profile URL."""
    if not value:
        return None
    if not isinstance(value, str):
        value = str(value)
    url = value.strip()
    if not url:
        return None
    if not url.startswith("http"):
        url = f"https://{url}"
    # Strictly enforce linkedin.com
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower().split(":")[0]  # strip port
        if host != "linkedin.com" and not host.endswith(".linkedin.com"):
            return None
        # Must start with exactly https://www.linkedin.com/
        if host == "linkedin.com":
            host = "www.linkedin.com"
        clean_url = f"https://{host}{parsed.path}"
        # Strip trailing slash
        return clean_url.rstrip("/")
    except Exception:
        return None


def normalize_confidence(value: Any) -> Optional[float]:
    """Convert confidence score to float, clamped to [0, 1] or [0, 100]."""
    if value is None:
        return None
    try:
        f = float(value)
        # Normalize to 0-100 range
        if 0 <= f <= 1:
            return round(f * 100, 2)
        if 0 <= f <= 100:
            return round(f, 2)
        return None
    except (TypeError, ValueError):
        return None


def normalize_text(value: Any, max_length: int = 500) -> Optional[str]:
    """Clean and truncate a text field."""
    if not value:
        return None
    if not isinstance(value, str):
        value = str(value)
    cleaned = " ".join(value.split()).strip()  # Collapse whitespace
    return cleaned[:max_length] if cleaned else None


def build_dedupe_key(
    email: Optional[str],
    linkedin: Optional[str],
    full_name: Optional[str],
    company_domain: str,
    company_name: Optional[str],
) -> str:
    """Build a deduplication key: email > linkedin > name+company hash."""
    if email:
        return f"email:{email.lower()}"
    if linkedin:
        # Normalize linkedin URL for deduplication
        clean = linkedin.lower().rstrip("/")
        return f"linkedin:{clean}"
    raw = f"{(full_name or '').lower().strip()}|{company_domain.lower()}|{(company_name or '').lower().strip()}"
    return f"name_company:{hashlib.sha256(raw.encode()).hexdigest()[:32]}"


def normalize_leads(
    company_id: str, domain: str, raw_leads: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Normalize, validate, and deduplicate a list of raw lead dicts.

    Returns a list of clean lead dicts ready for Supabase upsert.
    """
    company_domain = normalize_domain(domain)
    seen_keys: set[str] = set()
    out: list[dict[str, Any]] = []

    for raw in raw_leads:
        if not isinstance(raw, dict):
            continue

        # Extract and normalize fields
        raw_name = normalize_text(raw.get("fullName") or raw.get("full_name") or raw.get("name"), max_length=200)
        full_name = raw_name.title() if raw_name else None
        email = normalize_email(raw.get("email") or raw.get("mail"))
        linkedin = normalize_linkedin(
            raw.get("linkedinUrl") or raw.get("linkedin_url") or raw.get("linkedin") or raw.get("linkdin id") or raw.get("linkedin id")
        )
        company_name = normalize_text(
            raw.get("companyName") or raw.get("company_name") or raw.get("company"),
            max_length=200,
        )
        job_title = normalize_text(
            raw.get("jobTitle") or raw.get("job_title") or raw.get("title"),
            max_length=200,
        )
        phone = normalize_phone(raw.get("phone") or raw.get("number"))
        location = normalize_text(raw.get("location") or raw.get("address"), max_length=200)
        seniority = normalize_text(raw.get("seniority"), max_length=100)
        department = normalize_text(raw.get("department"), max_length=100)
        confidence = normalize_confidence(
            raw.get("confidenceScore") or raw.get("confidence_score")
        )

        # Must have at least one identifying field
        if not full_name and not email and not linkedin and not phone:
            continue

        # Build dedup key and skip duplicates
        dedupe_key = build_dedupe_key(email, linkedin, full_name, company_domain, company_name)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        # Split name into parts
        name_parts = full_name.split() if full_name else []
        first_name = name_parts[0] if name_parts else None
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else None

        # Infer company_name from domain if missing
        if not company_name:
            company_name = company_domain.split(".")[0].capitalize() if company_domain else None

        out.append(
            {
                "company_id": company_id,
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "job_title": job_title,
                "seniority": seniority,
                "department": department,
                "company_name": company_name,
                "company_domain": company_domain,
                "linkedin_url": linkedin,
                "email": email,
                "phone": phone,
                "location": location,
                "source": str(raw.get("source", "rocketreach")),
                "confidence_score": confidence,
                "dedupe_key": dedupe_key,
            }
        )

    return out
