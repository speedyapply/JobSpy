"""How well a job fits the profile in profile.json, from its title and description.

The score (0-100) weighs four things:
  skills      55%  the technologies the job names that the profile has; a sibling
                   (Vue for React, PostgreSQL for MySQL) counts for part
  role        15%  the title is one of the profile's roles, and not senior or lead
  experience  15%  the years the job asks for against the profile's
  location    15%  remote, or in one of the profile's locations
A senior title, or asking 3+ years more than the profile has, lowers the whole score.

Jobs without a description (LinkedIn without fetch_description) are scored on their
title alone, and say so.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# name -> regex of the ways job ads write it (matched on lower case, no accents)
TECH = {
    "html": r"html5?",
    "css": r"css3?",
    "javascript": r"javascript|(?<![.\w])js\b|ecmascript|es6",
    "typescript": r"typescript|\bts\b",
    "react": r"react(?:\.?js)?(?! native)",
    "react native": r"react native",
    "next.js": r"next\.?js",
    "vue": r"vue(?:\.?js)?",
    "angular": r"angular(?:js)?",
    "svelte": r"svelte",
    "zustand": r"zustand",
    "redux": r"redux",
    "flutter": r"flutter",
    "dart": r"\bdart\b",
    "sass": r"\bsass\b|\bscss\b",
    "tailwind": r"tailwind(?:css)?",
    "bootstrap": r"bootstrap",
    "vite": r"\bvite\b",
    "material ui": r"material[ -]?ui|\bmui\b",
    "node.js": r"node(?:\.?js)?\b",
    "express": r"\bexpress(?:\.?js)?\b",
    "nestjs": r"nest\.?js",
    "rest api": r"\bapis?\s*rest|\brest(?:ful)?\b\s*(?:api|services|servicios)|restful",
    "graphql": r"graphql",
    "php": r"\bphp\b",
    "laravel": r"laravel",
    "symfony": r"symfony",
    "wordpress": r"wordpress",
    "drupal": r"drupal",
    "python": r"python",
    "django": r"django",
    "flask": r"flask",
    "fastapi": r"fastapi",
    "java": r"\bjava\b(?!\s*script)",
    "spring": r"spring(?:\s*boot)?",
    "kotlin": r"kotlin",
    "c#": r"c#|c sharp",
    ".net": r"\.net\b|dotnet|asp\.net",
    "c++": r"c\+\+",
    "golang": r"golang|\bgo\b(?= ?lang|,| developer| backend)",
    "ruby": r"\bruby\b|rails",
    "swift": r"\bswift\b",
    "sql": r"\bsql\b|t-sql|pl/sql",
    "oracle": r"oracle",
    "mysql": r"mysql|mariadb",
    "postgresql": r"postgre(?:s|sql)",
    "sql server": r"sql server|mssql",
    "mongodb": r"mongo(?:db)?",
    "redis": r"\bredis\b",
    "sequelize": r"sequelize",
    "prisma": r"prisma",
    "ejs": r"\bejs\b",
    "docker": r"docker",
    "kubernetes": r"kubernetes|\bk8s\b",
    "aws": r"\baws\b|amazon web services",
    "azure": r"azure",
    "gcp": r"\bgcp\b|google cloud",
    "ci/cd": r"ci/cd|ci ?cd|github actions|gitlab ci|jenkins",
    "git": r"\bgit\b",
    "github": r"github",
    "gitlab": r"gitlab",
    "jira": r"\bjira\b",
    "figma": r"figma",
    "postman": r"postman",
    "linux": r"linux",
    "bash": r"\bbash\b|shell script",
    "testing": r"\bjest\b|vitest|cypress|playwright|testing|tests? (?:unitarios|automatizados)",
    "ui/ux": r"ui/ux|ux/ui|\bux\b",
    "sap": r"\bsap\b|abap",
}

# a sibling of a skill the profile has counts for this much of a match
FAMILIES = (
    ({"react", "vue", "angular", "svelte", "next.js"}, 0.4),
    ({"react", "react native", "flutter"}, 0.4),
    ({"node.js", "nestjs", "express"}, 0.6),
    ({"sql", "mysql", "postgresql", "sql server", "oracle"}, 0.7),
    ({"sequelize", "prisma"}, 0.6),
    ({"zustand", "redux"}, 0.7),
    ({"sass", "tailwind", "bootstrap", "material ui", "css"}, 0.6),
    ({"git", "github", "gitlab"}, 0.8),
    ({"javascript", "typescript"}, 0.6),
)

SENIOR = r"\bsenior\b|\bsr\.?\b|\blead\b|\blider\b|arquitect|architect|principal|head of|\bmanager\b|jefe"
JUNIOR = r"junior|\bjr\.?\b|trainee|practicas|becari|sin experiencia"
DEV = r"desarroll|programador|developer|engineer|ingenier|software|\bdev\b"
LEVELS = ["a1", "a2", "b1", "b2", "c1", "c2"]


def normalise(text: object) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore")
    return text.decode().lower()


def present(value: object) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return str(value).strip() not in ("", "nan", "None")


@dataclass
class Match:
    score: int
    have: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    title_only: bool = False

    def notes(self) -> str:
        """One line for the CSV: what it has, what it lacks, what to watch"""
        parts = []
        if self.have:
            parts.append("tiene: " + ", ".join(self.have))
        if self.missing:
            parts.append("le falta: " + ", ".join(self.missing))
        parts += self.warnings
        if self.title_only:
            parts.append("solo título")
        return " | ".join(parts)


def detect_skills(text: str) -> list[str]:
    """The technologies a text names (a CV, say), in TECH's order"""
    text = normalise(text)
    return [name for name, pattern in TECH.items() if re.search(pattern, text)]


class Profile:
    def __init__(self, source: Path | dict[str, object]) -> None:
        data = (
            json.loads(source.read_text(encoding="utf-8"))
            if isinstance(source, Path)
            else source
        )
        self.skills = {normalise(s) for s in data.get("skills", [])}
        self.roles = [normalise(r) for r in data.get("roles", [])]
        self.years = float(data.get("years_experience", 0))
        self.locations = [normalise(loc) for loc in data.get("locations", [])]
        self.remote_ok = bool(data.get("remote_ok", True))
        self.english = normalise(data.get("english", "")).strip()

    def credit(self, tech: str) -> float:
        if tech in self.skills:
            return 1.0
        return max(
            (
                part
                for family, part in FAMILIES
                if tech in family and family & self.skills
            ),
            default=0.0,
        )

    def score(self, job: dict[str, object]) -> Match:
        title = normalise(job.get("title"))
        description = (
            normalise(job.get("description")) if present(job.get("description")) else ""
        )
        text = f"{title}\n{description}"
        warnings: list[str] = []

        # skills
        asked = [name for name, pattern in TECH.items() if re.search(pattern, text)]
        asked += [
            s
            for s in self.skills
            if s not in TECH and re.search(rf"\b{re.escape(s)}\b", text)
        ]
        weights = {
            t: 2.0 if re.search(TECH.get(t, re.escape(t)), title) else 1.0
            for t in asked
        }
        credits = {t: self.credit(t) for t in asked}
        have = [t for t in asked if credits[t] == 1.0]
        missing = [t for t in asked if credits[t] < 1.0]
        total = sum(weights.values())
        skills = sum(credits[t] * weights[t] for t in asked) / total if total else None
        if skills is None and description:
            skills = 0.4  # a description that names no technology: can't tell

        # role
        if any(role in title for role in self.roles):
            role = 1.0
        elif re.search(DEV, title):
            role = 0.6
        else:
            role = 0.2
        senior = bool(re.search(SENIOR, title))
        if senior and self.years < 4:
            role *= 0.4
            warnings.append("puesto senior")
        if re.search(JUNIOR, title):
            role = min(1.0, role + 0.2)

        # experience: the smallest "N años" the ad asks for
        asked_years = [
            int(n)
            for n in re.findall(
                r"(\d{1,2})\s*\+?\s*(?:o mas\s+)?(?:anos?|years?)", text
            )
            if 0 < int(n) <= 15
        ]
        experience = 0.7
        gap = 0.0
        if asked_years:
            need = min(asked_years)
            gap = need - self.years
            experience = (
                1.0 if gap <= 0 else 0.6 if gap <= 1 else 0.3 if gap <= 2 else 0.0
            )
            if gap > 0:
                warnings.append(f"pide {need}+ años")
        elif senior:
            experience = 0.2

        # location
        modality = normalise(job.get("work_from_home_type"))
        remote = (
            job.get("is_remote") in (True, "True", "true")
            or "teletrabajo" in modality
            or "remote" in modality
        )
        place = normalise(job.get("location"))
        local = any(loc in place or loc in text for loc in self.locations)
        if remote and self.remote_ok:
            location = 1.0
        elif local:
            location = 1.0
        elif "hibrido" in modality or "hybrid" in modality:
            location = 0.3
            warnings.append(f"híbrido en {job.get('location')}")
        elif place:
            location = 0.0
            warnings.append(f"presencial en {job.get('location')}")
        else:
            location = 0.5

        # languages: an English level above the profile's is worth knowing
        level = re.search(
            r"ingles[^.\n]{0,40}?\b(c1|c2)\b|english[^.\n]{0,40}?\b(c1|c2)\b|ingles nativo|native english",
            text,
        )
        if level and self.english in LEVELS:
            asked_level = (level.group(1) or level.group(2) or "c2").lower()
            if LEVELS.index(asked_level) > LEVELS.index(self.english):
                warnings.append(f"inglés {asked_level.upper()}")

        parts = [(skills, 0.55), (role, 0.15), (experience, 0.15), (location, 0.15)]
        weight = sum(w for value, w in parts if value is not None)
        value = sum(v * w for v, w in parts if v is not None) / weight
        # far from the level asked: good skills alone don't make it a fit
        if senior and self.years < 4:
            value *= 0.8
        if gap >= 3:
            value *= 0.7
        return Match(
            score=round(value * 100),
            have=have,
            missing=missing,
            warnings=warnings,
            title_only=not description,
        )
