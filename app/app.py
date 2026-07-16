"""Streamlit dashboard for the IOOS Economic Impact Evidence Matrix."""

from __future__ import annotations

import csv
import base64
import html as html_lib
import io
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
DATA_DIR = REPO_ROOT / "data"
EVIDENCE_PATH = DATA_DIR / "evidence_matrix.csv"
SOURCE_PATH = DATA_DIR / "source_registry.csv"
REVIEW_PATH = DATA_DIR / "review_needed.csv"
STAGED_EVIDENCE_PATH = DATA_DIR / "staged_evidence.csv"
BEST_SOURCES_PATH = DATA_DIR / "best_sources.csv"
REGIONAL_TARGETS_PATH = DATA_DIR / "regional_research_targets.csv"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_matrix.py"
FILLED_BRIEFING_PATH = REPO_ROOT / "outputs" / "IOOS_Congressional_Briefing_Filled.html"
UCAR_LOGO_PATH = APP_DIR / "logo-ucar.avif"
COL_LOGO_PATH = APP_DIR / "col-logo.avif"
IOOS_HERO_IMAGE_PATH = APP_DIR / "HERO1.png"
MARACOOS_COVERAGE_MAP_PATH = APP_DIR / "MARACOOS Coverage Map.png"
DATA_TO_DECISION_FLOW_PATH = APP_DIR / "data to decision flow chart.png"
IOOS_COVERAGE_MAP_PATH = APP_DIR / "IOOS Coverage Mao.png"
IOOS_OCEAN_SYSTEMS_PATH = APP_DIR / "IOOS in ocean.jpg"
ANIMAL_TAGS_IMAGE_PATH = APP_DIR / "Animal atn-tags.jpg"

INTAKE_SCHEMA = [
    "row_id",
    "Date record created",
    "Impact domain",
    "IOOS component",
    "Region",
    "IOOS region code",
    "User group",
    "Decision supported",
    "Economic pathway",
    "Metric",
    "Metric year / dollar year",
    "Source",
    "Source URL",
    "Evidence strength",
    "IOOS attribution strength",
    "Economic number type",
    "IOOS role type",
    "Source verification needed",
    "Allowed use",
    "Not allowed use",
    "Limitations",
    "Claim allowed",
    "Update frequency",
    "AI extraction notes",
]

INTAKE_OPTIONAL_COLUMNS = {
    "Date record created",
    "Economic number type",
    "IOOS role type",
    "Allowed use",
    "Not allowed use",
}

INTAKE_TO_EVIDENCE_COLUMNS = {
    "row_id": "row_id",
    "Date record created": "date_record_created",
    "Impact domain": "impact_domain",
    "IOOS component": "ioos_component",
    "Region": "region",
    "IOOS region code": "ioos_region_code",
    "User group": "user_group",
    "Decision supported": "decision_supported",
    "Economic pathway": "economic_pathway",
    "Metric": "metric",
    "Metric year / dollar year": "metric_year_or_dollar_year",
    "Source": "source_id",
    "Evidence strength": "evidence_strength",
    "IOOS attribution strength": "ioos_attribution_strength",
    "Economic number type": "economic_number_type",
    "IOOS role type": "ioos_role_type",
    "Source verification needed": "source_verification_needed",
    "Allowed use": "allowed_use",
    "Not allowed use": "not_allowed_use",
    "Limitations": "limitations",
    "Claim allowed": "claim_allowed",
    "Update frequency": "update_frequency",
    "AI extraction notes": "ai_extraction_notes",
}

STAGED_DB_TO_INTAKE_COLUMNS = {
    "row_id": "row_id",
    "date_record_created": "Date record created",
    "impact_domain": "Impact domain",
    "ioos_component": "IOOS component",
    "region": "Region",
    "ioos_region_code": "IOOS region code",
    "user_group": "User group",
    "decision_supported": "Decision supported",
    "economic_pathway": "Economic pathway",
    "metric": "Metric",
    "metric_year_or_dollar_year": "Metric year / dollar year",
    "source": "Source",
    "source_url": "Source URL",
    "evidence_strength": "Evidence strength",
    "ioos_attribution_strength": "IOOS attribution strength",
    "economic_number_type": "Economic number type",
    "ioos_role_type": "IOOS role type",
    "source_verification_needed": "Source verification needed",
    "allowed_use": "Allowed use",
    "not_allowed_use": "Not allowed use",
    "limitations": "Limitations",
    "claim_allowed": "Claim allowed",
    "update_frequency": "Update frequency",
    "ai_extraction_notes": "AI extraction notes",
}

INTAKE_TO_STAGED_DB_COLUMNS = {
    intake_column: db_column
    for db_column, intake_column in STAGED_DB_TO_INTAKE_COLUMNS.items()
}

PATH_TABLES = {
    STAGED_EVIDENCE_PATH: "staged_evidence",
    BEST_SOURCES_PATH: "best_sources",
}

TABLE_DELETE_FILTERS = {
    "source_registry": ("source_id", "not.is.null"),
    "evidence_matrix": ("row_id", "not.is.null"),
    "review_needed": ("id", "not.is.null"),
    "staged_evidence": ("id", "not.is.null"),
    "best_sources": ("source_id", "not.is.null"),
}

TABLE_CONFLICT_KEYS = {
    "source_registry": "source_id",
    "evidence_matrix": "row_id",
    "best_sources": "source_id",
}

TABLE_ORDER_COLUMNS = {
    "source_registry": "source_id",
    "evidence_matrix": "row_id",
    "review_needed": "id",
    "staged_evidence": "id",
    "best_sources": "source_id",
}

SUPABASE_KEY_NAMES = [
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_KEY",
    "SUPABASE_ANON_KEY",
    "service_role_key",
    "service_key",
    "anon_key",
    "key",
]

SUPABASE_URL_NAMES = [
    "SUPABASE_URL",
    "supabase_url",
    "url",
]

SUPABASE_SECRET_SECTIONS = [
    ("supabase",),
    ("connections", "supabase"),
]

INTAKE_REQUIRED_VALUES = [
    "Source",
    "Source URL",
    "IOOS region code",
    "Claim allowed",
    "Limitations",
    "Evidence strength",
    "IOOS attribution strength",
]

ALLOWED_RATING_VALUES = [
    "Strong",
    "Medium",
    "Contextual",
    "Modeled",
    "Needs verification",
]
ALLOWED_RATINGS = set(ALLOWED_RATING_VALUES)

ECONOMIC_NUMBER_TYPE_VALUES = [
    "Observed dollar benefit",
    "Modeled dollar estimate",
    "Dollar exposure/context",
    "Operational metric only",
    "No economic number",
    "Do not use",
]
ALLOWED_ECONOMIC_NUMBER_TYPES = set(ECONOMIC_NUMBER_TYPE_VALUES)

IOOS_ROLE_TYPE_VALUES = [
    "Direct impact source",
    "Direct decision-support source",
    "Backend data source",
    "Partner/infrastructure source",
    "Context only",
    "No IOOS attribution",
]
ALLOWED_IOOS_ROLE_TYPES = set(IOOS_ROLE_TYPE_VALUES)

IOOS_REGION_OPTIONS = {
    "AOOS": "Alaska",
    "CARICOOS": "Caribbean",
    "CeNCOOS": "Central and Northern California",
    "GCOOS": "Gulf of America",
    "GLOS": "Great Lakes",
    "MARACOOS": "Mid-Atlantic",
    "NANOOS": "Pacific Northwest",
    "NERACOOS": "Northeast",
    "PacIOOS": "Pacific Islands",
    "SCCOOS": "Southern California",
    "SECOORA": "Southeast Atlantic",
}
NON_ASSOCIATION_REGION_CODES = {
    "National": "National or national-scale IOOS evidence",
    "Multiple": "Multiple IOOS regions",
    "Unknown": "Region code needs follow-up",
}
ALLOWED_IOOS_REGION_CODES = set(IOOS_REGION_OPTIONS) | set(NON_ASSOCIATION_REGION_CODES)
EVIDENCE_ROW_ID_PREFIX = "EVID"
EVIDENCE_ROW_ID_WIDTH = 4
EVIDENCE_ROW_ID_RE = re.compile(r"^EVID-(\d{4})$")
BRIEFING_ROW_IDS = {
    "ports": "EVID-0001",
    "habs": "EVID-0005",
    "hf_radar": "EVID-0009",
    "ocean_enterprise": "EVID-0014",
}
MARACOOS_CODE = "MARACOOS"
MARACOOS_SUPABASE_TABLES = ("MARACOOS", "maracoos")
APP_DISPLAY_SOURCE_VERIFICATION_NEEDED_VALUE = "Yes"
MARACOOS_COLUMN_ALIASES = {
    "Date record created": "date_record_created",
    "Impact domain": "impact_domain",
    "IOOS component": "ioos_component",
    "Region": "region",
    "IOOS region code": "ioos_region_code",
    "User group": "user_group",
    "Decision supported": "decision_supported",
    "Economic pathway": "economic_pathway",
    "Metric": "metric",
    "Metric year / dollar year": "metric_year_or_dollar_year",
    "Source": "source",
    "Source URL": "source_url",
    "Evidence strength": "evidence_strength",
    "IOOS attribution strength": "ioos_attribution_strength",
    "Economic number type": "economic_number_type",
    "IOOS role type": "ioos_role_type",
    "Source verification needed": "source_verification_needed",
    "Allowed use": "allowed_use",
    "Not allowed use": "not_allowed_use",
    "Limitations": "limitations",
    "Claim allowed": "claim_allowed",
    "Update frequency": "update_frequency",
    "AI extraction notes": "ai_extraction_notes",
}
MARACOOS_DISPLAY_COLUMNS = [
    "row_id",
    "date_record_created",
    "impact_domain",
    "ioos_component",
    "region",
    "ioos_region_code",
    "user_group",
    "decision_supported",
    "economic_pathway",
    "metric",
    "metric_year_or_dollar_year",
    "source",
    "source_id",
    "source_url",
    "evidence_strength",
    "ioos_attribution_strength",
    "economic_number_type",
    "ioos_role_type",
    "source_verification_needed",
    "allowed_use",
    "not_allowed_use",
    "claim_allowed",
    "limitations",
    "update_frequency",
    "ai_extraction_notes",
    "data_origin",
]
MARACOOS_STRENGTH_RANK = {
    "Strong": 0,
    "Medium": 1,
    "Modeled": 2,
    "Contextual": 3,
    "Needs verification": 4,
}
IOOS_TOP_STATEMENT = (
    "IOOS helps coastal communities, ports, emergency managers, fishermen, offshore operators, "
    "and coastal businesses make safer, faster, and more cost-effective decisions using real-time ocean data."
)
MARACOOS_TOP_STATEMENT = (
    "MARACOOS helps Mid-Atlantic communities, ports, emergency managers, fishermen, offshore operators, "
    "and coastal businesses make safer, faster, and more cost-effective decisions using real-time ocean data."
)
FUNDING_TO_OUTCOME_STATEMENT = (
    "Continued IOOS funding keeps regional observing assets, data systems, and decision-support tools "
    "operational. Increased funding would improve coverage, reliability, modernization, and service to "
    "high-risk coastal and maritime users."
)
FLAT_OR_REDUCED_FUNDING_RISK = (
    "Reduced or stagnant funding could limit regional observing coverage, delay sensor replacement, "
    "reduce data product maintenance, constrain regional stakeholder support, and weaken the ability to "
    "translate national ocean infrastructure into state and local decision support."
)
PLACEHOLDER_BRIEF_NOTICE = (
    "Draft placeholder only: no claim, metric, source label, legislative statement, or example in this "
    "preview should be treated as verified or externally usable until reviewed against the source record."
)
FEDERAL_FUNDING_PROTECTS = [
    "Observing assets, including buoys, shore stations, HF radar, sensors, and gliders",
    "Data systems that move quality-controlled observations into public and partner tools",
    "Forecasts and decision-support products for ports, hazards, fisheries, and water quality",
    "Web tools, maps, APIs, and user support that make federal ocean data usable locally",
    "Regional staff capacity to work with state, local, maritime, and emergency-response users",
]
FEDERAL_FUNDING_RISKS = [
    "Reduced observing coverage and less redundancy in high-risk coastal and offshore areas",
    "Delayed replacement of aging sensors and slower modernization of data systems",
    "Less maintenance for forecasts, web products, and public-facing decision tools",
    "Less regional support for stakeholders who need help applying national ocean data locally",
]
MID_ATLANTIC_STATE_RELEVANCE = [
    ("New York", "NY-NJ Harbor operations, coastal flooding, beach economies, offshore wind, fisheries, and water quality."),
    ("New Jersey", "Port corridors, coastal flooding, beach tourism, offshore wind areas, fisheries, and water-quality decisions."),
    ("Delaware", "Delaware Bay navigation, coastal hazards, fisheries, shellfish and water quality, offshore wind, and emergency response."),
    ("Maryland", "Chesapeake and coastal flooding, Port of Baltimore connections, fisheries, water quality, and emergency management."),
    ("Virginia", "Hampton Roads ports, naval and military operations, coastal flooding, offshore wind, fisheries, and emergency response."),
    ("North Carolina", "Outer Banks hazards, fisheries, offshore operations, military and naval coordination, and emergency response where applicable."),
]

REQUIRED_ADD_FIELDS = [
    "impact_domain",
    "ioos_component",
    "ioos_region_code",
    "source_id",
    "claim_allowed",
    "limitations",
    "evidence_strength",
    "ioos_attribution_strength",
    "economic_number_type",
    "ioos_role_type",
    "allowed_use",
    "not_allowed_use",
]

REPORT_STATUS_ORDER = [
    "report-ready",
    "use-with-caution",
    "background-only",
    "needs-follow-up",
]

UPDATE_FREQUENCY_BUCKETS = {
    "Quarterly": [r"\bquarterly\b"],
    "Annual": [r"\bannual\b", r"\byearly\b"],
    "Real-time": [r"\breal[- ]?time\b"],
    "Periodic": [r"\bperiodic\b", r"\bongoing\b"],
    "Event-based": [r"\bevent[- ]?based\b"],
}

CAUSAL_TERMS = [
    r"\bcaused?\b",
    r"\bcreated?\b",
    r"\battribut(?:e|ed|able|ion)\b",
    r"\bsaved?\b",
    r"\bprevent(?:ed|s|ing)?\b",
    r"\bavoided?\b",
    r"\breduced?\b",
    r"\bincreased?\b",
    r"\bprotected?\b",
    r"\bROI\b",
]

CONSERVATIVE_CLAIM_TERMS = [
    r"\bcan\b",
    r"\bcould\b",
    r"\bsupport",
    r"\bhelp",
    r"\bsuggest",
    r"\bestimated\b",
    r"\bmodeled\b",
    r"\bpotential\b",
    r"\bpending\b",
    r"\bwhere documented\b",
]

PROJECT_TIMELINE = [
    {
        "start": date(2026, 6, 1),
        "end": date(2026, 6, 29),
        "milestone": "Discovery and Prototype",
        "focus": "Explore AI workflows, build the first evidence workflow, identify economic data sources, and compare research tools.",
    },
    {
        "start": date(2026, 6, 30),
        "end": date(2026, 7, 8),
        "milestone": "Expansion and Scaling",
        "focus": "Vet information, expand the dataset, scale the framework for MARACOOS, and add imagery to summary materials.",
    },
    {
        "start": date(2026, 7, 8),
        "end": date(2026, 7, 14),
        "milestone": "Refinement",
        "focus": "Start finalizing the national report, expand regional evidence where useful, and document the workflow metadata.",
    },
    {
        "start": date(2026, 7, 14),
        "end": date(2026, 7, 21),
        "milestone": "Internal Review",
        "focus": "Identify IOOS, MIIS, and COL reviewers and begin the AI tools summary for COL.",
    },
    {
        "start": date(2026, 7, 21),
        "end": date(2026, 7, 28),
        "milestone": "Develop Materials",
        "focus": "Develop retreat materials and incorporate early reviewer comments.",
    },
    {
        "start": date(2026, 7, 28),
        "end": date(2026, 8, 4),
        "milestone": "Editing",
        "focus": "Continue incorporating comments and finalize report, workflow, and presentation materials.",
    },
    {
        "start": date(2026, 8, 4),
        "end": date(2026, 8, 11),
        "milestone": "Finalize",
        "focus": "Complete final polishing of the evidence matrix, workflow documentation, report, and retreat materials.",
    },
    {
        "start": date(2026, 8, 12),
        "end": date(2026, 8, 13),
        "milestone": "Boulder Retreat",
        "focus": "Present recommendations, facilitate discussion, gather staff feedback, and identify implementation priorities.",
    },
]

PROJECT_OBJECTIVES = [
    "Build a defensible national IOOS economic impact evidence base.",
    "Keep AI-generated rows staged until human verification clears them.",
    "Distinguish measured, modeled, contextual, and weak-attribution claims.",
    "Use MARACOOS as the first regional pilot for scaling the framework.",
    "Generate communication-ready report and briefing materials from vetted evidence.",
]

PROJECT_GOVERNANCE_RULES = [
    {
        "Area": "Staged evidence",
        "Rule": "Candidate rows stay outside the live matrix until Source verification needed is set to No.",
    },
    {
        "Area": "Claim language",
        "Rule": "Claims must stay conservative when evidence is modeled, contextual, or still under review.",
    },
    {
        "Area": "Source registry",
        "Rule": "Every official evidence row must point to an authoritative source_id with a working source URL.",
    },
    {
        "Area": "Reviewer follow-up",
        "Rule": "Validation warnings and errors are treated as operator tasks before report-ready use.",
    },
    {
        "Area": "Briefing sources",
        "Rule": "The best_sources table is the curated shortlist for policy briefs and final report materials.",
    },
]

PROJECT_EVIDENCE_PRIORITIES = [
    {
        "Priority": "PORTS and maritime transportation",
        "Need": "Local case studies, port-safety benefits, draft optimization, and national scenario boundaries.",
    },
    {
        "Priority": "HF radar and search and rescue",
        "Need": "Operational SAROPS evidence, search-area reduction cases, and cautious public-safety value framing.",
    },
    {
        "Priority": "HAB forecasts and seafood decisions",
        "Need": "Forecast value, closure timing, avoided false alarms, and state or regional management evidence.",
    },
    {
        "Priority": "Ocean acidification and shellfish hatcheries",
        "Need": "Monitoring-to-decision pathways, hatchery adaptation evidence, and clear separation from sector exposure.",
    },
    {
        "Priority": "Ocean Enterprise and marine economy context",
        "Need": "Sector scale from Ocean Enterprise, BEA MESA, ENOW, NOEP, and other macroeconomic baselines.",
    },
    {
        "Priority": "MARACOOS regional pilot",
        "Need": "A repeatable regional case structure that can later extend to one or two additional regions.",
    },
]

APP_ROLES = {
    "Viewer": "Explore dashboards, sources, evidence rows, and exports.",
    "Contributor": "Stage candidate evidence and draft new source records.",
    "Reviewer": "Verify evidence, resolve warnings, and promote trusted rows.",
    "Admin": "Manage users, roles, source settings, and release readiness.",
}

APP_NAVIGATION = [
    "Overview",
    "Dashboard",
    "Regions",
    "Financial Evidence",
    "Evidence Database",
    "Briefs & Outputs",
    "Best Sources",
    "Review / Admin",
]

REVIEW_ADMIN_NAVIGATION = [
    "Evidence Intake",
    "Review Evidence",
    "Validation Queue",
    "Add Evidence Row",
    "Run Validation",
    "Regional Builds",
    "Project Roadmap",
]

BEST_SOURCE_SCHEMA = [
    "source_id",
    "source_name",
    "source_url",
    "source_type",
    "ioos_region_code",
    "priority_tier",
    "briefing_role",
    "impact_domains",
    "staged_row_ids",
    "key_metrics",
    "evidence_profile",
    "attribution_profile",
    "recommended_claim_language",
    "caveats",
    "source_verification_needed",
    "status",
]

REJECTION_REASON_OPTIONS = [
    "Bad citation",
    "Link to document does not work",
    "Wrong metric",
    "AI hallucination",
    "Source does not support the claim",
    "Other",
]

EVIDENCE_DATABASE_COLUMNS = [
    "row_id",
    "date_record_created",
    "impact_domain",
    "ioos_component",
    "region",
    "ioos_region_code",
    "metric",
    "claim_allowed",
    "source_name",
    "source_url",
    "source_type",
    "source_verification_status",
    "evidence_strength",
    "ioos_attribution_strength",
    "economic_number_type",
    "ioos_role_type",
    "source_verification_needed",
    "allowed_use",
    "not_allowed_use",
    "limitations",
]

METHOD_STEPS = [
    {
        "Step": "1. Collect",
        "What happens": "Gather candidate claims, source URLs, metrics, and regional context.",
        "Owner": "Contributor",
    },
    {
        "Step": "2. Stage",
        "What happens": "Hold AI-assisted or newly found rows outside the official matrix.",
        "Owner": "Contributor",
    },
    {
        "Step": "3. Review",
        "What happens": "Check source support, attribution, limitations, and claim language.",
        "Owner": "Reviewer",
    },
    {
        "Step": "4. Promote",
        "What happens": "Move verified rows into the official evidence matrix.",
        "Owner": "Reviewer",
    },
    {
        "Step": "5. Use",
        "What happens": "Export trusted data for reports, briefs, presentations, and updates.",
        "Owner": "Viewer",
    },
]

NARRATIVE_TAB_LABELS = [
    "What is IOOS?",
    "Sectors supported",
    "System cost",
    "Return case studies",
    "How we work",
]

EVIDENCE_ATLAS_LEVELS = [
    {
        "key": "level_1",
        "label": "Direct Reported Dollar Values",
        "title": "Direct Reported Dollar Values",
        "definition": "A source reports a dollar value for benefits, savings, avoided costs, or other monetized outcomes.",
        "safe_use": "Record the published value, dollar year, source, and caveat; do not recalculate unless an explicit adjustment method is stored.",
    },
    {
        "key": "level_2",
        "label": "Operational Cost Savings",
        "title": "Operational Cost Savings",
        "definition": "A source documents operational efficiency such as reduced hours, fuel, delay, sampling, inspection, or closure time.",
        "safe_use": "Use the operational metric directly unless the source also provides the dollar conversion.",
    },
    {
        "key": "level_3",
        "label": "Avoided Losses",
        "title": "Avoided Losses",
        "definition": "A source estimates or documents avoided damage, search costs, response costs, closures, vessel losses, or hazard impacts.",
        "safe_use": "Keep the counterfactual and uncertainty language attached to the claim.",
    },
    {
        "key": "level_4",
        "label": "Economic Activity Supported",
        "title": "Economic Activity Supported",
        "definition": "A source sizes the sector, port, fishery, tourism economy, cargo activity, or other exposure supported by IOOS information.",
        "safe_use": "Use as context only; never add these values to documented benefit totals.",
    },
]

EVIDENCE_ATLAS_LEVEL_BY_KEY = {
    level["key"]: level
    for level in EVIDENCE_ATLAS_LEVELS
}

EVIDENCE_ATLAS_UNCLASSIFIED = {
    "key": "unclassified",
    "label": "Needs Classification",
    "title": "Needs Classification",
    "definition": "The current row does not yet carry enough claim-use metadata for a financial evidence category.",
    "safe_use": "Review the metric, economic number type, allowed use, and limitations before using externally.",
}

EVIDENCE_ATLAS_TEXT_COLUMNS = [
    "impact_domain",
    "ioos_component",
    "region",
    "ioos_region_code",
    "user_group",
    "decision_supported",
    "economic_pathway",
    "metric",
    "economic_number_type",
    "ioos_role_type",
    "allowed_use",
    "not_allowed_use",
    "claim_allowed",
    "limitations",
    "ai_extraction_notes",
    "source_id",
    "source_name",
    "source_type",
]

ATLAS_OPERATIONAL_PATTERNS = [
    r"\btransit\b",
    r"\bfuel\b",
    r"\bwaiting\b",
    r"\bdelay",
    r"\bhours?\b",
    r"\bflight hours?\b",
    r"\bvessel hours?\b",
    r"\bsampling trips?\b",
    r"\binspection",
    r"\bclosure",
    r"\bdredg",
    r"\bpilot",
    r"\bthroughput\b",
    r"\befficien",
]

ATLAS_AVOIDED_LOSS_PATTERNS = [
    r"\bavoid",
    r"\bprevent",
    r"\breduc",
    r"\bdamage",
    r"\bloss",
    r"\bstorm",
    r"\bsurge",
    r"\bflood",
    r"\boil spill",
    r"\bspill response",
    r"\bsearch\b",
    r"\brescue\b",
    r"\bsarops\b",
    r"\bhf radar\b",
    r"\brip current",
    r"\bevacu",
    r"\bemergency response",
]

ATLAS_ECONOMIC_ACTIVITY_PATTERNS = [
    r"\bcargo\b",
    r"\btonnage\b",
    r"\bship calls?\b",
    r"\bpassengers?\b",
    r"\blandings?\b",
    r"\bharvest\b",
    r"\bbeach visitors?\b",
    r"\btourism\b",
    r"\bGDP\b",
    r"\bjobs?\b",
    r"\beconomic activity\b",
    r"\bmarket footprint\b",
    r"\bsector size\b",
    r"\bexposure\b",
]

SECTOR_STORYLINES = [
    {
        "name": "Maritime transportation and ports",
        "keywords": ["ports", "port", "maritime", "navigation", "shipping", "commerce"],
        "why": "Real-time water levels, currents, bridge air gap, and weather information help pilots, vessel operators, and ports make safer and more efficient movement decisions.",
    },
    {
        "name": "Seafood, shellfish, and fisheries",
        "keywords": ["hab", "shellfish", "fisher", "seafood", "aquaculture", "acidification", "oxygen"],
        "why": "Forecasts and monitoring can help managers target sampling, time closures and reopenings, protect hatchery operations, and understand habitat conditions.",
    },
    {
        "name": "Emergency response and maritime safety",
        "keywords": ["search", "rescue", "sarops", "hf radar", "hfr", "emergency", "safety", "spill"],
        "why": "Surface-current data, models, and regional products support search planning, spill response, storm preparation, and other time-sensitive public-safety decisions.",
    },
    {
        "name": "Coastal hazards and resilience",
        "keywords": ["hazard", "resilience", "flood", "storm", "beach", "rip", "digital coast"],
        "why": "Observations, webcams, forecasts, and planning tools give communities better situational awareness for flooding, erosion, beach safety, and resilience planning.",
    },
    {
        "name": "Ocean technology and the blue economy",
        "keywords": ["ocean enterprise", "technology", "data services", "blue economy", "marine economy"],
        "why": "IOOS data services, Regional Association websites, and ocean observing capability support a broader market of data users, service providers, and ocean-technology firms.",
    },
    {
        "name": "Offshore wind and marine operations",
        "keywords": ["offshore wind", "wind", "energy", "metocean", "construction", "blade"],
        "why": "Metocean observations and forecast products can support safer planning windows, reduced uncertainty, and better coordination for offshore energy and marine operations.",
    },
]

SYSTEM_COST_COMPONENTS = [
    {
        "name": "Regional operations",
        "description": "Regional Associations, observing assets, field staff, partner coordination, and local product maintenance.",
    },
    {
        "name": "Observing infrastructure",
        "description": "Buoys, shore stations, HF radar, gliders, sensors, telecommunications, calibration, repair, and replacement cycles.",
    },
    {
        "name": "Data management",
        "description": "Quality control, metadata, cyber hygiene, archives, APIs, interoperability, and user-facing data portals.",
    },
    {
        "name": "Forecast and decision products",
        "description": "Models, dashboards, maps, alerts, web tools, and partner workflows that translate observations into operational decisions.",
    },
]

CASE_STUDY_THEMES = [
    {
        "name": "PORTS and port efficiency",
        "keywords": ["ports", "tampa", "houston", "columbia", "grounding", "draft"],
    },
    {
        "name": "HF radar and search and rescue",
        "keywords": ["hf radar", "hfr", "search", "rescue", "sarops"],
    },
    {
        "name": "HAB forecasts and seafood decisions",
        "keywords": ["hab", "harmful algal", "shellfish", "seafood"],
    },
    {
        "name": "Regional data user value",
        "keywords": ["prototype user valuation", "regional association", "data services", "user value"],
    },
    {
        "name": "Ocean Enterprise and marine economy context",
        "keywords": ["ocean enterprise", "marine economy", "jobs", "revenue"],
    },
    {
        "name": "Coastal hazards and resilience",
        "keywords": ["coastal", "hazard", "resilience", "digital coast", "flood"],
    },
]

DECISION_USE_CATEGORY_KEYWORDS = {
    "Ports": [
        "ports",
        "port efficiency",
        "maritime transportation",
        "navigation",
        "vessel",
        "commercial marine transportation",
    ],
    "SAR": ["search and rescue", "sarops", "hf radar", "hfr", "surface current"],
    "HABs": ["hab", "harmful algal", "algal bloom", "sea nettle", "vibrio"],
    "Flooding": ["flood", "storm surge", "water level sensor", "coastal flood"],
    "Offshore wind": ["offshore wind", "wind farm", "blade inspection", "lease"],
    "Fisheries": ["fisher", "fisheries", "seafood", "shellfish", "aquaculture", "scallop", "crab"],
    "Coastal hazards": ["coastal hazard", "resilience", "rip current", "beach safety", "storm", "erosion"],
}

DECISION_USE_TEXT_COLUMNS = [
    "impact_domain",
    "ioos_component",
    "user_group",
    "decision_supported",
    "economic_pathway",
    "metric",
    "claim_allowed",
]

BENEFIT_STUDY_SOURCE_TYPES = [
    "case study",
    "valuation study",
    "modeled national scenario",
    "regional benefits study",
    "peer-reviewed regional benefits study",
    "peer-reviewed article",
]

BENEFIT_STUDY_EXCLUDED_SOURCE_TYPES = [
    "survey",
    "technical paper",
    "project report",
    "official annual report",
    "official report to congress",
    "official economic report",
]

BENEFIT_STUDY_TEXT_COLUMNS = [
    "source_id",
    "source_name",
    "source_type",
    "briefing_role",
    "impact_domains",
    "key_metrics",
    "evidence_profile",
    "recommended_claim_language",
    "caveats",
]


st.set_page_config(
    page_title="IOOS Economic Impact Hub",
    page_icon=":bar_chart:",
    layout="wide",
)


def apply_hub_styles() -> None:
    """Apply the internal data-product visual language."""
    hero_uri = asset_data_uri(IOOS_HERO_IMAGE_PATH, "image/png")
    st.markdown(
        f"""
        <style>
            :root {{
                --ioos-ink: #10212b;
                --ioos-muted: #5e6f79;
                --ioos-line: #dbe7ea;
                --ioos-panel: #f7fbfc;
                --ioos-paper: #ffffff;
                --ioos-soft: #eef6f7;
                --ioos-blue: #0a5d8f;
                --ioos-green: #1f7a68;
                --ioos-gold: #c4892c;
                --ioos-red: #b84d3f;
                --ioos-violet: #6c5b8f;
                --ioos-shadow: 0 12px 30px rgba(15, 47, 58, 0.08);
            }}

            .stApp {{
                background: #fbfdfd;
                color: var(--ioos-ink);
            }}

            .block-container {{
                padding-top: 1rem;
                padding-bottom: 3rem;
                max-width: 1440px;
            }}

            h1, h2, h3, p, label, span, div {{
                letter-spacing: 0;
            }}

            .hub-kicker {{
                color: var(--ioos-green);
                font-size: 0.78rem;
                font-weight: 700;
                text-transform: uppercase;
                margin-bottom: 0.3rem;
            }}

            .hub-page-title {{
                border-bottom: 1px solid var(--ioos-line);
                margin: 0.4rem 0 1.1rem;
                padding-bottom: 0.9rem;
            }}

            .hub-page-title h1 {{
                color: var(--ioos-ink);
                font-size: clamp(1.9rem, 2.6vw, 3.1rem);
                line-height: 1.05;
                margin: 0;
            }}

            .hub-page-title p {{
                color: var(--ioos-muted);
                font-size: 1rem;
                line-height: 1.62;
                margin: 0.45rem 0 0;
                max-width: 880px;
            }}

            .hub-hero {{
                background:
                    linear-gradient(90deg, rgba(9, 33, 45, 0.88), rgba(9, 33, 45, 0.52), rgba(9, 33, 45, 0.12)),
                    url("{hero_uri}");
                background-position: center;
                background-size: cover;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 8px;
                color: #ffffff;
                min-height: 330px;
                padding: clamp(1.4rem, 4vw, 3.4rem);
                display: flex;
                flex-direction: column;
                justify-content: flex-end;
                margin-bottom: 1.1rem;
            }}

            .hub-hero.hub-about-hero {{
                min-height: 470px;
                margin-bottom: 1rem;
            }}

            .hub-hero h1 {{
                color: #ffffff;
                font-size: clamp(2.1rem, 4vw, 4.5rem);
                line-height: 1.02;
                margin: 0;
                max-width: 780px;
            }}

            .hub-hero p {{
                color: #e8f6fa;
                font-size: clamp(1rem, 1.45vw, 1.22rem);
                max-width: 760px;
                margin: 0.8rem 0 0;
            }}

            .hub-strip {{
                background: var(--ioos-panel);
                border: 1px solid var(--ioos-line);
                border-radius: 8px;
                padding: 0.9rem 1rem;
                margin: 0.8rem 0 1.1rem;
            }}

            .hub-band {{
                background: var(--ioos-soft);
                border-bottom: 1px solid var(--ioos-line);
                border-top: 1px solid var(--ioos-line);
                margin: 1.3rem calc(50% - 50vw);
                padding: 1.2rem calc(50vw - 50%);
            }}

            .hub-strip strong {{
                color: var(--ioos-ink);
            }}

            .hub-utility {{
                align-items: center;
                background: #ffffff;
                border: 1px solid var(--ioos-line);
                border-radius: 8px;
                display: flex;
                gap: 0.8rem;
                justify-content: space-between;
                margin: 0.15rem 0 0.85rem;
                padding: 0.58rem 0.72rem;
            }}

            .hub-utility-brand {{
                color: var(--ioos-ink);
                font-size: 0.94rem;
                font-weight: 820;
            }}

            .hub-utility-user {{
                color: var(--ioos-muted);
                font-size: 0.84rem;
            }}

            .hub-chip {{
                background: #e8f5f1;
                border: 1px solid #b9ddd3;
                border-radius: 999px;
                color: #145d50;
                display: inline-block;
                font-size: 0.78rem;
                font-weight: 700;
                padding: 0.24rem 0.6rem;
            }}

            .hub-chip.neutral {{
                background: #eef4f6;
                border-color: #cbdce2;
                color: #3f5660;
            }}

            .hub-chip.warning {{
                background: #fff6df;
                border-color: #f0cf91;
                color: #76510c;
            }}

            .hub-chip.danger {{
                background: #fff0ec;
                border-color: #efb4a9;
                color: #8f3528;
            }}

            .hub-callout {{
                border-left: 4px solid var(--ioos-green);
                background: #f6fbf8;
                padding: 0.85rem 1rem;
                margin: 0.6rem 0 1rem;
            }}

            .hub-lede {{
                color: var(--ioos-muted);
                font-size: 1.08rem;
                line-height: 1.72;
                margin-bottom: 1rem;
            }}

            .hub-section {{
                margin-top: 2.1rem;
                margin-bottom: 1.2rem;
            }}

            .overview-intro {{
                color: var(--ioos-muted);
                font-size: 1.02rem;
                line-height: 1.65;
                margin: 0 0 1rem;
                max-width: 940px;
            }}

            .overview-card,
            .region-card,
            .region-detail-card,
            .sector-card,
            .cost-card,
            .case-card,
            .method-card,
            .atlas-level-card,
            .atlas-method-card {{
                background: var(--ioos-paper);
                border: 1px solid var(--ioos-line);
                border-radius: 8px;
                padding: 1rem;
            }}

            .overview-card b,
            .region-card b,
            .region-detail-card b,
            .sector-card b,
            .cost-card b,
            .case-card b,
            .method-card b,
            .atlas-level-card b,
            .atlas-method-card b {{
                color: var(--ioos-ink);
                display: block;
                font-size: 0.98rem;
                line-height: 1.28;
                margin-bottom: 0.35rem;
            }}

            .overview-card p,
            .region-card p,
            .region-detail-card p,
            .sector-card p,
            .cost-card p,
            .case-card p,
            .method-card p,
            .atlas-level-card p,
            .atlas-method-card p {{
                color: var(--ioos-muted);
                font-size: 0.86rem;
                line-height: 1.52;
                margin: 0.38rem 0 0;
            }}

            .overview-grid,
            .region-grid,
            .region-metric-grid,
            .sector-grid,
            .cost-grid,
            .case-grid,
            .method-grid,
            .atlas-level-grid,
            .atlas-method-grid {{
                display: grid;
                gap: 0.85rem;
            }}

            .overview-grid,
            .region-metric-grid,
            .atlas-level-grid {{
                grid-template-columns: repeat(4, minmax(150px, 1fr));
            }}

            .region-grid {{
                grid-template-columns: repeat(3, minmax(250px, 1fr));
            }}

            .sector-grid,
            .cost-grid,
            .atlas-method-grid {{
                grid-template-columns: repeat(2, minmax(240px, 1fr));
            }}

            .case-grid {{
                grid-template-columns: repeat(3, minmax(250px, 1fr));
            }}

            .method-grid {{
                grid-template-columns: repeat(3, minmax(220px, 1fr));
            }}

            .overview-stat {{
                color: var(--ioos-blue);
                display: block;
                font-size: 1.55rem;
                font-weight: 860;
                line-height: 1.05;
                margin-top: 0.45rem;
            }}

            .region-card {{
                min-height: 250px;
            }}

            .region-card-header {{
                align-items: flex-start;
                display: flex;
                gap: 0.75rem;
                justify-content: space-between;
                margin-bottom: 0.6rem;
            }}

            .region-name {{
                color: var(--ioos-ink);
                display: block;
                font-size: 1.02rem;
                font-weight: 820;
                line-height: 1.25;
                margin-top: 0.3rem;
            }}

            .region-code {{
                color: var(--ioos-muted);
                display: block;
                font-size: 0.78rem;
                font-weight: 760;
                text-transform: uppercase;
            }}

            .region-stats {{
                border-top: 1px solid var(--ioos-line);
                display: grid;
                gap: 0.55rem;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                margin-top: 0.8rem;
                padding-top: 0.8rem;
            }}

            .region-stat span {{
                color: var(--ioos-blue);
                display: block;
                font-size: 1.18rem;
                font-weight: 840;
                line-height: 1.05;
            }}

            .region-stat small {{
                color: var(--ioos-muted);
                display: block;
                font-size: 0.72rem;
                line-height: 1.25;
                margin-top: 0.15rem;
                text-transform: uppercase;
            }}

            .region-detail-card {{
                margin: 0.7rem 0 1rem;
            }}

            .region-detail-card ul {{
                color: var(--ioos-muted);
                font-size: 0.86rem;
                line-height: 1.5;
                margin: 0.45rem 0 0;
                padding-left: 1.1rem;
            }}

            .atlas-count {{
                color: var(--ioos-blue);
                display: block;
                font-size: 1.72rem;
                font-weight: 860;
                line-height: 1.05;
                margin: 0.55rem 0 0.35rem;
            }}

            .atlas-rule {{
                border-top: 1px solid var(--ioos-line);
                color: #405760;
                font-size: 0.8rem;
                line-height: 1.45;
                margin-top: 0.75rem;
                padding-top: 0.7rem;
            }}

            .atlas-boundary-list {{
                margin: 0.3rem 0 0;
                padding-left: 1.1rem;
            }}

            .atlas-boundary-list li {{
                color: var(--ioos-muted);
                font-size: 0.88rem;
                line-height: 1.5;
                margin-bottom: 0.28rem;
            }}

            .overview-link {{
                color: var(--ioos-blue);
                display: inline-block;
                font-size: 0.82rem;
                font-weight: 760;
                margin-top: 0.55rem;
                text-decoration: none;
            }}

            .evidence-empty-state {{
                background: #fff9eb;
                border: 1px solid #efcf90;
                border-radius: 8px;
                color: #6d4f13;
                line-height: 1.55;
                padding: 1rem;
            }}

            .hub-process-step {{
                border: 1px solid var(--ioos-line);
                border-radius: 8px;
                padding: 0.85rem 0.95rem;
                min-height: 142px;
                background: #ffffff;
            }}

            .hub-process-step b {{
                color: var(--ioos-blue);
            }}

            .hub-top-nav {{
                background: #ffffff;
                border: 1px solid var(--ioos-line);
                border-radius: 8px;
                margin-bottom: 1.2rem;
                padding: 0.42rem 0.5rem 0.18rem;
            }}

            .hub-top-nav [role="radiogroup"] {{
                align-items: center;
                gap: 0.2rem;
            }}

            .hub-top-nav label {{
                border-radius: 0;
                border-bottom: 3px solid transparent;
                color: var(--ioos-muted);
                font-weight: 700;
                padding: 0.3rem 0.25rem 0.58rem;
            }}

            .hub-top-nav label:has(input:checked) {{
                border-bottom-color: var(--ioos-blue);
                color: var(--ioos-ink);
            }}

            .hub-top-nav div[data-testid="stButton"] button {{
                background: #ffffff !important;
                border: 1px solid var(--ioos-line) !important;
                color: var(--ioos-ink) !important;
                min-height: 2.25rem;
            }}

            .hub-top-nav div[data-testid="stButton"] button p {{
                color: var(--ioos-ink) !important;
                font-weight: 760;
            }}

            .hub-top-nav div[data-testid="stButton"] button:hover {{
                background: var(--ioos-soft) !important;
                border-color: var(--ioos-blue) !important;
            }}

            button[data-testid="stBaseButton-secondary"] {{
                background: #ffffff !important;
                border: 1px solid var(--ioos-line) !important;
                color: var(--ioos-ink) !important;
            }}

            button[data-testid="stBaseButton-secondary"] p {{
                color: var(--ioos-ink) !important;
                font-weight: 760;
            }}

            button[data-testid="stBaseButton-secondary"]:hover {{
                background: var(--ioos-soft) !important;
                border-color: var(--ioos-blue) !important;
                color: var(--ioos-ink) !important;
            }}

            button[data-testid="stBaseButton-secondary"]:hover p {{
                color: var(--ioos-ink) !important;
            }}

            div[data-testid="stTabs"] [role="tablist"] {{
                border-bottom: 1px solid var(--ioos-line);
                gap: 0.35rem;
                margin-bottom: 1rem;
            }}

            div[data-testid="stTabs"] [role="tab"] {{
                border-bottom: 3px solid transparent;
                color: var(--ioos-muted);
                font-weight: 780;
                padding: 0.45rem 0.55rem 0.62rem;
            }}

            div[data-testid="stTabs"] [role="tab"] p {{
                color: inherit;
                font-size: 0.92rem;
                font-weight: 780;
            }}

            div[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{
                border-bottom-color: var(--ioos-blue);
                color: var(--ioos-ink);
            }}

            div[data-testid="stCaptionContainer"],
            div[data-testid="stCaptionContainer"] p {{
                color: var(--ioos-muted) !important;
            }}

            div[data-testid="stTextArea"] label,
            div[data-testid="stNumberInput"] label,
            div[data-testid="stFileUploader"] label,
            div[data-testid="stSelectbox"] label,
            div[data-testid="stExpander"] summary,
            div[data-testid="stExpander"] summary p,
            div[data-testid="stExpander"] p,
            div[data-testid="stExpander"] li {{
                color: var(--ioos-ink) !important;
            }}

            div[data-testid="stTextArea"] textarea,
            div[data-testid="stTextInput"] input,
            div[data-testid="stNumberInput"] input {{
                background: #ffffff !important;
                border-color: var(--ioos-line) !important;
                color: var(--ioos-ink) !important;
                caret-color: var(--ioos-blue);
            }}

            div[data-testid="stTextArea"] textarea::placeholder,
            div[data-testid="stTextInput"] input::placeholder {{
                color: #6d8189 !important;
                opacity: 1;
            }}

            div[data-testid="stMetric"] {{
                background: #ffffff;
                border: 1px solid var(--ioos-line);
                border-radius: 8px;
                padding: 0.85rem 0.9rem;
            }}

            div[data-testid="stMetric"] [data-testid="stMetricLabel"] p,
            div[data-testid="stMetric"] [data-testid="stMetricLabel"],
            div[data-testid="stMetric"] [data-testid="stMetricValue"],
            div[data-testid="stMetric"] [data-testid="stMetricValue"] div {{
                color: var(--ioos-ink) !important;
            }}

            div[data-testid="stMetric"] [data-testid="stMetricLabel"] p {{
                color: var(--ioos-muted) !important;
                font-weight: 720;
            }}

            div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
                font-weight: 820;
            }}

            .evidence-signal-chart {{
                background: linear-gradient(135deg, #ffffff 0%, #f7fbfc 100%);
                border: 1px solid var(--ioos-line);
                border-radius: 8px;
                box-shadow: var(--ioos-shadow);
                margin: 1rem 0 1.25rem;
                padding: 1rem;
            }}

            .evidence-signal-header {{
                align-items: flex-end;
                border-bottom: 1px solid var(--ioos-line);
                display: flex;
                gap: 1rem;
                justify-content: space-between;
                padding-bottom: 0.85rem;
            }}

            .evidence-signal-header h2 {{
                color: var(--ioos-ink);
                font-size: 1.2rem;
                line-height: 1.2;
                margin: 0;
            }}

            .evidence-signal-header p {{
                color: var(--ioos-muted);
                font-size: 0.86rem;
                line-height: 1.45;
                margin: 0;
                max-width: 520px;
            }}

            .evidence-signal-grid {{
                display: grid;
                gap: 0.8rem;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                margin-top: 0.9rem;
            }}

            .evidence-signal-card {{
                background: rgba(255, 255, 255, 0.74);
                border-left: 4px solid var(--ioos-green);
                border-radius: 8px;
                min-height: 210px;
                padding: 0.9rem;
            }}

            .evidence-signal-card.signal-benefits {{
                border-left-color: var(--ioos-blue);
            }}

            .evidence-signal-card.signal-safety {{
                border-left-color: var(--ioos-gold);
            }}

            .evidence-signal-card.signal-market {{
                border-left-color: var(--ioos-violet);
            }}

            .evidence-signal-title {{
                color: var(--ioos-muted);
                font-size: 0.74rem;
                font-weight: 820;
                line-height: 1.2;
                margin-bottom: 0.42rem;
                text-transform: uppercase;
            }}

            .evidence-signal-value {{
                color: var(--ioos-ink);
                font-size: 1.48rem;
                font-weight: 820;
                line-height: 1.08;
                overflow-wrap: anywhere;
            }}

            .evidence-signal-unit {{
                color: var(--ioos-muted);
                font-size: 0.84rem;
                line-height: 1.36;
                margin-top: 0.25rem;
            }}

            .evidence-signal-note {{
                color: #405760;
                font-size: 0.82rem;
                line-height: 1.43;
                margin: 0.68rem 0 0;
            }}

            .evidence-signal-tags {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.35rem;
                margin-top: 0.7rem;
            }}

            .evidence-signal-tags span {{
                background: #eef6f7;
                border: 1px solid var(--ioos-line);
                border-radius: 999px;
                color: #405760;
                font-size: 0.72rem;
                font-weight: 760;
                line-height: 1;
                padding: 0.28rem 0.48rem;
            }}

            .evidence-signal-meter {{
                background: #e7eff2;
                border-radius: 999px;
                height: 0.52rem;
                margin-top: 0.78rem;
                overflow: hidden;
            }}

            .evidence-signal-meter span {{
                background: linear-gradient(90deg, var(--ioos-blue), var(--ioos-green));
                border-radius: inherit;
                display: block;
                height: 100%;
            }}

            header[data-testid="stHeader"],
            div[data-testid="stToolbar"],
            div[data-testid="stDecoration"],
            div[data-testid="stStatusWidget"],
            div[data-testid="stElementToolbar"],
            section[data-testid="stSidebar"],
            div[data-testid="stSidebarCollapsedControl"],
            button[kind="headerNoPadding"] {{
                display: none !important;
                height: 0 !important;
                visibility: hidden !important;
            }}

            [data-testid="stDataFrame"] {{
                border: 1px solid var(--ioos-line);
                border-radius: 8px;
            }}

            .design-token-grid,
            .trust-demo-grid,
            .source-grid,
            .brief-grid,
            .queue-grid {{
                display: grid;
                gap: 0.85rem;
            }}

            .design-token-grid {{
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            }}

            .trust-demo-grid {{
                grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            }}

            .source-grid {{
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            }}

            .brief-grid {{
                grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
            }}

            .queue-grid {{
                grid-template-columns: repeat(4, minmax(150px, 1fr));
            }}

            .token-card,
            .evidence-card,
            .detail-panel,
            .source-profile,
            .brief-preview,
            .review-card,
            .metric-panel,
            .rubric-row {{
                background: var(--ioos-paper);
                border: 1px solid var(--ioos-line);
                border-radius: 8px;
                box-shadow: var(--ioos-shadow);
            }}

            .token-card,
            .source-profile,
            .brief-preview,
            .review-card,
            .metric-panel,
            .rubric-row {{
                padding: 0.95rem;
            }}

            .token-swatch {{
                border-radius: 6px;
                height: 42px;
                margin-bottom: 0.6rem;
                border: 1px solid rgba(16, 33, 43, 0.1);
            }}

            .token-card b,
            .source-profile b,
            .review-card b,
            .metric-panel b {{
                color: var(--ioos-ink);
                display: block;
                font-size: 0.93rem;
                line-height: 1.25;
                margin-bottom: 0.25rem;
            }}

            .token-card span,
            .source-profile span,
            .review-card span,
            .metric-panel span {{
                color: var(--ioos-muted);
                font-size: 0.82rem;
                line-height: 1.42;
            }}

            .trust-cluster {{
                align-items: center;
                display: flex;
                flex-wrap: wrap;
                gap: 0.38rem;
                margin-top: 0.7rem;
            }}

            .trust-badge,
            .status-pill {{
                align-items: center;
                border-radius: 999px;
                display: inline-flex;
                font-size: 0.76rem;
                font-weight: 760;
                gap: 0.35rem;
                line-height: 1;
                min-height: 1.75rem;
                padding: 0.34rem 0.56rem;
                white-space: nowrap;
            }}

            .trust-badge::before,
            .status-pill::before {{
                border-radius: 999px;
                content: "";
                display: inline-block;
                height: 0.46rem;
                width: 0.46rem;
            }}

            .strength-strong {{
                background: #e8f5f1;
                border: 1px solid #99cbbc;
                color: #145d50;
            }}

            .strength-strong::before {{ background: #1f7a68; }}

            .strength-medium {{
                background: #eef6fb;
                border: 1px solid #9fc9de;
                color: #13577e;
            }}

            .strength-medium::before {{ background: #0a5d8f; }}

            .strength-modeled {{
                background: #f4f1fb;
                border: 1px solid #c7bde2;
                color: #5b4c83;
            }}

            .strength-modeled::before {{ background: #6c5b8f; }}

            .strength-contextual {{
                background: #f3f6f7;
                border: 1px solid #cbdce2;
                color: #445e68;
            }}

            .strength-contextual::before {{ background: #70858e; }}

            .strength-needs-verification,
            .status-needs-follow-up,
            .status-flagged,
            .status-staged {{
                background: #fff6df;
                border: 1px solid #f0cf91;
                color: #76510c;
            }}

            .strength-needs-verification::before,
            .status-needs-follow-up::before,
            .status-flagged::before,
            .status-staged::before {{
                background: #c4892c;
            }}

            .status-report-ready,
            .status-ready-for-external-use,
            .status-verified {{
                background: #e8f5f1;
                border: 1px solid #99cbbc;
                color: #145d50;
            }}

            .status-report-ready::before,
            .status-ready-for-external-use::before,
            .status-verified::before {{
                background: #1f7a68;
            }}

            .status-use-with-caution,
            .status-in-review {{
                background: #eef6fb;
                border: 1px solid #9fc9de;
                color: #13577e;
            }}

            .status-use-with-caution::before,
            .status-in-review::before {{
                background: #0a5d8f;
            }}

            .status-background-only,
            .status-draft {{
                background: #f3f6f7;
                border: 1px solid #cbdce2;
                color: #445e68;
            }}

            .status-background-only::before,
            .status-draft::before {{
                background: #70858e;
            }}

            .status-rejected {{
                background: #fff0ec;
                border: 1px solid #efb4a9;
                color: #8f3528;
            }}

            .status-rejected::before {{
                background: #b84d3f;
            }}

            .ioos-chain {{
                align-items: center;
                display: inline-flex;
                gap: 0.24rem;
                vertical-align: middle;
            }}

            .chain-step {{
                align-items: center;
                border: 1px solid #bfd3da;
                border-radius: 999px;
                color: #6d8189;
                display: inline-flex;
                font-size: 0.64rem;
                font-weight: 800;
                height: 1.35rem;
                justify-content: center;
                width: 1.35rem;
            }}

            .chain-step.active {{
                background: #0a5d8f;
                border-color: #0a5d8f;
                color: #ffffff;
            }}

            .chain-label {{
                color: var(--ioos-muted);
                font-size: 0.76rem;
                font-weight: 720;
                margin-left: 0.2rem;
            }}

            .value-chain-full {{
                display: grid;
                gap: 0.7rem;
                grid-template-columns: repeat(5, minmax(120px, 1fr));
                margin: 1rem 0;
            }}

            .value-chain-node {{
                background: #ffffff;
                border: 1px solid var(--ioos-line);
                border-radius: 8px;
                min-height: 118px;
                padding: 0.9rem;
                position: relative;
            }}

            .value-chain-node::after {{
                background: var(--ioos-blue);
                content: "";
                height: 2px;
                position: absolute;
                right: -0.72rem;
                top: 2rem;
                width: 0.72rem;
            }}

            .value-chain-node:last-child::after {{
                display: none;
            }}

            .value-chain-node b {{
                color: var(--ioos-ink);
                display: block;
                line-height: 1.24;
                margin-bottom: 0.35rem;
            }}

            .value-chain-node span {{
                color: var(--ioos-muted);
                font-size: 0.82rem;
                line-height: 1.42;
            }}

            .evidence-card {{
                margin-bottom: 0.8rem;
                padding: 1rem;
            }}

            .evidence-card .row-meta,
            .detail-panel .row-meta,
            .brief-preview .row-meta {{
                color: var(--ioos-muted);
                display: flex;
                flex-wrap: wrap;
                font-size: 0.78rem;
                gap: 0.5rem;
                margin-top: 0.45rem;
            }}

            .evidence-card h3 {{
                color: var(--ioos-ink);
                font-size: 1.02rem;
                line-height: 1.34;
                margin: 0.25rem 0 0;
            }}

            .evidence-card .metric-value {{
                color: var(--ioos-blue);
                font-size: 1.14rem;
                font-weight: 820;
                line-height: 1.28;
                margin-top: 0.5rem;
            }}

            .detail-panel {{
                padding: 1rem;
                position: sticky;
                top: 0.8rem;
            }}

            .detail-panel h2 {{
                font-size: 1.12rem;
                line-height: 1.25;
                margin: 0.35rem 0 0.45rem;
            }}

            .detail-section {{
                border-top: 1px solid var(--ioos-line);
                margin-top: 0.9rem;
                padding-top: 0.8rem;
            }}

            .detail-section b {{
                color: var(--ioos-ink);
                display: block;
                font-size: 0.78rem;
                margin-bottom: 0.25rem;
                text-transform: uppercase;
            }}

            .detail-section p {{
                color: #354c55;
                line-height: 1.55;
                margin: 0;
            }}

            .filter-row {{
                background: #ffffff;
                border: 1px solid var(--ioos-line);
                border-radius: 8px;
                margin-bottom: 1rem;
                padding: 0.8rem 0.95rem 0.15rem;
            }}

            .coverage-key {{
                align-items: center;
                display: flex;
                flex-wrap: wrap;
                gap: 0.45rem;
                margin: 0.4rem 0 0.8rem;
            }}

            .coverage-key span {{
                border: 1px solid var(--ioos-line);
                border-radius: 999px;
                color: var(--ioos-muted);
                font-size: 0.76rem;
                padding: 0.25rem 0.55rem;
            }}

            .coverage-matrix-wrap {{
                border: 1px solid var(--ioos-line);
                border-radius: 8px;
                overflow-x: auto;
            }}

            .coverage-matrix-table {{
                border-collapse: collapse;
                min-width: 840px;
                width: 100%;
            }}

            .coverage-matrix-table th,
            .coverage-matrix-table td {{
                border-bottom: 1px solid var(--ioos-line);
                border-right: 1px solid var(--ioos-line);
                font-size: 0.78rem;
                padding: 0.45rem 0.55rem;
                text-align: center;
            }}

            .coverage-matrix-table th {{
                background: #f6fbfc;
                color: var(--ioos-ink);
                font-weight: 820;
            }}

            .coverage-matrix-table th:first-child,
            .coverage-matrix-table td:first-child {{
                color: var(--ioos-ink);
                font-weight: 760;
                max-width: 260px;
                min-width: 220px;
                text-align: left;
            }}

            .review-lane-title {{
                border-bottom: 3px solid var(--ioos-blue);
                color: var(--ioos-ink);
                font-size: 0.86rem;
                font-weight: 820;
                margin-bottom: 0.55rem;
                padding-bottom: 0.35rem;
                text-transform: uppercase;
            }}

            .review-card {{
                box-shadow: none;
                margin-bottom: 0.65rem;
                min-height: 126px;
            }}

            .ai-label {{
                background: #f4f1fb;
                border: 1px solid #c7bde2;
                border-radius: 999px;
                color: #5b4c83;
                display: inline-block;
                font-size: 0.72rem;
                font-weight: 800;
                margin-bottom: 0.45rem;
                padding: 0.22rem 0.5rem;
            }}

            .comparison-grid {{
                display: grid;
                gap: 0.85rem;
                grid-template-columns: 1fr 1fr;
            }}

            .comparison-pane {{
                background: #ffffff;
                border: 1px solid var(--ioos-line);
                border-radius: 8px;
                min-height: 190px;
                padding: 1rem;
            }}

            .comparison-pane h3 {{
                font-size: 0.94rem;
                margin: 0 0 0.55rem;
            }}

            .claim-review-panel {{
                background: #ffffff;
                border: 1px solid var(--ioos-line);
                border-radius: 8px;
                box-shadow: var(--ioos-shadow);
                margin: 0.85rem 0 1rem;
                padding: 1rem;
            }}

            .claim-review-topline,
            .claim-review-main,
            .claim-review-meta {{
                display: grid;
                gap: 0.75rem;
            }}

            .claim-review-topline {{
                align-items: center;
                grid-template-columns: 1fr auto;
                margin-bottom: 0.75rem;
            }}

            .claim-review-main {{
                grid-template-columns: minmax(0, 1fr) minmax(250px, 0.36fr);
            }}

            .claim-review-panel h2 {{
                color: var(--ioos-ink);
                font-size: 1.25rem;
                line-height: 1.25;
                margin: 0;
            }}

            .claim-review-panel p {{
                color: #354c55;
                line-height: 1.48;
                margin: 0.45rem 0 0;
            }}

            .claim-review-meta {{
                grid-template-columns: repeat(3, minmax(0, 1fr));
                margin-top: 0.9rem;
            }}

            .claim-review-meta div,
            .source-review-box {{
                background: #f6fbfc;
                border: 1px solid #cfe1e8;
                border-radius: 8px;
                padding: 0.75rem;
            }}

            .claim-review-meta b,
            .source-review-box b {{
                color: var(--ioos-ink);
                display: block;
                font-size: 0.74rem;
                margin-bottom: 0.25rem;
                text-transform: uppercase;
            }}

            .source-review-link {{
                align-items: center;
                background: #0a5d8f;
                border-radius: 8px;
                color: #ffffff !important;
                display: inline-flex;
                font-weight: 820;
                justify-content: center;
                margin-top: 0.4rem;
                min-height: 2.55rem;
                padding: 0.55rem 0.85rem;
                text-decoration: none !important;
                width: 100%;
            }}

            .source-review-link:hover {{
                background: #084c75;
            }}

            .source-review-missing {{
                color: #8f3528;
                display: block;
                font-weight: 760;
                margin-top: 0.4rem;
            }}

            div[data-testid="stMarkdownContainer"]:has(.claim-review-actions-marker)
            + div[data-testid="stHorizontalBlock"] div[data-testid="column"]:nth-child(1) button {{
                background: #1f7a68;
                border-color: #1f7a68;
                color: #ffffff;
            }}

            div[data-testid="stMarkdownContainer"]:has(.claim-review-actions-marker)
            + div[data-testid="stHorizontalBlock"] div[data-testid="column"]:nth-child(2) button {{
                background: #b84d3f;
                border-color: #b84d3f;
                color: #ffffff;
            }}

            .brief-preview {{
                box-shadow: none;
                min-height: 440px;
            }}

            .brief-preview h2 {{
                color: var(--ioos-ink);
                font-size: 1.45rem;
                line-height: 1.15;
                margin: 0 0 0.75rem;
            }}

            .brief-number {{
                border-left: 4px solid var(--ioos-green);
                margin: 0.8rem 0;
                padding-left: 0.7rem;
            }}

            .brief-number b {{
                color: var(--ioos-blue);
                display: block;
                font-size: 1.35rem;
                line-height: 1.1;
            }}

            .brief-number span {{
                color: #405760;
                font-size: 0.86rem;
                line-height: 1.45;
            }}

            @media (max-width: 980px) {{
                .brief-grid,
                .comparison-grid,
                .value-chain-full,
                .queue-grid,
                .overview-grid,
                .region-grid,
                .region-metric-grid,
                .sector-grid,
                .cost-grid,
                .case-grid,
                .method-grid,
                .atlas-level-grid,
                .atlas-method-grid,
                .claim-review-main,
                .claim-review-meta {{
                    grid-template-columns: 1fr;
                }}

                .evidence-signal-header {{
                    align-items: flex-start;
                    flex-direction: column;
                }}

                .detail-panel {{
                    position: static;
                }}

                .value-chain-node::after {{
                    display: none;
                }}
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_hero() -> None:
    """Render the app hero above the primary navigation."""
    st.markdown(
        """
        <div class="hub-hero hub-about-hero">
            <div class="hub-kicker">Start here</div>
            <h1>IOOS Economic Impact Hub</h1>
            <p>A guided evidence app for explaining what IOOS is, who it serves, what it costs to maintain, and where the database already supports return-on-investment case studies.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_top_navigation() -> str:
    """Render the primary left-to-right app navigation."""
    current_page = st.session_state.get("primary_navigation", APP_NAVIGATION[0])
    if current_page not in APP_NAVIGATION:
        current_page = APP_NAVIGATION[0]
        st.session_state["primary_navigation"] = current_page

    st.markdown('<div class="hub-top-nav">', unsafe_allow_html=True)
    page = st.segmented_control(
        "Primary navigation",
        APP_NAVIGATION,
        default=current_page,
        label_visibility="collapsed",
        key="primary_navigation_picker",
    )
    if page is None:
        page = current_page
    st.session_state["primary_navigation"] = page
    st.markdown("</div>", unsafe_allow_html=True)
    return page


def render_workspace_header(page: str) -> None:
    role = st.session_state.get("employee_role", "Viewer")
    st.markdown(
        f"""
        <div class="hub-strip">
            <span class="hub-chip">{role}</span>
            <strong style="margin-left:0.45rem;">{page}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )


def count_value(df: pd.DataFrame, column: str, value: str) -> int:
    if df.empty or column not in df.columns:
        return 0
    return int((df[column].map(normalize_text).str.lower() == value.lower()).sum())


def active_phase_label() -> str:
    active_index = active_project_phase_index(date.today())
    if active_index is None:
        return "Complete" if date.today() > PROJECT_TIMELINE[-1]["end"] else "Not started"
    return PROJECT_TIMELINE[active_index]["milestone"]


def render_process_steps() -> None:
    columns = st.columns(len(METHOD_STEPS))
    for column, step in zip(columns, METHOD_STEPS):
        column.markdown(
            f"""
            <div class="hub-process-step">
                <b>{step["Step"]}</b>
                <p>{step["What happens"]}</p>
                <span class="hub-chip">{step["Owner"]}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE pairs without adding a runtime dependency."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def is_placeholder_secret(value: str) -> bool:
    lowered = value.lower()
    return not value or "replace" in lowered or "your-" in lowered


def get_nested_secret(section_path: tuple[str, ...], name: str) -> str:
    """Read a nested Streamlit secret without assuming a specific TOML shape."""
    try:
        current = st.secrets
        for section in section_path:
            current = current.get(section, {})
        value = current.get(name, "") if hasattr(current, "get") else ""
    except Exception:
        value = ""
    return str(value or "").strip()


def get_secret(name: str) -> str:
    """Read Supabase settings from Streamlit secrets or the local environment."""
    try:
        secret_value = st.secrets.get(name, "")
    except Exception:
        secret_value = ""
    return str(secret_value or os.environ.get(name, "")).strip()


def first_config_value(names: list[str]) -> str:
    """Find the first configured value across env, flat secrets, and nested secrets."""
    for name in names:
        value = get_secret(name)
        if value and not is_placeholder_secret(value):
            return value

    for section_path in SUPABASE_SECRET_SECTIONS:
        for name in names:
            value = get_nested_secret(section_path, name)
            if value and not is_placeholder_secret(value):
                return value

    return ""


def supabase_settings() -> tuple[str, str]:
    load_dotenv(REPO_ROOT / ".env")
    return first_config_value(SUPABASE_URL_NAMES), first_config_value(SUPABASE_KEY_NAMES)


def supabase_enabled() -> bool:
    url, service_key = supabase_settings()
    return bool(url and service_key)


def supabase_missing_settings() -> list[str]:
    url, service_key = supabase_settings()
    missing = []
    if not url:
        missing.append("Supabase URL")
    if not service_key:
        missing.append("Supabase API key")
    return missing


def supabase_request(
    method: str,
    table: str,
    query: dict[str, str] | None = None,
    body: object | None = None,
    prefer: str | None = None,
) -> object:
    """Call Supabase PostgREST using the service role key."""
    supabase_url, service_key = supabase_settings()
    if not supabase_url or not service_key:
        raise RuntimeError("Supabase settings are not configured.")

    query_string = f"?{urlencode(query)}" if query else ""
    url = f"{supabase_url.rstrip('/')}/rest/v1/{table}{query_string}"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "User-Agent": "IOOSStreamlitApp/1.0",
    }
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer

    request = Request(url, data=payload, headers=headers, method=method)
    try:
        with urlopen(request, timeout=60) as response:
            text = response.read().decode("utf-8")
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {table} failed with HTTP {exc.code}: {message}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method} {table} failed: {exc.reason}") from exc

    if not text:
        return []
    return json.loads(text)


def map_supabase_rows_for_app(table: str, rows: list[dict[str, object]]) -> pd.DataFrame:
    """Convert Supabase rows back to the app's CSV-facing column names."""
    if table == "staged_evidence":
        mapped = [
            {
                intake_column: str(row.get(db_column, "") or "")
                for db_column, intake_column in STAGED_DB_TO_INTAKE_COLUMNS.items()
            }
            for row in rows
        ]
        return pd.DataFrame(mapped, columns=INTAKE_SCHEMA)

    if table == "review_needed":
        mapped = []
        for row in rows:
            mapped.append(
                {
                    "severity": str(row.get("severity", "") or ""),
                    "row_id": str(row.get("row_id", "") or ""),
                    "source_id": str(row.get("source_id", "") or ""),
                    "check": str(row.get("check_name", row.get("check", "")) or ""),
                    "message": str(row.get("message", "") or ""),
                }
            )
        return pd.DataFrame(mapped, columns=["severity", "row_id", "source_id", "check", "message"])

    records = []
    for row in rows:
        records.append(
            {
                key: str(value or "")
                for key, value in row.items()
                if key not in {"id", "updated_at"}
            }
        )
    return pd.DataFrame(records)


def map_rows_for_supabase(table: str, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Convert app/CSV rows to Supabase table columns."""
    mapped_rows: list[dict[str, str]] = []
    for row in rows:
        if table == "staged_evidence":
            mapped_rows.append(
                {
                    db_column: normalize_text(row.get(intake_column))
                    for intake_column, db_column in INTAKE_TO_STAGED_DB_COLUMNS.items()
                }
            )
        elif table == "review_needed":
            mapped_rows.append(
                {
                    "severity": normalize_text(row.get("severity")),
                    "row_id": normalize_text(row.get("row_id")),
                    "source_id": normalize_text(row.get("source_id")),
                    "check_name": normalize_text(row.get("check", row.get("check_name"))),
                    "message": normalize_text(row.get("message")),
                }
            )
        else:
            mapped_rows.append({key: normalize_text(value) for key, value in row.items()})
    return mapped_rows


def load_supabase_table(table: str) -> pd.DataFrame:
    query = {"select": "*"}
    order_column = TABLE_ORDER_COLUMNS.get(table)
    if order_column:
        query["order"] = f"{order_column}.asc"
    rows = supabase_request("GET", table, query=query)
    return map_supabase_rows_for_app(table, rows if isinstance(rows, list) else [])


def replace_supabase_table(table: str, rows: list[dict[str, str]]) -> None:
    delete_column, delete_filter = TABLE_DELETE_FILTERS[table]
    supabase_request(
        "DELETE",
        table,
        query={delete_column: delete_filter},
        prefer="return=minimal",
    )
    append_supabase_rows(table, rows)


def append_supabase_rows(table: str, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    mapped_rows = map_rows_for_supabase(table, rows)
    conflict = TABLE_CONFLICT_KEYS.get(table)
    query = {"on_conflict": conflict} if conflict else None
    prefer = "resolution=merge-duplicates,return=minimal" if conflict else "return=minimal"
    supabase_request("POST", table, query=query, body=mapped_rows, prefer=prefer)


@st.cache_data(show_spinner=False)
def load_csv(path: Path) -> pd.DataFrame:
    """Load a CSV as strings so identifiers and matrix text are preserved."""
    table = PATH_TABLES.get(path)
    if table and supabase_enabled():
        try:
            return load_supabase_table(table)
        except RuntimeError:
            pass
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


@st.cache_data(show_spinner=False)
def load_optional_supabase_table(table_names: tuple[str, ...]) -> tuple[pd.DataFrame, str, tuple[str, ...]]:
    """Try a short list of optional Supabase tables without breaking the page."""
    if not supabase_enabled():
        return pd.DataFrame(), "", ()

    errors: list[str] = []
    for table in table_names:
        try:
            return load_supabase_table(table), table, tuple(errors)
        except RuntimeError as exc:
            errors.append(f"{table}: {exc}")

    return pd.DataFrame(), "", tuple(errors)


def clear_data_cache() -> None:
    """Refresh cached CSV reads after validation or row additions."""
    load_csv.clear()
    load_optional_supabase_table.clear()


def search_dataframe(df: pd.DataFrame, search_text: str) -> pd.DataFrame:
    """Return rows where any column contains the search text."""
    if df.empty or not search_text.strip():
        return df
    text = search_text.strip().lower()
    row_matches = df.astype(str).apply(
        lambda row: row.str.lower().str.contains(text, regex=False).any(),
        axis=1,
    )
    return df[row_matches]


def add_multiselect_filter(df: pd.DataFrame, column: str, label: str) -> pd.DataFrame:
    """Add an inline multiselect for a column when that column exists."""
    if column not in df.columns:
        return df
    options = sorted(value for value in df[column].dropna().unique() if str(value).strip())
    selected = st.multiselect(label, options, key=f"filter_{column}_{slugify_source_id(label, set())}")
    if selected:
        return df[df[column].isin(selected)]
    return df


def add_status_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Filter status/report-ready style fields when they are present."""
    status_columns = [
        column
        for column in df.columns
        if "status" in column.lower()
        or "report" in column.lower()
        or column == "source_verification_needed"
    ]
    for column in status_columns:
        df = add_multiselect_filter(df, column, column.replace("_", " ").title())
    return df


def link_column_config(df: pd.DataFrame) -> dict[str, object]:
    """Make URL columns clickable in displayed tables."""
    return {
        column: st.column_config.LinkColumn(column.replace("_", " ").title())
        for column in df.columns
        if column.endswith("_url") or column == "source_url"
    }


def render_filtered_table(
    df: pd.DataFrame,
    key_prefix: str,
    preferred_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Render search, filters, table, and CSV download for a dataframe."""
    search_text = st.text_input("Search", key=f"{key_prefix}_search")
    filtered = search_dataframe(df, search_text)

    filtered = add_multiselect_filter(filtered, "impact_domain", "Impact Domain")
    filtered = add_multiselect_filter(filtered, "ioos_region_code", "IOOS Region Code")
    filtered = add_multiselect_filter(filtered, "evidence_strength", "Evidence Strength")
    filtered = add_multiselect_filter(
        filtered,
        "ioos_attribution_strength",
        "IOOS Attribution Strength",
    )
    filtered = add_multiselect_filter(filtered, "update_frequency", "Update Frequency")
    filtered = add_status_filters(filtered)

    st.caption(f"Showing {len(filtered):,} of {len(df):,} rows")
    display_df = filtered
    if preferred_columns:
        columns = [column for column in preferred_columns if column in filtered.columns]
        if columns:
            display_df = filtered[columns]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config=link_column_config(display_df),
    )
    st.download_button(
        "Download filtered CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        file_name=f"{key_prefix}_filtered.csv",
        mime="text/csv",
    )
    sort_columns = [column for column in ["impact_domain", "row_id"] if column in filtered.columns]
    if sort_columns:
        return filtered.sort_values(sort_columns, kind="stable")
    return filtered


def intake_schema_csv_header() -> str:
    return ",".join(INTAKE_SCHEMA)


def allowed_ratings_text() -> str:
    return ", ".join(ALLOWED_RATING_VALUES)


def allowed_economic_number_types_text() -> str:
    return ", ".join(ECONOMIC_NUMBER_TYPE_VALUES)


def allowed_ioos_role_types_text() -> str:
    return ", ".join(IOOS_ROLE_TYPE_VALUES)


def allowed_ioos_region_codes_text() -> str:
    return ", ".join(sorted(ALLOWED_IOOS_REGION_CODES))


def record_created_prompt_rule() -> str:
    return (
        "Set Date record created to the date you create the CSV in YYYY-MM-DD format; "
        f"use {date.today().isoformat()} if creating it today."
    )


def split_ioos_region_codes(value: object) -> list[str]:
    return [part.strip() for part in normalize_text(value).split(";") if part.strip()]


def invalid_ioos_region_codes(value: object) -> list[str]:
    return [code for code in split_ioos_region_codes(value) if code not in ALLOWED_IOOS_REGION_CODES]


def has_dollar_signal(text: str) -> bool:
    return bool(re.search(r"\$|\b(?:dollars?|USD|costs?|benefits?|savings?|revenue|GDP|sales)\b", text, re.I))


def has_numeric_signal(text: str) -> bool:
    return bool(re.search(r"\d|%|percent|million|billion", text, re.I))


def infer_economic_number_type(row: pd.Series | dict[str, object]) -> str:
    metric = normalize_text(row.get("Metric", row.get("metric", "")))
    claim = normalize_text(row.get("Claim allowed", row.get("claim_allowed", "")))
    limitations = normalize_text(row.get("Limitations", row.get("limitations", "")))
    evidence = normalize_text(row.get("Evidence strength", row.get("evidence_strength", "")))
    combined = f"{metric} {claim} {limitations}"

    if re.search(r"\bdo not use\b|unsupported|invalid", combined, re.I):
        return "Do not use"
    if has_dollar_signal(metric):
        if re.search(r"\b(exposure|context|baseline|sector|GDP|jobs|employment|sales|revenue|cargo|tons?)\b", combined, re.I):
            return "Dollar exposure/context"
        if evidence == "Modeled" or re.search(r"\b(modeled|scenario|potential|estimate|estimated|counterfactual|benefit transfer|prospective)\b", combined, re.I):
            return "Modeled dollar estimate"
        return "Observed dollar benefit"
    if has_numeric_signal(metric):
        return "Operational metric only"
    if re.search(r"\bqualitative|not quantified|no dollar|not monetized\b", combined, re.I):
        return "Operational metric only"
    return "No economic number"


def infer_ioos_role_type(row: pd.Series | dict[str, object]) -> str:
    attribution = normalize_text(row.get("IOOS attribution strength", row.get("ioos_attribution_strength", "")))
    metric = normalize_text(row.get("Metric", row.get("metric", "")))
    component = normalize_text(row.get("IOOS component", row.get("ioos_component", "")))
    decision = normalize_text(row.get("Decision supported", row.get("decision_supported", "")))
    pathway = normalize_text(row.get("Economic pathway", row.get("economic_pathway", "")))
    claim = normalize_text(row.get("Claim allowed", row.get("claim_allowed", "")))
    limitations = normalize_text(row.get("Limitations", row.get("limitations", "")))
    combined = f"{component} {decision} {pathway} {metric} {claim} {limitations}"

    if attribution in {"", "Needs verification"}:
        return "Partner/infrastructure source"
    if attribution == "Contextual":
        return "Context only"
    if re.search(r"\b(no IOOS|not IOOS|not IOOS-specific|not an IOOS|no direct IOOS)\b", limitations, re.I):
        return "No IOOS attribution"
    if re.search(r"\b(backend|data source|data service|portal|ERDDAP|harvested|delivered|assimilated|feeds?|input|surface current|HF radar|Doppio|SAROPS)\b", combined, re.I):
        return "Backend data source"
    if infer_economic_number_type(row) in {"Observed dollar benefit", "Modeled dollar estimate"} and attribution == "Strong":
        return "Direct impact source"
    if decision:
        return "Direct decision-support source"
    return "Partner/infrastructure source"


def default_allowed_use(row: pd.Series | dict[str, object]) -> str:
    economic_type = normalize_text(row.get("Economic number type", row.get("economic_number_type", ""))) or infer_economic_number_type(row)
    ioos_role = normalize_text(row.get("IOOS role type", row.get("ioos_role_type", ""))) or infer_ioos_role_type(row)
    if economic_type == "Observed dollar benefit":
        return "Can support a dollar benefit claim after source verification and caveats."
    if economic_type == "Modeled dollar estimate":
        return "Can support a modeled or potential dollar claim with model language."
    if economic_type == "Dollar exposure/context":
        return "Can describe the size of an affected sector or asset base; use as context only."
    if economic_type == "Operational metric only":
        return "Can support an operational value claim, not a dollar return claim."
    if ioos_role == "Backend data source":
        return "Can document the IOOS data pathway behind a user decision or partner tool."
    if economic_type == "Do not use":
        return "Do not use in external materials until corrected and reviewed."
    return "Can document capability, context, or source leads for follow-up."


def default_not_allowed_use(row: pd.Series | dict[str, object]) -> str:
    economic_type = normalize_text(row.get("Economic number type", row.get("economic_number_type", ""))) or infer_economic_number_type(row)
    ioos_role = normalize_text(row.get("IOOS role type", row.get("ioos_role_type", ""))) or infer_ioos_role_type(row)
    if economic_type == "Dollar exposure/context":
        return "Do not present the dollar figure as an IOOS-caused benefit or ROI."
    if economic_type == "Operational metric only":
        return "Do not convert the operational metric into dollars without a separate valuation method."
    if ioos_role == "Backend data source":
        return "Do not claim direct economic return from IOOS data alone."
    if economic_type == "Modeled dollar estimate":
        return "Do not present modeled or potential values as observed realized benefits."
    if economic_type == "No economic number":
        return "Do not use as evidence of economic return."
    if economic_type == "Do not use":
        return "Do not cite until reviewed."
    return "Do not overstate attribution beyond what the source directly supports."


def research_prompt(topic: str) -> str:
    topic_text = topic.strip() or "[INSERT TOPIC]"
    return f"""You are generating candidate evidence rows for the IOOS Economic Evidence App.

Produce an actual .csv file as the output, not just comma-separated value text pasted into the chat. The .csv file must include this exact header row as the first line:

{intake_schema_csv_header()}

Task:
Research the following IOOS economic impact topic:
{topic_text}

Rules:
- Use only real sources.
- Do not invent numbers, metrics, source titles, or URLs.
- IOOS region code must be one or more exact codes separated by semicolons: {allowed_ioos_region_codes_text()}.
- Use National for national-scale evidence and Multiple for evidence that spans several known regional associations.
- If the evidence is qualitative, say so in the Metric field.
- Evidence strength and IOOS attribution strength must be exactly one of: {allowed_ratings_text()}.
- Economic number type must be exactly one of: {allowed_economic_number_types_text()}.
- IOOS role type must be exactly one of: {allowed_ioos_role_types_text()}.
- {record_created_prompt_rule()}
- Put rating explanations in Limitations or AI extraction notes, not in the rating fields.
- If the source supports economic context but not IOOS-attributable benefit, set IOOS attribution strength to Contextual.
- If the claim is modeled, set Evidence strength to Modeled.
- Use Economic number type = Dollar exposure/context when dollars describe sector size, GDP, jobs, cargo value, asset value, or market exposure rather than IOOS benefit.
- Use Economic number type = Operational metric only when the source documents performance, use, search-area reduction, forecast cadence, or decisions but no dollar return.
- Use IOOS role type = Backend data source when IOOS data feeds, supports, or is assimilated into another tool or partner decision process but the source does not support an IOOS return estimate.
- In Allowed use and Not allowed use, explain exactly what the row can and cannot support in a report.
- If the source has not been manually checked, set Source verification needed to Yes.
- Use conservative claim language in Claim allowed.
- Quote every CSV field that contains a comma, quote, or line break.
- Include limitations for every row.
- Return the .csv file only; do not include Markdown, commentary, or a pasted CSV transcript outside the file."""


def source_prompt(source_text: str) -> str:
    source_body = source_text.strip() or "[PASTE SOURCE URL, TITLE, TEXT, ABSTRACT, OR REPORT EXCERPT]"
    return f"""You are extracting candidate rows for the IOOS Economic Evidence App.

Source:
{source_body}

Produce an actual .csv file as the output, not just comma-separated value text pasted into the chat. The .csv file must include this exact header row as the first line:

{intake_schema_csv_header()}

Rules:
- Extract only evidence actually supported by the source.
- Do not create a row if the source is too vague.
- Do not overstate IOOS attribution.
- IOOS region code must be one or more exact codes separated by semicolons: {allowed_ioos_region_codes_text()}.
- Use National for national-scale evidence and Multiple for evidence that spans several known regional associations.
- Evidence strength and IOOS attribution strength must be exactly one of: {allowed_ratings_text()}.
- Economic number type must be exactly one of: {allowed_economic_number_types_text()}.
- IOOS role type must be exactly one of: {allowed_ioos_role_types_text()}.
- {record_created_prompt_rule()}
- Put rating explanations in Limitations or AI extraction notes, not in the rating fields.
- If the source is not IOOS-specific, mark IOOS attribution strength as Contextual.
- If the source provides economic exposure but not avoided cost or benefit, say that in Limitations.
- Use Economic number type = Dollar exposure/context for sector size or affected economic activity that should not be framed as IOOS ROI.
- Use Economic number type = Operational metric only for performance/use metrics such as search-area reduction, forecast skill, request volume, or delivery cadence.
- Use IOOS role type = Backend data source when IOOS data is a supporting data feed rather than the monetized object of analysis.
- In Allowed use and Not allowed use, explicitly state whether the row can support a dollar claim, an operational value claim, an attribution chain, or context only.
- Set Source verification needed to Yes unless the row has been manually checked.
- Write Claim allowed as a cautious sentence that COL could safely use.
- Quote every CSV field that contains a comma, quote, or line break.
- Return the .csv file only; do not include Markdown, commentary, or a pasted CSV transcript outside the file."""


def claude_batch_prompt(source_links: str, research_focus: str) -> str:
    links = [line.strip() for line in source_links.splitlines() if line.strip()]
    if links:
        link_text = "\n".join(f"{index}. {link}" for index, link in enumerate(links, start=1))
    else:
        link_text = "[PASTE PAPER OR REPORT LINKS HERE, ONE PER LINE]"

    focus_text = research_focus.strip() or (
        "Extract IOOS economic impact evidence, including observed or modeled benefits, "
        "avoided costs, operational decisions supported, user groups, caveats, and update cadence."
    )

    return f"""You are Claude acting as a research coworker for the IOOS Economic Evidence App.

Goal:
Read the linked papers, reports, or source pages below and extract candidate evidence rows that could support cautious IOOS economic impact claims.

Research focus:
{focus_text}

Links:
{link_text}

Produce an actual .csv file as the output, not just comma-separated value text pasted into the chat. The .csv file must include this exact header row as the first line:

{intake_schema_csv_header()}

Rules:
- Use only evidence that is actually supported by the linked source.
- Do not invent numbers, metrics, dollar years, titles, source URLs, agencies, or IOOS attribution.
- If a link is inaccessible or too vague, do not create a row from it.
- Leave row_id blank unless the source itself provides a stable row identifier.
- Source must be the paper/report/source title.
- Source URL must be the exact link used for the row.
- IOOS region code must be one or more exact codes separated by semicolons: {allowed_ioos_region_codes_text()}.
- Use National for national-scale evidence and Multiple for evidence that spans several known regional associations.
- Evidence strength and IOOS attribution strength must be exactly one of: {allowed_ratings_text()}.
- Economic number type must be exactly one of: {allowed_economic_number_types_text()}.
- IOOS role type must be exactly one of: {allowed_ioos_role_types_text()}.
- {record_created_prompt_rule()}
- Set Source verification needed to Yes for every row.
- Put rating explanations, uncertainty, page/table references, and access problems in Limitations or AI extraction notes, not in the rating fields.
- If the source supports economic context but not IOOS-attributable benefit, set IOOS attribution strength to Contextual.
- If the claim is based on a model, scenario, benefit-transfer method, or estimate rather than observed outcomes, set Evidence strength to Modeled unless the source clearly justifies a stronger rating.
- If the source provides exposure, activity, or use statistics but not avoided cost or benefit, say that in Limitations.
- Set Economic number type to Observed dollar benefit only when the source directly supports realized dollar benefits, avoided costs, savings, or revenue effects.
- Set Economic number type to Modeled dollar estimate for scenario, benefit-transfer, forecast-value, potential, or modeled dollar estimates.
- Set Economic number type to Dollar exposure/context when the source sizes an affected sector but does not estimate IOOS benefits.
- Set Economic number type to Operational metric only when the source has a quantitative operational metric but no dollar estimate.
- Set IOOS role type to Backend data source when IOOS data is a data feed, model input, portal service, or infrastructure component behind another decision tool.
- Fill Allowed use and Not allowed use with report-writing guardrails, especially whether the row can support a hard-dollar claim or only an attribution/context claim.
- Write Claim allowed as a cautious sentence that COL could safely use.
- Include limitations for every row.
- Quote every CSV field that contains a comma, quote, or line break.
- Every row must include Source, Source URL, IOOS region code, Claim allowed, Limitations, Evidence strength, and IOOS attribution strength.
- Before returning, check that every row has exactly the same number of columns as the header.
- Return the .csv file only; do not include Markdown, commentary, or a pasted CSV transcript outside the file."""


def regional_target_label(row: pd.Series) -> str:
    association = normalize_text(row.get("ioos_association"))
    region = normalize_text(row.get("region_name"))
    if association and region:
        return f"{association} - {region}"
    return association or region or "Regional target"


def selected_regional_target(regional_targets_df: pd.DataFrame, key: str) -> pd.Series | None:
    if regional_targets_df.empty:
        return None

    labels = {
        regional_target_label(row): index
        for index, row in regional_targets_df.iterrows()
    }
    selected = st.selectbox("Regional focus", list(labels), key=key)
    return regional_targets_df.loc[labels[selected]]


def evidence_rows_for_regional_target(evidence_df: pd.DataFrame, target: pd.Series | None) -> pd.DataFrame:
    if target is None or evidence_df.empty:
        return pd.DataFrame()

    target_code = normalize_text(target.get("ioos_region_code")) or normalize_text(target.get("ioos_association"))
    code_mask = pd.Series(False, index=evidence_df.index)
    if target_code and "ioos_region_code" in evidence_df.columns:
        code_mask = evidence_df["ioos_region_code"].apply(
            lambda value: target_code in split_ioos_region_codes(value)
        )

    keywords = [
        value.strip().lower()
        for value in normalize_text(target.get("region_keywords")).split(";")
        if value.strip()
    ]
    for fallback in [target.get("ioos_association"), target.get("region_name")]:
        value = normalize_text(fallback).lower()
        if value and value not in keywords:
            keywords.append(value)

    if not keywords:
        return evidence_df[code_mask].copy()

    text_columns = [column for column in ["region", "ioos_component", "impact_domain"] if column in evidence_df.columns]
    text_mask = pd.Series(False, index=evidence_df.index)
    for column in text_columns:
        column_text = evidence_df[column].map(lambda value: normalize_text(value).lower())
        text_mask = text_mask | column_text.apply(lambda value: any(keyword in value for keyword in keywords))
    return evidence_df[code_mask | text_mask].copy()


def association_regional_targets(regional_targets_df: pd.DataFrame) -> pd.DataFrame:
    """Return the 11 IOOS Regional Association targets in official code order."""
    target_columns = [
        "region_id",
        "region_name",
        "ioos_association",
        "ioos_region_code",
        "phase",
        "status",
        "region_keywords",
        "priority_domains",
        "starter_research_question",
        "source_targets",
        "evidence_gap",
        "prompt_notes",
    ]
    if regional_targets_df.empty or "ioos_region_code" not in regional_targets_df.columns:
        targets = pd.DataFrame(
            [
                {
                    "region_id": code.lower(),
                    "region_name": name,
                    "ioos_association": code,
                    "ioos_region_code": code,
                    "phase": "Regional pilot" if code == MARACOOS_CODE else "Regional build queue",
                    "status": "active" if code == MARACOOS_CODE else "planned",
                    "region_keywords": f"{code}; {name}",
                    "priority_domains": "Priority domains pending",
                    "starter_research_question": (
                        f"What source-backed evidence shows how {code} data, products, "
                        f"or observing assets support decisions with economic relevance in {name}?"
                    ),
                    "source_targets": "Regional association materials; NOAA; state agencies; ports; peer-reviewed studies; economic baseline data",
                    "evidence_gap": f"Need regional rows that distinguish direct {code} attribution from broader ocean economy exposure.",
                    "prompt_notes": "Start with decision-use evidence and conservative claims.",
                }
                for code, name in IOOS_REGION_OPTIONS.items()
            ]
        )
    else:
        targets = regional_targets_df.copy()
        for column in target_columns:
            if column not in targets.columns:
                targets[column] = ""

    official_order = {code: index for index, code in enumerate(IOOS_REGION_OPTIONS)}
    targets["_region_order"] = targets["ioos_region_code"].map(lambda value: official_order.get(normalize_text(value), 999))
    targets = targets[targets["_region_order"] < 999].copy()
    targets = targets.sort_values(["_region_order", "ioos_region_code"], kind="stable")
    return targets[target_columns].reset_index(drop=True)


def region_code_mask(df: pd.DataFrame, code: str, column: str = "ioos_region_code") -> pd.Series:
    if df.empty or column not in df.columns or not normalize_text(code):
        return pd.Series(False, index=df.index, dtype=bool)
    code_key = normalize_text(code).lower()
    return df[column].apply(
        lambda value: code_key in {part.lower() for part in split_ioos_region_codes(value)}
    )


def rows_for_region_code(df: pd.DataFrame, code: str, column: str = "ioos_region_code") -> pd.DataFrame:
    if df.empty:
        return df.copy()
    return df[region_code_mask(df, code, column)].copy()


def regional_section_status(target: pd.Series, evidence_count: int, source_count: int) -> tuple[str, str]:
    code = normalize_text(target.get("ioos_region_code"))
    status = normalize_text(target.get("status")).lower()
    if code == MARACOOS_CODE:
        return "Pilot build", ""
    if evidence_count or source_count:
        return "Seeded", "neutral"
    if status == "active":
        return "Active", ""
    return "Queued", "warning"


def split_semicolon_items(value: object) -> list[str]:
    return [item.strip() for item in normalize_text(value).split(";") if item.strip()]


def html_list_items(items: list[str], fallback: str) -> str:
    if not items:
        items = [fallback]
    return "".join(f"<li>{hub_escape(item)}</li>" for item in items)


def regional_overview_cards_html(
    regional_targets_df: pd.DataFrame,
    evidence_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> str:
    cards: list[str] = []
    for _, target in regional_targets_df.iterrows():
        code = normalize_text(target.get("ioos_region_code"))
        evidence_count = len(rows_for_region_code(evidence_df, code))
        source_count = len(rows_for_region_code(best_sources_df, code))
        status_label, status_class = regional_section_status(target, evidence_count, source_count)
        priority_items = split_semicolon_items(target.get("priority_domains"))
        priority_preview = "; ".join(priority_items[:2]) or "Priority domains pending"
        cards.append(
            f"""
            <div class="region-card">
                <div class="region-card-header">
                    <div>
                        <span class="region-code">{hub_escape(code)}</span>
                        <span class="region-name">{hub_escape(normalize_text(target.get("region_name")) or code)}</span>
                    </div>
                    <span class="hub-chip {hub_escape(status_class)}">{hub_escape(status_label)}</span>
                </div>
                <p>{hub_escape(priority_preview)}</p>
                <div class="region-stats">
                    <div class="region-stat">
                        <span>{evidence_count:,}</span>
                        <small>public rows</small>
                    </div>
                    <div class="region-stat">
                        <span>{source_count:,}</span>
                        <small>best sources</small>
                    </div>
                </div>
                <p>{hub_escape(row_field(target, "evidence_gap", "Regional evidence gap pending."))}</p>
            </div>
            """
        )
    return f'<div class="region-grid">{"".join(cards)}</div>'


def semicolon_bullets(value: object, fallback: str) -> str:
    items = [item.strip() for item in normalize_text(value).split(";") if item.strip()]
    if not items:
        return f"- {fallback}"
    return "\n".join(f"- {item}" for item in items)


def regional_research_prompt(
    target: pd.Series,
    research_focus: str,
    source_leads: str,
    rows_requested: int,
) -> str:
    association = normalize_text(target.get("ioos_association")) or "[IOOS REGIONAL ASSOCIATION]"
    association_code = normalize_text(target.get("ioos_region_code")) or association
    region = normalize_text(target.get("region_name")) or "[REGION]"
    phase = normalize_text(target.get("phase")) or "regional evidence build"
    priority_domains = normalize_text(target.get("priority_domains")) or "[PRIORITY DOMAINS]"
    source_targets = normalize_text(target.get("source_targets")) or "[SOURCE TYPES TO SEARCH]"
    evidence_gap = normalize_text(target.get("evidence_gap")) or "[EVIDENCE GAP]"
    prompt_notes = normalize_text(target.get("prompt_notes")) or "[PROMPT NOTES]"
    focus = research_focus.strip() or normalize_text(target.get("starter_research_question")) or (
        f"Find source-backed economic impact evidence for {association} in the {region} region."
    )
    source_text = source_leads.strip() or "[OPTIONAL SOURCE URLS, TITLES, OR SEARCH LEADS]"
    priority_domain_bullets = semicolon_bullets(priority_domains, "[PRIORITY DOMAINS]")
    source_target_bullets = semicolon_bullets(source_targets, "[SOURCE TYPES TO SEARCH]")

    return f"""You are generating candidate regional evidence rows for the IOOS Economic Evidence App.

Regional build:
- Association: {association}
- IOOS region code: {association_code}
- Region: {region}
- Phase: {phase}
- Known evidence gap: {evidence_gap}
- Operator notes: {prompt_notes}

Research focus:
{focus}

Priority impact domains:
{priority_domain_bullets}

Priority source targets, in order:
{source_target_bullets}

Optional source leads from the operator:
{source_text}

Produce an actual .csv file as the output, not just comma-separated value text pasted into the chat. The .csv file must include this exact header row as the first line:

{intake_schema_csv_header()}

Task:
Find up to {rows_requested} candidate rows that can support a cautious, source-backed regional case study for {association}. Work silently in three passes before returning CSV:
1. Source scan: identify specific reports, product pages, agency pages, peer-reviewed studies, or datasets that mention {association}, IOOS, or a clearly relevant {region} decision context.
2. Evidence classification: decide whether each row is Direct decision-use evidence, Regional economic context, Comparable valuation evidence, or Follow-up lead.
3. CSV quality check: remove rows that lack a real source URL, a clear decision supported, limitations, or conservative claim language.

Preferred row mix:
- First priority: direct {association} or IOOS regional evidence tying an observing asset, product, forecast, portal, or data service to a user decision.
- Second priority: {region} decision-support evidence from NOAA, USCG, state agencies, ports, or academic partners where {association} or IOOS may be part of the pathway.
- Third priority: regional economic context rows that size affected sectors, but only if the claim clearly says they are context rather than {association}-attributable impact.
- Fourth priority: comparable valuation or method rows that can guide future {association} valuation, clearly marked as not direct {association} impact.

Rules:
- Do not create or imply official master-matrix rows. These are candidate rows for staged_evidence review.
- Use only real sources and include the exact source URL used for each row.
- Do not invent numbers, metrics, dollar years, source titles, agencies, or attribution.
- Prefer one source per row. If a claim requires multiple sources, create separate rows or explain the dependency in AI extraction notes.
- Set Region to a specific regional label such as "{region}", a state/local area, or the source-specific geography.
- Set IOOS region code to "{association_code}" for direct {association} rows.
- For context or comparison rows outside {association}, use one or more exact codes separated by semicolons: {allowed_ioos_region_codes_text()}.
- Use National for national-scale evidence and Multiple for evidence that spans several known regional associations.
- Set IOOS component to the specific {association} product, observing asset, partner system, or data service when the source supports it.
- Put the row type at the start of AI extraction notes, for example "Row type: Direct decision-use evidence" or "Row type: Regional economic context".
- Name the user group and decision as concretely as the source allows, such as emergency managers deciding flood response timing or search planners using surface-current data.
- If the source is about regional economic exposure but not {association} or IOOS decision support, set IOOS attribution strength to Contextual.
- If the source is about a broader NOAA, USCG, state, port, or academic system, do not call attribution Strong unless {association} or IOOS is explicitly part of the pathway.
- If the value is modeled, prospective, scenario-based, or benefit-transfer, set Evidence strength to Modeled.
- Economic number type must be exactly one of: {allowed_economic_number_types_text()}.
- IOOS role type must be exactly one of: {allowed_ioos_role_types_text()}.
- {record_created_prompt_rule()}
- Use Economic number type = Observed dollar benefit only for directly supported realized dollar benefits, avoided costs, savings, or revenue effects.
- Use Economic number type = Modeled dollar estimate for scenario, benefit-transfer, forecast-value, potential, or modeled dollar estimates.
- Use Economic number type = Dollar exposure/context when the source sizes a sector, market, GDP, jobs, cargo, assets, or exposure without estimating {association} benefits.
- Use Economic number type = Operational metric only for search-area reduction, forecast skill, dashboard use, data delivery, request volume, sensor coverage, or decision cadence without dollars.
- Use IOOS role type = Backend data source when {association} or IOOS data feeds, supports, or is assimilated into another tool or partner decision process but the source does not support a return estimate.
- In Allowed use and Not allowed use, state whether the row can support a hard-dollar claim, a modeled-dollar claim, an operational value claim, a backend attribution chain, or context only.
- Do not use a homepage, press release, or broad program page when a more specific report, product page, dataset, article, or case study is available.
- Evidence strength and IOOS attribution strength must be exactly one of: {allowed_ratings_text()}.
- Set Source verification needed to Yes for every row.
- Include limitations for every row, including source age, geographic limits, method uncertainty, and attribution caveats.
- Write Claim allowed as a conservative sentence COL could safely use.
- For context rows, Claim allowed must not imply {association} caused, created, saved, reduced, or avoided the economic value.
- Quote every CSV field that contains a comma, quote, or line break.
- Every row must include Source, Source URL, IOOS region code, Claim allowed, Limitations, Evidence strength, and IOOS attribution strength.
- Before returning, check that every row has exactly the same number of columns as the header.
- Return the .csv file only; do not include Markdown, commentary, or a pasted CSV transcript outside the file."""


def format_evidence_row_id(number: int) -> str:
    """Format a durable master evidence row identifier."""
    return f"{EVIDENCE_ROW_ID_PREFIX}-{number:0{EVIDENCE_ROW_ID_WIDTH}d}"


def evidence_row_id_number(value: object) -> int | None:
    """Extract the numeric part of current and legacy evidence IDs."""
    text = normalize_text(value)
    if not text:
        return None
    match = EVIDENCE_ROW_ID_RE.match(text)
    if match:
        return int(match.group(1))
    if text.isdigit():
        return int(text)
    return None


def next_row_id_number(df: pd.DataFrame) -> int:
    """Find the next available master evidence ID number."""
    if "row_id" not in df.columns or df.empty:
        return 1
    existing_numbers = [
        number
        for number in df["row_id"].map(evidence_row_id_number).tolist()
        if number is not None
    ]
    return (max(existing_numbers) + 1) if existing_numbers else 1


def next_row_id(df: pd.DataFrame) -> str:
    """Suggest the next durable master evidence row_id."""
    return format_evidence_row_id(next_row_id_number(df))


def append_evidence_row(row: dict[str, str], columns: list[str]) -> None:
    """Append one row to the evidence store while preserving existing rows."""
    append_rows(EVIDENCE_PATH, [row], columns)


def write_csv(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    """Write rows with a fixed header and mirror supported tables to Supabase."""
    table = PATH_TABLES.get(path)
    if table and supabase_enabled():
        if table == "source_registry":
            append_supabase_rows(table, rows)
        else:
            replace_supabase_table(table, rows)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_rows(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    """Append rows to local CSV and supported Supabase tables."""
    table = PATH_TABLES.get(path)
    if table and supabase_enabled():
        append_supabase_rows(table, rows)

    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def normalize_intake_df(df: pd.DataFrame) -> pd.DataFrame:
    """Keep candidate rows on the exact intake contract and set review defaults."""
    normalized = df.copy()
    normalized.columns = [str(column).strip().lstrip("\ufeff") for column in normalized.columns]
    for column in INTAKE_SCHEMA:
        if column not in normalized.columns:
            normalized[column] = ""
    normalized = normalized[INTAKE_SCHEMA].fillna("").astype(str)
    today_iso = date.today().isoformat()
    normalized["Date record created"] = normalized["Date record created"].apply(
        lambda value: normalize_text(value) or today_iso
    )
    normalized["Source verification needed"] = normalized["Source verification needed"].apply(
        lambda value: normalize_text(value) or "Yes"
    )
    normalized["Economic number type"] = normalized.apply(
        lambda row: normalize_text(row.get("Economic number type")) or infer_economic_number_type(row),
        axis=1,
    )
    normalized["IOOS role type"] = normalized.apply(
        lambda row: normalize_text(row.get("IOOS role type")) or infer_ioos_role_type(row),
        axis=1,
    )
    normalized["Allowed use"] = normalized.apply(
        lambda row: normalize_text(row.get("Allowed use")) or default_allowed_use(row),
        axis=1,
    )
    normalized["Not allowed use"] = normalized.apply(
        lambda row: normalize_text(row.get("Not allowed use")) or default_not_allowed_use(row),
        axis=1,
    )
    return normalized


def validate_intake_csv_shape(file_bytes: bytes) -> list[str]:
    """Catch malformed CSV records before pandas can reinterpret them as an index."""
    errors: list[str] = []
    try:
        csv_text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return ["CSV must be UTF-8 encoded."]

    try:
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader, None)
        if header is None:
            return ["CSV is empty."]

        expected_columns = len(header)
        for row_number, row in enumerate(reader, start=2):
            if not row or not any(normalize_text(value) for value in row):
                continue
            if len(row) != expected_columns:
                errors.append(
                    f"CSV row {row_number} has {len(row)} values, but the header has "
                    f"{expected_columns}. Quote fields that contain commas."
                )
    except csv.Error as exc:
        return [f"CSV could not be parsed: {exc}"]

    return errors


def validate_intake_df(df: pd.DataFrame) -> list[str]:
    """Validate AI candidate rows before they can enter staging or the matrix."""
    errors: list[str] = []
    columns = [str(column).strip().lstrip("\ufeff") for column in df.columns]
    missing_columns = [
        column
        for column in INTAKE_SCHEMA
        if column not in columns and column not in INTAKE_OPTIONAL_COLUMNS
    ]
    extra_columns = [column for column in columns if column not in INTAKE_SCHEMA]

    if missing_columns:
        errors.append("Missing required columns: " + ", ".join(missing_columns))
    if extra_columns:
        errors.append("Unexpected columns: " + ", ".join(extra_columns))
    if errors:
        return errors

    normalized = normalize_intake_df(df)
    for row_number, (_, row) in enumerate(normalized.iterrows(), start=1):
        label = f"row {row_number}"
        for column in INTAKE_REQUIRED_VALUES:
            if not normalize_text(row.get(column)):
                errors.append(f"{label} missing required value: {column}")
        created_date = normalize_text(row.get("Date record created"))
        if created_date:
            try:
                date.fromisoformat(created_date)
            except ValueError:
                errors.append(f"{label} Date record created must use YYYY-MM-DD format")
        for column in ["Evidence strength", "IOOS attribution strength"]:
            value = normalize_text(row.get(column))
            if value and value not in ALLOWED_RATINGS:
                errors.append(f"{label} has invalid {column}: {value}")
        economic_type = normalize_text(row.get("Economic number type"))
        if economic_type and economic_type not in ALLOWED_ECONOMIC_NUMBER_TYPES:
            errors.append(
                f"{label} has invalid Economic number type: {economic_type}. "
                f"Use: {allowed_economic_number_types_text()}"
            )
        ioos_role = normalize_text(row.get("IOOS role type"))
        if ioos_role and ioos_role not in ALLOWED_IOOS_ROLE_TYPES:
            errors.append(
                f"{label} has invalid IOOS role type: {ioos_role}. "
                f"Use: {allowed_ioos_role_types_text()}"
            )
        invalid_codes = invalid_ioos_region_codes(row.get("IOOS region code"))
        if invalid_codes:
            errors.append(
                f"{label} has invalid IOOS region code(s): {', '.join(invalid_codes)}. "
                f"Use: {allowed_ioos_region_codes_text()}"
            )
        verification = normalize_text(row.get("Source verification needed"))
        if verification not in {"Yes", "No"}:
            errors.append(f"{label} Source verification needed must be Yes or No")
    return errors


def slugify_source_id(value: str, existing_ids: set[str]) -> str:
    """Create a stable source_id from a staged Source value."""
    base = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "ai-intake-source"
    base = base[:60].strip("-") or "ai-intake-source"
    candidate = base
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    existing_ids.add(candidate)
    return candidate


def map_staged_row_to_evidence(row: dict[str, str], source_id: str, row_id: str) -> dict[str, str]:
    """Convert one exact-schema candidate row into the official matrix columns."""
    evidence_row = {
        evidence_column: normalize_text(row.get(intake_column))
        for intake_column, evidence_column in INTAKE_TO_EVIDENCE_COLUMNS.items()
    }
    evidence_row["row_id"] = row_id
    evidence_row["source_id"] = source_id
    return evidence_row


def source_lookup(source_df: pd.DataFrame) -> tuple[dict[tuple[str, str], str], set[str]]:
    """Build source matching helpers from the source registry."""
    lookup: dict[tuple[str, str], str] = {}
    existing_ids: set[str] = set()
    if source_df.empty:
        return lookup, existing_ids

    for _, source in source_df.iterrows():
        source_id = normalize_text(source.get("source_id"))
        if not source_id:
            continue
        existing_ids.add(source_id)
        key = (
            normalize_text(source.get("source_name")).lower(),
            normalize_text(source.get("source_url")).lower(),
        )
        lookup[key] = source_id
    return lookup, existing_ids


def accepted_rows_to_official(
    staged_rows: list[dict[str, str]],
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
) -> tuple[list[dict[str, str]], pd.DataFrame]:
    """Convert verified staged rows to official evidence rows and source records."""
    lookup, existing_ids = source_lookup(source_df)
    source_records = source_df.to_dict("records") if not source_df.empty else []
    source_row_index = {normalize_text(row.get("source_id")): row for row in source_records}
    used_row_ids = {normalize_text(row_id) for row_id in evidence_df.get("row_id", pd.Series(dtype=str))}
    next_id_number = next_row_id_number(evidence_df)
    evidence_rows: list[dict[str, str]] = []

    for row in staged_rows:
        source_name = normalize_text(row.get("Source"))
        source_url = normalize_text(row.get("Source URL"))
        key = (source_name.lower(), source_url.lower())
        source_id = lookup.get(key)
        if not source_id:
            source_id = slugify_source_id(source_name or source_url, existing_ids)
            lookup[key] = source_id
            source_record = {
                "source_id": source_id,
                "source_name": source_name,
                "source_url": source_url,
                "source_type": "AI intake",
                "verification_status": "Verified",
                "rows_supported": "",
                "notes": normalize_text(row.get("AI extraction notes")),
            }
            source_records.append(source_record)
            source_row_index[source_id] = source_record

        row_id = normalize_text(row.get("row_id"))
        if not row_id or row_id in used_row_ids:
            row_id = format_evidence_row_id(next_id_number)
            next_id_number += 1
        used_row_ids.add(row_id)

        evidence_rows.append(map_staged_row_to_evidence(row, source_id, row_id))
        source_record = source_row_index.get(source_id)
        if source_record is not None:
            supported = [
                value.strip()
                for value in normalize_text(source_record.get("rows_supported")).split(";")
                if value.strip()
            ]
            if row_id not in supported:
                supported.append(row_id)
            source_record["rows_supported"] = "; ".join(supported)

    source_columns = list(source_df.columns) if not source_df.empty else [
        "source_id",
        "source_name",
        "source_url",
        "source_type",
        "verification_status",
        "rows_supported",
        "notes",
    ]
    updated_sources = pd.DataFrame(source_records, columns=source_columns)
    return evidence_rows, updated_sources


def best_source_records(best_sources_df: pd.DataFrame) -> list[dict[str, str]]:
    """Return best_sources rows on the exact schema the app can persist."""
    if best_sources_df.empty:
        return []
    return [
        {column: normalize_text(row.get(column)) for column in BEST_SOURCE_SCHEMA}
        for _, row in best_sources_df.iterrows()
    ]


def split_semicolon_values(value: object) -> list[str]:
    return [part.strip() for part in normalize_text(value).split(";") if part.strip()]


def merge_semicolon_values(existing: object, *new_values: object) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for value in [existing, *new_values]:
        for part in split_semicolon_values(value):
            key = part.lower()
            if key in seen:
                continue
            seen.add(key)
            values.append(part)
    return "; ".join(values)


def infer_best_source_priority(row: pd.Series) -> str:
    evidence = normalize_text(row.get("Evidence strength"))
    attribution = normalize_text(row.get("IOOS attribution strength"))
    if evidence in {"Strong", "Medium"} and attribution in {"Strong", "Medium"}:
        return "primary"
    if evidence == "Contextual" or attribution == "Contextual":
        return "context"
    if "Needs verification" in {evidence, attribution}:
        return "hold"
    return "supporting"


def staged_row_to_best_source_record(row: pd.Series, source_id: str) -> dict[str, str]:
    evidence = normalize_text(row.get("Evidence strength")) or "Unrated"
    attribution = normalize_text(row.get("IOOS attribution strength")) or "Unrated"
    ioos_role = normalize_text(row.get("IOOS role type"))
    notes = normalize_text(row.get("AI extraction notes"))
    not_allowed = normalize_text(row.get("Not allowed use"))
    limitations = normalize_text(row.get("Limitations"))
    caveats = limitations
    if not_allowed:
        caveats = f"{caveats} Not allowed: {not_allowed}".strip()
    return {
        "source_id": source_id,
        "source_name": normalize_text(row.get("Source")) or normalize_text(row.get("Source URL")) or "Verified staged source",
        "source_url": normalize_text(row.get("Source URL")),
        "source_type": "verified staged evidence source",
        "ioos_region_code": normalize_text(row.get("IOOS region code")) or "Unknown",
        "priority_tier": infer_best_source_priority(row),
        "briefing_role": normalize_text(row.get("Allowed use")) or normalize_text(row.get("Decision supported")),
        "impact_domains": normalize_text(row.get("Impact domain")),
        "staged_row_ids": normalize_text(row.get("row_id")),
        "key_metrics": normalize_text(row.get("Metric")),
        "evidence_profile": f"{evidence} evidence. {notes}".strip(),
        "attribution_profile": f"{attribution} IOOS attribution. {ioos_role}".strip(),
        "recommended_claim_language": normalize_text(row.get("Claim allowed")),
        "caveats": caveats,
        "source_verification_needed": "No",
        "status": "verified",
    }


def matching_best_source_index(records: list[dict[str, str]], row: pd.Series) -> int | None:
    row_id = normalize_text(row.get("row_id")).lower()
    source_url = normalize_text(row.get("Source URL")).lower()
    source_name = normalize_text(row.get("Source")).lower()

    for index, record in enumerate(records):
        staged_ids = {value.lower() for value in split_semicolon_values(record.get("staged_row_ids"))}
        if row_id and row_id in staged_ids:
            return index
        if source_url and source_url == normalize_text(record.get("source_url")).lower():
            return index
        if source_name and source_name == normalize_text(record.get("source_name")).lower():
            return index
    return None


def merge_best_source_record(existing: dict[str, str], incoming: dict[str, str]) -> dict[str, str]:
    merged = {column: normalize_text(existing.get(column)) for column in BEST_SOURCE_SCHEMA}
    for column in BEST_SOURCE_SCHEMA:
        if not merged.get(column):
            merged[column] = normalize_text(incoming.get(column))
    merged["staged_row_ids"] = merge_semicolon_values(
        merged.get("staged_row_ids"),
        incoming.get("staged_row_ids"),
    )
    merged["impact_domains"] = merge_semicolon_values(
        merged.get("impact_domains"),
        incoming.get("impact_domains"),
    )
    merged["key_metrics"] = merge_semicolon_values(
        merged.get("key_metrics"),
        incoming.get("key_metrics"),
    )
    merged["source_verification_needed"] = "No"
    merged["status"] = "verified"
    if merged.get("priority_tier") not in {"primary", "supporting", "context", "hold"}:
        merged["priority_tier"] = incoming.get("priority_tier", "supporting")
    return merged


def upsert_best_source_from_staged_row(
    row: pd.Series,
    best_sources_df: pd.DataFrame,
) -> tuple[list[dict[str, str]], str]:
    records = best_source_records(best_sources_df)
    existing_ids = {normalize_text(record.get("source_id")) for record in records if normalize_text(record.get("source_id"))}
    match_index = matching_best_source_index(records, row)

    if match_index is None:
        row_id = normalize_text(row.get("row_id"))
        source_name = normalize_text(row.get("Source"))
        source_url = normalize_text(row.get("Source URL"))
        source_id = slugify_source_id(f"bs {row_id or source_name or source_url}", existing_ids)
        records.append(staged_row_to_best_source_record(row, source_id))
        return records, source_id

    source_id = normalize_text(records[match_index].get("source_id"))
    if not source_id:
        source_id = slugify_source_id(
            f"bs {normalize_text(row.get('row_id')) or normalize_text(row.get('Source'))}",
            existing_ids,
        )
    incoming = staged_row_to_best_source_record(row, source_id)
    records[match_index] = merge_best_source_record(records[match_index], incoming)
    return records, source_id


def append_ai_review_note(existing: object, note: str) -> str:
    existing_text = normalize_text(existing)
    if not note:
        return existing_text
    if note in existing_text:
        return existing_text
    if existing_text:
        return f"{existing_text} | {note}"
    return note


def update_staged_review_row(
    staged_df: pd.DataFrame,
    row_index: int,
    source_verification_needed: str,
    review_note: str,
) -> pd.DataFrame:
    normalized = normalize_intake_df(staged_df)
    if row_index not in normalized.index:
        return normalized
    normalized.at[row_index, "Source verification needed"] = source_verification_needed
    normalized.at[row_index, "AI extraction notes"] = append_ai_review_note(
        normalized.at[row_index, "AI extraction notes"],
        review_note,
    )
    return normalized


def pending_source_review_rows(staged_df: pd.DataFrame) -> pd.DataFrame:
    if staged_df.empty:
        return pd.DataFrame()
    normalized = normalize_intake_df(staged_df)
    return normalized[
        normalized["Source verification needed"].map(normalize_text).str.lower() != "no"
    ].copy()


def run_validation() -> subprocess.CompletedProcess[str]:
    """Run the Python validator using the current interpreter."""
    return subprocess.run(
        [sys.executable, str(VALIDATOR_PATH)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def count_summary(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Build a readable count and percent table for one categorical column."""
    if df.empty or column not in df.columns:
        return pd.DataFrame(columns=["Category", "Rows", "Share"])

    counts = df[column].replace("", "Blank").value_counts().reset_index()
    counts.columns = ["Category", "Rows"]
    total = counts["Rows"].sum()
    counts["Share"] = (counts["Rows"] / total * 100) if total else 0
    return counts


def render_summary_table(df: pd.DataFrame, title: str) -> None:
    """Render category counts with bars that stay readable for long labels."""
    st.subheader(title)
    if df.empty:
        st.info("No data available.")
        return

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Category": st.column_config.TextColumn(width="large"),
            "Rows": st.column_config.NumberColumn(width="small"),
            "Share": st.column_config.ProgressColumn(
                "Share",
                format="%.0f%%",
                min_value=0,
                max_value=100,
                width="medium",
            ),
        },
    )


def normalize_text(value: object) -> str:
    """Normalize text used by derived dashboard classifications."""
    return str(value or "").strip()


def brief_escape(value: object) -> str:
    """Escape matrix text for the congressional briefing HTML preview."""
    return html_lib.escape(normalize_text(value), quote=False).replace("\u00ae", "&reg;")


def asset_data_uri(path: Path, mime_type: str) -> str:
    """Embed small static assets directly in generated HTML."""
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:{mime_type};base64,{encoded}"


VALUE_CHAIN_LAYERS = [
    ("Obs", "Observations", "Buoys, gliders, HF radar, satellites, coastal stations."),
    ("Mod", "Models", "Data assimilation, circulation models, risk and exposure models."),
    ("Fcst", "Forecast Products", "Operational products people can act on."),
    ("Dec", "Sector Decisions", "Navigation, closures, routing, emergency response, planning."),
    ("Val", "Economic Value", "Avoided cost, added revenue, jobs, benefit ratios, or resilience value."),
]

STRENGTH_DEFINITIONS = {
    "strong": ("Strong", "Direct, credible, source-backed metric support.", "strength-strong"),
    "medium": ("Moderate", "Useful evidence with method, scope, age, or transfer limits.", "strength-medium"),
    "modeled": ("Modeled", "Scenario, projection, model, or benefit-transfer estimate.", "strength-modeled"),
    "contextual": ("Indicative", "Context for economic relevance, not a standalone quantified claim.", "strength-contextual"),
    "needs verification": ("Needs review", "Claim, metric, source, or attribution needs checking.", "strength-needs-verification"),
    "": ("Unrated", "No rating is currently recorded.", "strength-contextual"),
}

ATTRIBUTION_DEFINITIONS = {
    "strong": ("Direct attribution", 5, "IOOS traces through the value chain to a sector decision and economic value."),
    "medium": ("Partial attribution", 4, "IOOS is a documented input, but the economic value depends on other systems or assumptions."),
    "modeled": ("Modeled attribution", 3, "The link is estimated through a model, scenario, or transferred benefit method."),
    "contextual": ("Contextual link", 2, "The source supports the setting, but not a direct IOOS-to-value claim."),
    "needs verification": ("Review link", 1, "The IOOS connection needs reviewer confirmation."),
    "": ("Unrated link", 0, "No attribution rating is currently recorded."),
}

STATUS_DEFINITIONS = {
    "report-ready": ("Ready for external use", "status-report-ready"),
    "ready-for-external-use": ("Ready for external use", "status-ready-for-external-use"),
    "verified": ("Verified", "status-verified"),
    "use-with-caution": ("Use with caution", "status-use-with-caution"),
    "background-only": ("Background only", "status-background-only"),
    "needs-follow-up": ("Needs follow-up", "status-needs-follow-up"),
    "staged": ("Staged", "status-staged"),
    "draft": ("Draft", "status-draft"),
    "in-review": ("In review", "status-in-review"),
    "flagged": ("Flagged", "status-flagged"),
    "rejected": ("Rejected", "status-rejected"),
    "": ("Unspecified", "status-background-only"),
}

SAVED_FILTER_SETS = {
    "Custom": {},
    "Ready external claims": {
        "external_ready": True,
    },
    "Strong direct attribution": {
        "evidence_strength": ["Strong"],
        "ioos_attribution_strength": ["Strong"],
        "external_ready": True,
    },
    "Gulf strong ready": {
        "ioos_region_code": ["GCOOS"],
        "evidence_strength": ["Strong"],
        "external_ready": True,
    },
    "Fisheries and HABs": {
        "impact_domain_contains": "fisheries",
        "external_ready": False,
    },
    "Needs reviewer attention": {
        "status": ["needs-follow-up", "use-with-caution"],
        "verification_needed": ["Yes"],
    },
}


def hub_escape(value: object) -> str:
    """Escape user/data text for small HTML fragments."""
    return html_lib.escape(normalize_text(value), quote=True)


def rating_key(value: object) -> str:
    text = normalize_text(value).lower()
    if text in {"moderate", "medium"}:
        return "medium"
    if text in {"indicative"}:
        return "contextual"
    return text


def strength_badge_html(value: object) -> str:
    label, description, css_class = STRENGTH_DEFINITIONS.get(
        rating_key(value),
        (normalize_text(value) or "Unrated", "Rating not in the current rubric.", "strength-contextual"),
    )
    return (
        f'<span class="trust-badge {css_class}" title="{hub_escape(description)}">'
        f'Evidence: {hub_escape(label)}</span>'
    )


def attribution_definition(value: object) -> tuple[str, int, str]:
    return ATTRIBUTION_DEFINITIONS.get(
        rating_key(value),
        (normalize_text(value) or "Unrated link", 0, "Attribution rating is not in the current rubric."),
    )


def attribution_chain_html(value: object, show_label: bool = True) -> str:
    label, active_count, description = attribution_definition(value)
    steps = []
    for index, (short_label, long_label, _) in enumerate(VALUE_CHAIN_LAYERS, start=1):
        active_class = " active" if index <= active_count else ""
        steps.append(
            f'<span class="chain-step{active_class}" title="{hub_escape(long_label)}">{hub_escape(short_label)}</span>'
        )
    label_html = (
        f'<span class="chain-label" title="{hub_escape(description)}">{hub_escape(label)}</span>'
        if show_label
        else ""
    )
    return f'<span class="ioos-chain">{"".join(steps)}{label_html}</span>'


def status_definition(status: object) -> tuple[str, str]:
    key = normalize_text(status).lower().replace(" ", "-").replace("_", "-")
    return STATUS_DEFINITIONS.get(
        key,
        (normalize_text(status) or "Unspecified", "status-background-only"),
    )


def status_pill_html(status: object) -> str:
    label, css_class = status_definition(status)
    return f'<span class="status-pill {css_class}">Status: {hub_escape(label)}</span>'


def row_review_status(row: pd.Series) -> str:
    recorded = normalize_text(row.get("dashboard_status"))
    if recorded:
        return recorded
    source_verification = normalize_text(row.get("source_verification_needed")).lower()
    evidence = normalize_text(row.get("evidence_strength"))
    attribution = normalize_text(row.get("ioos_attribution_strength"))
    if source_verification == "yes" or "needs verification" in {evidence.lower(), attribution.lower()}:
        return "needs-follow-up"
    if evidence in {"Strong", "Medium"} and attribution in {"Strong", "Medium"}:
        return "report-ready"
    if evidence == "Contextual" or attribution == "Contextual":
        return "background-only"
    return "use-with-caution"


def is_external_ready_row(row: pd.Series) -> bool:
    status = row_review_status(row)
    evidence = normalize_text(row.get("evidence_strength"))
    attribution = normalize_text(row.get("ioos_attribution_strength"))
    source_verification = normalize_text(row.get("source_verification_needed")).lower()
    return (
        status in {"report-ready", "ready-for-external-use", "verified"}
        and evidence in {"Strong", "Medium"}
        and attribution in {"Strong", "Medium"}
        and source_verification != "yes"
    )


def trust_signal_cluster_html(row: pd.Series) -> str:
    return (
        '<div class="trust-cluster">'
        f'{strength_badge_html(row.get("evidence_strength"))}'
        f'{attribution_chain_html(row.get("ioos_attribution_strength"))}'
        f'{status_pill_html(row_review_status(row))}'
        "</div>"
    )


def source_for_row(row: pd.Series, source_df: pd.DataFrame) -> pd.Series | None:
    source_id = normalize_text(row.get("source_id"))
    if source_id and not source_df.empty and "source_id" in source_df.columns:
        matches = source_df[source_df["source_id"].map(normalize_text) == source_id]
        if not matches.empty:
            return matches.iloc[0]
    return None


def source_citation(row: pd.Series, source_df: pd.DataFrame) -> str:
    source_row = source_for_row(row, source_df)
    source_id = normalize_text(row.get("source_id"))
    source_name = row_field(source_row, "source_name", source_id or row_field(row, "source_name", "Source not specified"))
    source_type = row_field(source_row, "source_type", row_field(row, "source_type"))
    source_url = row_field(source_row, "source_url", row_field(row, "source_url"))
    year = row_field(row, "metric_year_or_dollar_year")
    parts = [source_name]
    if year and year.lower() != "not applicable":
        parts.append(year)
    if source_type:
        parts.append(source_type)
    if source_url:
        parts.append(source_url)
    return ". ".join(parts)


def claim_copy_block(row: pd.Series, source_df: pd.DataFrame) -> str:
    claim = row_field(row, "claim_allowed", row_field(row, "metric", "Claim not specified"))
    metric = row_field(row, "metric")
    limitations = row_field(row, "limitations")
    citation = source_citation(row, source_df)
    economic_type = row_field(row, "economic_number_type")
    ioos_role = row_field(row, "ioos_role_type")
    allowed_use = row_field(row, "allowed_use")
    not_allowed_use = row_field(row, "not_allowed_use")
    lines = [claim]
    if metric and metric != claim:
        lines.append(f"Metric: {metric}")
    if economic_type or ioos_role:
        lines.append(
            "Claim use: "
            f"{economic_type or 'Unclassified economic number'}; "
            f"{ioos_role or 'Unclassified IOOS role'}."
        )
    if allowed_use:
        lines.append(f"Allowed use: {allowed_use}")
    if not_allowed_use:
        lines.append(f"Not allowed use: {not_allowed_use}")
    lines.append(f"Source: {citation}")
    if limitations:
        lines.append(f"Limitations: {limitations}")
    lines.append(
        "Review status: "
        f"{status_definition(row_review_status(row))[0]}; "
        f"evidence {normalize_text(row.get('evidence_strength')) or 'unrated'}; "
        f"IOOS attribution {normalize_text(row.get('ioos_attribution_strength')) or 'unrated'}."
    )
    return "\n".join(lines)


def render_copy_button(text: str, label: str = "Copy claim + citation") -> None:
    button_id = f"copy_{abs(hash(text))}"
    payload = json.dumps(text)
    components.html(
        f"""
        <button id="{button_id}" style="
            background:#0a5d8f;border:0;border-radius:6px;color:white;
            cursor:pointer;font:700 14px system-ui;padding:10px 14px;">
            {html_lib.escape(label)}
        </button>
        <span id="{button_id}_status" style="color:#5e6f79;font:13px system-ui;margin-left:10px;"></span>
        <script>
        const btn = document.getElementById("{button_id}");
        const status = document.getElementById("{button_id}_status");
        btn.addEventListener("click", async () => {{
            try {{
                await navigator.clipboard.writeText({payload});
                status.textContent = "Copied";
            }} catch (error) {{
                status.textContent = "Copy failed; select the text below.";
            }}
        }});
        </script>
        """,
        height=54,
    )


def truncate_text(value: object, max_chars: int = 180) -> str:
    text = normalize_text(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def evidence_card_html(row: pd.Series, source_df: pd.DataFrame) -> str:
    row_id = row_field(row, "row_id", "Evidence row")
    claim = row_field(row, "claim_allowed", row_field(row, "metric", "No claim text recorded."))
    metric = row_field(row, "metric")
    source_name = row_field(row, "source_name")
    if not source_name:
        source_name = row_field(source_for_row(row, source_df), "source_name", row_field(row, "source_id", "Source pending"))
    meta = [
        row_field(row, "date_record_created"),
        row_field(row, "impact_domain"),
        row_field(row, "region"),
        row_field(row, "ioos_region_code"),
        row_field(row, "metric_year_or_dollar_year"),
        row_field(row, "economic_number_type"),
        row_field(row, "ioos_role_type"),
    ]
    meta_html = "".join(f"<span>{hub_escape(item)}</span>" for item in meta if item)
    return f"""
    <div class="evidence-card">
        <span class="hub-chip neutral">{hub_escape(row_id)}</span>
        <h3>{hub_escape(claim)}</h3>
        <div class="metric-value">{hub_escape(metric)}</div>
        <div class="row-meta">{meta_html}<span>{hub_escape(source_name)}</span></div>
        {trust_signal_cluster_html(row)}
    </div>
    """


def evidence_display_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    display = df.copy()
    display["claim"] = display.apply(
        lambda row: row_field(row, "claim_allowed", row_field(row, "metric")),
        axis=1,
    )
    display["review_status"] = display.apply(lambda row: status_definition(row_review_status(row))[0], axis=1)
    display["attribution_signal"] = display["ioos_attribution_strength"].apply(
        lambda value: attribution_definition(value)[0] if normalize_text(value) else "Unrated link"
    )
    display["external_use_ready"] = display.apply(
        lambda row: "Yes" if is_external_ready_row(row) else "No",
        axis=1,
    )
    display["source"] = display.apply(
        lambda row: row_field(row, "source_name", row_field(row, "source_id")),
        axis=1,
    )
    columns = [
        "row_id",
        "date_record_created",
        "claim",
        "metric",
        "source",
        "source_url",
        "impact_domain",
        "ioos_region_code",
        "economic_number_type",
        "ioos_role_type",
        "evidence_strength",
        "attribution_signal",
        "review_status",
        "external_use_ready",
    ]
    return display[[column for column in columns if column in display.columns]]


def metric_year_value(row: pd.Series) -> int | None:
    text = row_field(row, "metric_year_or_dollar_year")
    matches = re.findall(r"(19|20)\d{2}", text)
    if not matches:
        full_matches = re.findall(r"\b((?:19|20)\d{2})\b", text)
        return int(full_matches[0]) if full_matches else None
    full_matches = re.findall(r"\b((?:19|20)\d{2})\b", text)
    return int(full_matches[0]) if full_matches else None


def add_metric_year_column(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "metric_year_or_dollar_year" not in df.columns:
        return df.copy()
    with_year = df.copy()
    with_year["metric_year"] = with_year.apply(metric_year_value, axis=1)
    return with_year


def filter_by_contains(df: pd.DataFrame, column: str, query: str) -> pd.DataFrame:
    if not query or column not in df.columns:
        return df
    return df[df[column].map(normalize_text).str.contains(query, case=False, na=False)]


def apply_evidence_filters(df: pd.DataFrame, filter_state: dict[str, object]) -> pd.DataFrame:
    filtered = df.copy()
    search_text = normalize_text(filter_state.get("search"))
    if search_text:
        filtered = search_dataframe(filtered, search_text)

    for column in [
        "impact_domain",
        "ioos_region_code",
        "source_type",
        "evidence_strength",
        "ioos_attribution_strength",
    ]:
        selected = filter_state.get(column)
        if selected and column in filtered.columns:
            selected_set = set(selected if isinstance(selected, list) else [selected])
            filtered = filtered[filtered[column].isin(selected_set)]

    if filter_state.get("impact_domain_contains"):
        filtered = filter_by_contains(filtered, "impact_domain", normalize_text(filter_state.get("impact_domain_contains")))

    if filter_state.get("external_ready"):
        filtered = filtered[filtered.apply(is_external_ready_row, axis=1)]

    statuses = filter_state.get("status")
    if statuses:
        selected_statuses = {normalize_text(status).lower() for status in statuses}
        filtered = filtered[
            filtered.apply(lambda row: normalize_text(row_review_status(row)).lower() in selected_statuses, axis=1)
        ]

    verification_needed = filter_state.get("verification_needed")
    if verification_needed and "source_verification_needed" in filtered.columns:
        selected_set = set(verification_needed if isinstance(verification_needed, list) else [verification_needed])
        filtered = filtered[filtered["source_verification_needed"].isin(selected_set)]

    year_range = filter_state.get("year_range")
    if year_range and "metric_year" in filtered.columns:
        start_year, end_year = year_range
        year_series = pd.to_numeric(filtered["metric_year"], errors="coerce")
        filtered = filtered[year_series.isna() | year_series.between(start_year, end_year)]

    return filtered


def evidence_row_by_id(evidence_df: pd.DataFrame, row_id: str) -> pd.Series | None:
    if evidence_df.empty or "row_id" not in evidence_df.columns:
        return None
    matches = evidence_df[evidence_df["row_id"].map(normalize_text) == row_id]
    if matches.empty:
        return None
    return matches.iloc[0]


def row_field(row: pd.Series | None, column: str, fallback: str = "") -> str:
    if row is None:
        return fallback
    value = normalize_text(row.get(column))
    return value or fallback


def atlas_row_text(row: pd.Series) -> str:
    """Collect the text used for atlas-level classification."""
    return " ".join(
        normalize_text(row.get(column))
        for column in EVIDENCE_ATLAS_TEXT_COLUMNS
        if column in row.index
    )


def atlas_text_matches(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def atlas_level_keys_for_row(row: pd.Series) -> list[str]:
    """Return all atlas levels a row supports; levels intentionally overlap."""
    economic_type = row_field(row, "economic_number_type")
    row_text = atlas_row_text(row)
    keys: list[str] = []

    if economic_type in {"Observed dollar benefit", "Modeled dollar estimate"} or (
        has_dollar_signal(row_text) and economic_type != "Dollar exposure/context"
    ):
        keys.append("level_1")
    if economic_type == "Operational metric only" or atlas_text_matches(row_text, ATLAS_OPERATIONAL_PATTERNS):
        keys.append("level_2")
    if atlas_text_matches(row_text, ATLAS_AVOIDED_LOSS_PATTERNS):
        keys.append("level_3")
    if economic_type == "Dollar exposure/context" or atlas_text_matches(row_text, ATLAS_ECONOMIC_ACTIVITY_PATTERNS):
        keys.append("level_4")

    ordered_keys = [level["key"] for level in EVIDENCE_ATLAS_LEVELS if level["key"] in set(keys)]
    return ordered_keys or ["unclassified"]


def atlas_level_label(key: str) -> str:
    level = EVIDENCE_ATLAS_LEVEL_BY_KEY.get(key, EVIDENCE_ATLAS_UNCLASSIFIED)
    return level["label"]


def atlas_level_labels_for_row(row: pd.Series) -> str:
    return "; ".join(atlas_level_label(key) for key in atlas_level_keys_for_row(row))


def atlas_pathway_for_row(row: pd.Series) -> str:
    keys = atlas_level_keys_for_row(row)
    if "level_3" in keys:
        return "Avoided losses"
    if "level_2" in keys:
        return "Operational savings"
    if "level_4" in keys:
        return "Economic activity supported"
    if "level_1" in keys:
        return "Reported dollar benefit"
    return "Needs classification"


def atlas_claim_boundary_for_row(row: pd.Series) -> str:
    keys = atlas_level_keys_for_row(row)
    economic_type = row_field(row, "economic_number_type")
    if keys == ["unclassified"]:
        return "Review before external use"
    if "level_4" in keys and "level_1" not in keys:
        return "Context only - do not add to benefit totals"
    if economic_type == "Modeled dollar estimate":
        return "Use as published estimate with model caveats"
    if economic_type == "Operational metric only":
        return "Use metric directly; do not convert to dollars here"
    return "Use with source, year, and limitations"


def add_evidence_atlas_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived atlas tags without changing the underlying evidence records."""
    if df.empty:
        return df.copy()
    atlas_df = df.copy()
    atlas_df["atlas_level_keys"] = atlas_df.apply(
        lambda row: ";".join(atlas_level_keys_for_row(row)),
        axis=1,
    )
    atlas_df["atlas_levels"] = atlas_df.apply(atlas_level_labels_for_row, axis=1)
    atlas_df["atlas_pathway"] = atlas_df.apply(atlas_pathway_for_row, axis=1)
    atlas_df["atlas_claim_boundary"] = atlas_df.apply(atlas_claim_boundary_for_row, axis=1)
    return atlas_df


def atlas_level_count_table(atlas_df: pd.DataFrame) -> pd.DataFrame:
    """Count rows by overlapping atlas level."""
    rows: list[dict[str, object]] = []
    total = len(atlas_df)
    for level in EVIDENCE_ATLAS_LEVELS + [EVIDENCE_ATLAS_UNCLASSIFIED]:
        key = level["key"]
        if atlas_df.empty or "atlas_level_keys" not in atlas_df.columns:
            count = 0
        else:
            count = int(atlas_df["atlas_level_keys"].map(lambda value: key in split_semicolon_values(value)).sum())
        rows.append(
            {
                "Category": atlas_level_label(key),
                "Rows": count,
                "Share of rows": (count / total * 100) if total else 0,
                "Safe use": level["safe_use"],
            }
        )
    return pd.DataFrame(rows)


def atlas_level_cards_html(atlas_df: pd.DataFrame) -> str:
    count_lookup = {
        row["Category"]: int(row["Rows"])
        for _, row in atlas_level_count_table(atlas_df).iterrows()
    }
    cards = []
    for level in EVIDENCE_ATLAS_LEVELS:
        label = atlas_level_label(level["key"])
        cards.append(
            f"""
            <div class="atlas-level-card">
                <span class="hub-chip neutral">Evidence category</span>
                <b>{hub_escape(level["title"])}</b>
                <span class="atlas-count">{count_lookup.get(label, 0):,}</span>
                <p>{hub_escape(level["definition"])}</p>
                <div class="atlas-rule">{hub_escape(level["safe_use"])}</div>
            </div>
            """
        )
    return f'<div class="atlas-level-grid">{"".join(cards)}</div>'


def atlas_rows_for_level(atlas_df: pd.DataFrame, level_key: str) -> pd.DataFrame:
    """Return rows tagged to one financial evidence category."""
    return atlas_filtered_by_levels(atlas_df, [level_key])


def atlas_category_summary(
    df: pd.DataFrame,
    column: str,
    split_values: bool = False,
    limit: int = 10,
) -> pd.DataFrame:
    """Build count/share data for a financial evidence chart."""
    if df.empty or column not in df.columns:
        return pd.DataFrame(columns=["Category", "Rows", "Share"])

    values: list[str] = []
    for value in df[column]:
        if split_values:
            parts = split_semicolon_values(value)
            values.extend(parts or ["Blank"])
        else:
            values.append(normalize_text(value) or "Blank")

    if not values:
        return pd.DataFrame(columns=["Category", "Rows", "Share"])

    counts = pd.Series(values, dtype="object").value_counts().head(limit).reset_index()
    counts.columns = ["Category", "Rows"]
    total = len(values)
    counts["Share"] = (counts["Rows"] / total * 100) if total else 0
    return counts


def atlas_unique_count(df: pd.DataFrame, column: str, split_values: bool = False) -> int:
    if df.empty or column not in df.columns:
        return 0
    if split_values:
        values = {
            part
            for value in df[column]
            for part in split_semicolon_values(value)
            if normalize_text(part)
        }
        return len(values)
    return int(df[column].map(normalize_text).replace("", pd.NA).dropna().nunique())


def render_atlas_breakdown_chart(
    df: pd.DataFrame,
    column: str,
    title: str,
    split_values: bool = False,
) -> None:
    st.markdown(f"**{title}**")
    summary = atlas_category_summary(df, column, split_values=split_values)
    if summary.empty:
        st.info("No data available for this chart.")
        return

    st.bar_chart(summary.set_index("Category"), y="Rows")
    st.dataframe(
        summary,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Category": st.column_config.TextColumn(width="large"),
            "Rows": st.column_config.NumberColumn(width="small"),
            "Share": st.column_config.ProgressColumn(
                "Share",
                format="%.0f%%",
                min_value=0,
                max_value=100,
                width="medium",
            ),
        },
    )


def render_financial_evidence_level_tab(atlas_df: pd.DataFrame, level: dict[str, str]) -> None:
    level_df = atlas_rows_for_level(atlas_df, level["key"])
    st.markdown(
        f"""
        <div class="atlas-method-card">
            <span class="hub-chip neutral">Evidence category</span>
            <b>{hub_escape(level["title"])}</b>
            <p>{hub_escape(level["definition"])}</p>
            <div class="atlas-rule">{hub_escape(level["safe_use"])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if level_df.empty:
        st.info("No financial evidence rows are tagged to this category yet.")
        return

    metric_cols = st.columns(4)
    metric_cols[0].metric("Rows", f"{len(level_df):,}")
    metric_cols[1].metric("Sectors", f"{atlas_unique_count(level_df, 'impact_domain'):,}")
    metric_cols[2].metric("IOOS regions", f"{atlas_unique_count(level_df, 'ioos_region_code', split_values=True):,}")
    metric_cols[3].metric("Sources", f"{atlas_unique_count(level_df, 'source_id'):,}")

    chart_left, chart_right = st.columns(2)
    with chart_left:
        render_atlas_breakdown_chart(level_df, "impact_domain", "Rows by sector")
        render_atlas_breakdown_chart(level_df, "evidence_strength", "Rows by evidence strength")
        render_atlas_breakdown_chart(level_df, "atlas_claim_boundary", "Rows by claim boundary")
    with chart_right:
        render_atlas_breakdown_chart(level_df, "ioos_region_code", "Rows by IOOS region", split_values=True)
        render_atlas_breakdown_chart(level_df, "economic_number_type", "Rows by economic number type")
        render_atlas_breakdown_chart(level_df, "ioos_attribution_strength", "Rows by IOOS attribution")

    st.subheader("Rows Behind This Category")
    display_columns = [
        "row_id",
        "impact_domain",
        "ioos_region_code",
        "evidence_strength",
        "ioos_attribution_strength",
        "economic_number_type",
        "atlas_claim_boundary",
        "metric",
        "claim_allowed",
        "source_name",
        "source_url",
        "limitations",
    ]
    st.dataframe(
        level_df[[column for column in display_columns if column in level_df.columns]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "atlas_claim_boundary": st.column_config.TextColumn("Claim boundary", width="medium"),
            "metric": st.column_config.TextColumn(width="large"),
            "claim_allowed": st.column_config.TextColumn("Claim allowed", width="large"),
            "source_url": st.column_config.LinkColumn("Source URL"),
            "limitations": st.column_config.TextColumn(width="large"),
        },
    )
    st.download_button(
        f"Download {level['label']} CSV",
        level_df.to_csv(index=False).encode("utf-8"),
        file_name=f"ioos_financial_evidence_{level['key']}.csv",
        mime="text/csv",
        key=f"download_{level['key']}_financial_evidence_csv",
    )


def atlas_filtered_by_levels(atlas_df: pd.DataFrame, selected_keys: list[str]) -> pd.DataFrame:
    if not selected_keys or atlas_df.empty or "atlas_level_keys" not in atlas_df.columns:
        return atlas_df
    selected = set(selected_keys)
    return atlas_df[
        atlas_df["atlas_level_keys"].map(
            lambda value: bool(selected.intersection(split_semicolon_values(value)))
        )
    ].copy()


def atlas_option_values(df: pd.DataFrame, column: str) -> list[str]:
    if df.empty or column not in df.columns:
        return []
    return sorted(value for value in df[column].dropna().unique() if normalize_text(value))


def best_source_atlas_use(row: pd.Series) -> str:
    verification_needed = row_field(row, "source_verification_needed")
    key_metrics = row_field(row, "key_metrics")
    if verification_needed.lower() == "yes":
        prefix = "Verify before use"
    else:
        prefix = "Source-ready"
    if has_dollar_signal(key_metrics):
        return f"{prefix}; contains reported dollar metrics"
    if atlas_text_matches(key_metrics, ATLAS_ECONOMIC_ACTIVITY_PATTERNS):
        return f"{prefix}; economic activity context"
    return f"{prefix}; qualitative or operational source"


def normalize_maracoos_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize dedicated MARACOOS rows into the app's evidence-style columns."""
    if df.empty:
        return pd.DataFrame()

    normalized = df.copy()
    for source_column, target_column in MARACOOS_COLUMN_ALIASES.items():
        if source_column not in normalized.columns:
            continue
        if target_column not in normalized.columns:
            normalized[target_column] = normalized[source_column]
        elif source_column != target_column:
            blank_target = normalized[target_column].map(normalize_text) == ""
            normalized.loc[blank_target, target_column] = normalized.loc[blank_target, source_column]

    return normalized.fillna("").astype(str)


def maracoos_region_mask(df: pd.DataFrame) -> pd.Series:
    """Find rows tagged as MARACOOS in either region-code or text columns."""
    if df.empty:
        return pd.Series(False, index=df.index)

    mask = pd.Series(False, index=df.index)
    if "ioos_region_code" in df.columns:
        mask = mask | df["ioos_region_code"].apply(lambda value: MARACOOS_CODE in split_ioos_region_codes(value))

    text_columns = [
        column
        for column in [
            "region",
            "ioos_component",
            "impact_domain",
            "source",
            "source_id",
            "ai_extraction_notes",
        ]
        if column in df.columns
    ]
    for column in text_columns:
        mask = mask | df[column].map(lambda value: MARACOOS_CODE.lower() in normalize_text(value).lower())
    return mask


def maracoos_rows_from_loaded_tables(evidence_df: pd.DataFrame, staged_df: pd.DataFrame) -> pd.DataFrame:
    """Build a MARACOOS fallback view from loaded evidence and staged rows."""
    frames: list[pd.DataFrame] = []
    for origin, source_df in [("staged_evidence", staged_df), ("evidence_matrix", evidence_df)]:
        normalized = normalize_maracoos_dataframe(source_df)
        if normalized.empty:
            continue
        filtered = normalized[maracoos_region_mask(normalized)].copy()
        if filtered.empty:
            continue
        filtered["data_origin"] = origin
        frames.append(filtered)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True, sort=False).fillna("").astype(str)
    dedupe_columns = [
        column
        for column in ["row_id", "source", "source_id", "source_url", "metric", "claim_allowed"]
        if column in combined.columns
    ]
    if dedupe_columns:
        combined = combined.drop_duplicates(subset=dedupe_columns, keep="first")
    return combined


def sort_maracoos_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    sorted_df = df.copy()
    if "source_verification_needed" in sorted_df.columns:
        sorted_df["_verification_rank"] = sorted_df["source_verification_needed"].map(
            lambda value: 0 if normalize_text(value) == "No" else 1
        )
    else:
        sorted_df["_verification_rank"] = 1

    for column, temp_column in [
        ("evidence_strength", "_evidence_rank"),
        ("ioos_attribution_strength", "_attribution_rank"),
    ]:
        if column in sorted_df.columns:
            sorted_df[temp_column] = sorted_df[column].map(
                lambda value: MARACOOS_STRENGTH_RANK.get(normalize_text(value), 99)
            )
        else:
            sorted_df[temp_column] = 99

    sort_columns = ["_verification_rank", "_evidence_rank", "_attribution_rank"]
    for column in ["impact_domain", "row_id"]:
        if column in sorted_df.columns:
            sort_columns.append(column)

    return sorted_df.sort_values(sort_columns).drop(
        columns=["_verification_rank", "_evidence_rank", "_attribution_rank"],
        errors="ignore",
    )


def maracoos_briefing_data(
    evidence_df: pd.DataFrame,
    staged_df: pd.DataFrame,
) -> tuple[pd.DataFrame, str, str]:
    """Load MARACOOS briefing rows, preferring a dedicated Supabase table."""
    dedicated_df, table_name, errors = load_optional_supabase_table(MARACOOS_SUPABASE_TABLES)
    if table_name and not dedicated_df.empty:
        normalized = normalize_maracoos_dataframe(dedicated_df)
        normalized["data_origin"] = f"supabase:{table_name}"
        return sort_maracoos_rows(normalized), f"Supabase `{table_name}`", ""

    fallback_df = maracoos_rows_from_loaded_tables(evidence_df, staged_df)
    source_label = (
        "Supabase evidence/staging rows tagged MARACOOS"
        if supabase_enabled()
        else "local evidence/staging rows tagged MARACOOS"
    )

    note = ""
    if table_name and dedicated_df.empty:
        note = f"Supabase `{table_name}` returned no rows, so this tab is showing rows tagged MARACOOS."
    elif errors and supabase_enabled():
        note = "A dedicated Supabase MARACOOS table was not readable, so this tab is showing rows tagged MARACOOS."

    return sort_maracoos_rows(fallback_df), source_label, note


def first_row_value(row: pd.Series, columns: list[str]) -> str:
    for column in columns:
        value = normalize_text(row.get(column))
        if value:
            return value
    return ""


def count_distinct_row_values(df: pd.DataFrame, columns: list[str]) -> int:
    values: set[str] = set()
    for _, row in df.iterrows():
        value = first_row_value(row, columns)
        if value:
            values.add(value)
    return len(values)


def combined_row_text(row: pd.Series, columns: list[str]) -> str:
    return " ".join(normalize_text(row.get(column)).lower() for column in columns if column in row.index)


def maracoos_row_matches(row: pd.Series, keywords: list[str]) -> bool:
    haystack = combined_row_text(
        row,
        [
            "impact_domain",
            "ioos_component",
            "region",
            "user_group",
            "decision_supported",
            "economic_pathway",
            "metric",
            "claim_allowed",
            "ai_extraction_notes",
        ],
    )
    return any(keyword.lower() in haystack for keyword in keywords)


def select_maracoos_brief_row(
    df: pd.DataFrame,
    keywords: list[str],
    used_indexes: set[object],
) -> pd.Series | None:
    if df.empty:
        return None

    candidates = df[df.apply(lambda row: maracoos_row_matches(row, keywords), axis=1)].copy()
    if candidates.empty:
        candidates = df.copy()
    candidates = candidates[~candidates.index.isin(used_indexes)]
    if candidates.empty:
        return None

    with_claim = candidates[candidates.get("claim_allowed", pd.Series("", index=candidates.index)).map(normalize_text) != ""]
    if not with_claim.empty:
        candidates = with_claim

    sorted_candidates = sort_maracoos_rows(candidates)
    row = sorted_candidates.iloc[0]
    used_indexes.add(row.name)
    return row


def maracoos_brief_item(row: pd.Series | None, fallback_title: str, fallback_body: str) -> dict[str, str]:
    if row is None:
        return {
            "title": fallback_title,
            "claim": fallback_body,
            "metric": "",
            "source": "",
            "caveat": "",
        }

    title = first_row_value(row, ["impact_domain", "ioos_component"]) or fallback_title
    return {
        "title": title,
        "claim": first_row_value(row, ["claim_allowed", "decision_supported"]) or fallback_body,
        "metric": normalize_text(row.get("metric")),
        "source": first_row_value(row, ["source", "source_id"]),
        "caveat": normalize_text(row.get("limitations")),
    }


def build_maracoos_congressional_briefing_html(
    maracoos_df: pd.DataFrame,
    prepared_for: str,
    prepared_date: date,
) -> str:
    """Build a congressional-style regional brief using only MARACOOS rows."""
    prepared_for = normalize_text(prepared_for) or "Congressional Staff"
    date_label = prepared_date.strftime("%B %#d, %Y") if os.name == "nt" else prepared_date.strftime("%B %-d, %Y")
    source_count = count_distinct_row_values(maracoos_df, ["source", "source_id", "source_url"])
    verified_count = (
        int((maracoos_df["source_verification_needed"].map(normalize_text) == "No").sum())
        if "source_verification_needed" in maracoos_df.columns
        else 0
    )
    strong_attribution_count = (
        int((maracoos_df["ioos_attribution_strength"].map(normalize_text) == "Strong").sum())
        if "ioos_attribution_strength" in maracoos_df.columns
        else 0
    )

    used_indexes: set[object] = set()
    disaster = maracoos_brief_item(
        select_maracoos_brief_row(
            maracoos_df,
            ["search", "rescue", "sarops", "hf radar", "hfr", "flood", "storm", "hazard", "resilience", "rip", "beach"],
            used_indexes,
        ),
        "Disaster Response",
        "MARACOOS rows describe Mid-Atlantic ocean information that supports emergency response, coastal hazard, or maritime safety decisions.",
    )
    ports = maracoos_brief_item(
        select_maracoos_brief_row(maracoos_df, ["port", "ports", "navigation", "shipping", "commerce"], used_indexes),
        "Port and Navigation Decisions",
        "MARACOOS rows describe ocean and coastal information used for navigation or port decision support.",
    )
    communities = maracoos_brief_item(
        select_maracoos_brief_row(
            maracoos_df,
            ["hab", "shellfish", "fish", "water quality", "oxygen", "acidification", "sturgeon", "coastal", "community"],
            used_indexes,
        ),
        "Coastal Communities",
        "MARACOOS rows describe environmental information that supports coastal community, fisheries, shellfish, or water-quality decisions.",
    )
    additional = maracoos_brief_item(
        select_maracoos_brief_row(maracoos_df, ["maracoos"], used_indexes),
        "Additional MARACOOS Evidence",
        "Additional MARACOOS rows can support regional follow-up with staff.",
    )
    items = [disaster, ports, communities, additional]

    ucar_logo_uri = asset_data_uri(UCAR_LOGO_PATH, "image/avif")
    col_logo_uri = asset_data_uri(COL_LOGO_PATH, "image/avif")
    hero_image_uri = asset_data_uri(IOOS_HERO_IMAGE_PATH, "image/png")
    maracoos_map_uri = asset_data_uri(MARACOOS_COVERAGE_MAP_PATH, "image/png")
    flow_chart_uri = asset_data_uri(DATA_TO_DECISION_FLOW_PATH, "image/png")

    pillar_items = [
        (
            "1. Disaster Response",
            disaster,
            "During major storms, IOOS-supported information helps ports and vessel operators make pre-storm decisions.",
        ),
        (
            "2. Port Efficiency",
            ports,
            "Real-time water level, current, and air-gap observations support safer navigation in high-value port and shipping corridors.",
        ),
        (
            "3. Coastal Communities",
            communities,
            "Regional ocean data improves coastal hazard awareness for emergency managers and communities.",
        ),
    ]
    item_cards = "\n".join(
        f"""
    <div class="pillar">
      <h3>{brief_escape(title)}</h3>
      <p class="action"><b>Placeholder action statement:</b> {brief_escape(action)}</p>
      <p><b>Placeholder evidence slot:</b> {brief_escape(item['claim'])}</p>
      <p><b>Placeholder metric slot:</b> {brief_escape(item['metric'] or "Qualitative MARACOOS evidence row")}</p>
      <p><b>Placeholder source slot:</b> {brief_escape(item['source'] or "MARACOOS evidence row")}</p>
    </div>"""
        for title, item, action in pillar_items
    )
    caveat_cards = "\n".join(
        f"""
    <div class="caveat">
      <h3>{brief_escape(item['title'])}</h3>
      <p>{brief_escape(item['caveat'] or "Placeholder caveat slot; verify before external distribution.")}</p>
    </div>"""
        for item in items
    )
    metric_strip = "\n".join(
        f"""    <div class="metric"><div class="value">{brief_escape(card['value'])}</div><div class="label">{brief_escape(card['label'])}</div></div>"""
        for card in congressional_brief_metric_cards(maracoos_df, pd.DataFrame())
    )
    state_relevance = "\n".join(
        f"""      <div><b>{brief_escape(state)}:</b> {brief_escape(relevance)}</div>"""
        for state, relevance in MID_ATLANTIC_STATE_RELEVANCE
    )
    funding_protect_items = "\n".join(
        f"""          <li>{brief_escape(item)}</li>"""
        for item in FEDERAL_FUNDING_PROTECTS
    )
    funding_risk_items = "\n".join(
        f"""          <li>{brief_escape(item)}</li>"""
        for item in FEDERAL_FUNDING_RISKS
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  :root {{
    --teal: #00A3B4;
    --teal-dark: #007785;
    --blue: #4A94B1;
    --gold: #F2A93B;
    --ink: #222;
    --gray: #5E6A71;
    --line: #D7E1E5;
    --panel: #EFF7F8;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Helvetica Neue", Arial, sans-serif;
    color: var(--ink);
    background: #888;
    margin: 0;
    padding: 20px 0 56px;
  }}
  .page {{
    width: 8.5in;
    min-height: 11in;
    margin: 0 auto 28px;
    background: #fff;
    padding: 0.5in 0.62in;
    box-shadow: 0 4px 18px rgba(0,0,0,0.25);
    font-size: 10.2pt;
    line-height: 1.32;
  }}
  .masthead {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 3px solid var(--teal);
    padding-bottom: 9px;
    margin-bottom: 12px;
  }}
  .logos {{ display: flex; align-items: center; gap: 18px; }}
  .logos img.logo-ucar {{ height: 26px; width: auto; }}
  .logos img.logo-col {{ height: 46px; width: auto; }}
  .logos .divider {{ width: 1px; height: 36px; background: var(--line); }}
  .doc-label {{
    text-align: right;
    font-size: 8.5pt;
    color: var(--gray);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}
  .hero {{
    background:
      linear-gradient(90deg, rgba(0, 48, 63, 0.86) 0%, rgba(0, 88, 104, 0.64) 34%, rgba(0, 119, 133, 0.22) 60%, rgba(0, 119, 133, 0.04) 82%),
      url("{hero_image_uri}") center 45%/100% auto no-repeat;
    color: #fff;
    min-height: 2.08in;
    padding: 14px 16px;
    border-radius: 3px;
    margin-bottom: 10px;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    overflow: hidden;
  }}
  .hero .kicker,
  .hero h1,
  .hero .subtitle {{
    max-width: 4.35in;
    text-shadow: 0 1.5px 4px rgba(0, 0, 0, 0.64);
  }}
  .hero .kicker {{
    font-size: 8.5pt;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #DFF6F9;
    margin-bottom: 5px;
    font-weight: 700;
  }}
  .hero h1 {{ font-size: 24pt; line-height: 1.05; margin: 0 0 5px; }}
  .hero .subtitle {{ font-size: 10.4pt; margin: 0 0 6px; color: #F2FCFD; }}
  .brief-meta {{
    display: flex;
    justify-content: space-between;
    color: var(--gray);
    font-size: 8.8pt;
    margin: -3px 0 10px;
  }}
  .metric-strip {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin: 10px 0 12px;
  }}
  .metric {{
    border: 1px solid var(--line);
    border-top: 4px solid var(--gold);
    padding: 8px 9px;
    min-height: 58px;
  }}
  .metric .value {{ color: var(--teal-dark); font-weight: 800; font-size: 16.5pt; line-height: 1.06; overflow-wrap: anywhere; }}
  .metric .label {{ color: var(--gray); font-size: 8.5pt; margin-top: 4px; }}
  h2.section {{
    font-size: 10.8pt;
    color: var(--teal-dark);
    border-bottom: 1.5px solid var(--teal);
    padding-bottom: 3px;
    margin: 12px 0 7px;
    font-weight: 800;
    letter-spacing: 0.02em;
    text-transform: uppercase;
  }}
  p {{ margin: 0 0 8px; }}
  .bottom-line {{
    background: var(--panel);
    border-left: 5px solid var(--teal);
    padding: 10px 13px;
    margin: 8px 0 12px;
    font-weight: 700;
    font-size: 11.2pt;
  }}
  .top-statement {{
    background: var(--panel);
    border-left: 5px solid var(--teal);
    padding: 10px 13px;
    margin: 8px 0 10px;
    font-weight: 700;
    font-size: 11.2pt;
  }}
  .placeholder-note {{
    border: 1px solid var(--gold);
    background: #FFF8EB;
    color: #4F3A12;
    padding: 7px 10px;
    margin: 6px 0 9px;
    font-size: 8.9pt;
    font-weight: 700;
  }}
  .pillars {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-top: 8px;
  }}
  .pillar {{
    border: 1px solid var(--line);
    border-left: 4px solid var(--blue);
    padding: 8px 9px;
    min-height: 185px;
  }}
  .pillar h3, .caveat h3 {{
    margin: 0 0 5px;
    color: var(--teal-dark);
    font-size: 10.2pt;
  }}
  .pillar p, .caveat p {{ font-size: 9.1pt; margin-bottom: 6px; }}
  .pillar .action {{ font-weight: 700; }}
  .two-col {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin: 8px 0 12px;
  }}
  .map-row {{
    grid-template-columns: 1.06fr 0.94fr;
    gap: 12px;
    align-items: start;
  }}
  .visual-card {{
    border: 1px solid var(--line);
    padding: 7px;
    background: #fff;
  }}
  .visual-card img {{
    display: block;
    width: 100%;
    height: auto;
    max-height: 1.75in;
    object-fit: contain;
  }}
  .visual-card .caption {{
    color: var(--gray);
    font-size: 7.8pt;
    margin: 5px 0 0;
    line-height: 1.2;
  }}
  .two-col ul {{
    margin: 0;
    padding-left: 16px;
  }}
  .state-box, .funding-box {{
    border: 1px solid var(--line);
    border-left: 4px solid var(--gold);
    padding: 8px 10px;
    margin: 8px 0 10px;
    background: #fff;
  }}
  .state-box h3, .funding-panel h3 {{
    margin: 0 0 5px;
    color: var(--teal-dark);
    font-size: 10pt;
  }}
  .state-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 5px 12px;
    font-size: 8.7pt;
    line-height: 1.25;
  }}
  .funding-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin: 6px 0 9px;
  }}
  .funding-panel {{
    border: 1px solid var(--line);
    padding: 8px 9px;
    background: #fff;
  }}
  .compact-list {{
    margin: 0;
    padding-left: 16px;
    font-size: 8.7pt;
    line-height: 1.25;
  }}
  .caveat-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }}
  .caveat {{
    border: 1px solid var(--line);
    padding: 8px 9px;
  }}
  .flow-visual {{
    margin: 6px 0 10px;
  }}
  .flow-visual img {{
    display: block;
    width: 100%;
    max-height: 3.05in;
    object-fit: contain;
    border: 1px solid var(--line);
    background: #fff;
  }}
  .flow-visual .caption {{
    color: var(--gray);
    font-size: 7.8pt;
    line-height: 1.2;
    margin: 4px 0 0;
  }}
  .ask-box {{
    background: var(--teal-dark);
    color: #fff;
    padding: 13px 15px;
    border-radius: 3px;
    margin-top: 12px;
    font-weight: 700;
  }}
  .ask-box .label {{
    color: #DFF6F9;
    font-size: 9pt;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 5px;
  }}
  .footnote {{ font-size: 8.1pt; color: var(--gray); font-style: italic; margin-top: 10px; }}
  .footer {{
    border-top: 1px solid var(--line);
    margin-top: 14px;
    padding-top: 7px;
    display: flex;
    justify-content: space-between;
    font-size: 8.2pt;
    color: var(--gray);
  }}
</style>
</head>
<body>
<div class="page">
  <div class="masthead">
    <div class="logos">
      <img class="logo-ucar" src="{ucar_logo_uri}" alt="UCAR">
      <div class="divider"></div>
      <img class="logo-col" src="{col_logo_uri}" alt="Center for Ocean Leadership">
    </div>
    <div class="doc-label">MARACOOS Brief</div>
  </div>

  <div class="hero">
    <div class="kicker">IOOS Reauthorization Brief</div>
    <h1>MARACOOS: Mid-Atlantic Ocean Intelligence</h1>
    <p class="subtitle">The regional case for reauthorizing the Integrated Ocean Observing System (IOOS)</p>
  </div>
  <div class="brief-meta">
    <span>Prepared for: {brief_escape(prepared_for)}</span>
    <span>{brief_escape(date_label)}</span>
  </div>

  <div class="placeholder-note">{brief_escape(PLACEHOLDER_BRIEF_NOTICE)}</div>
  <div class="top-statement">Draft top statement: {brief_escape(MARACOOS_TOP_STATEMENT)}</div>

  <div class="metric-strip">
{metric_strip}
  </div>

  <h2 class="section">What IOOS Is</h2>
  <div class="two-col map-row">
    <div>
      <p>IOOS is the United States&rsquo; national network of ocean sensors, buoys, radar systems, satellites, and data platforms. MARACOOS is the Mid-Atlantic regional association that translates that infrastructure into usable regional information.</p>
      <p>For a congressional audience, MARACOOS is the regional proof point: Mid-Atlantic observations, products, and partner systems connected to decisions in coastal communities, ports, and offshore waters.</p>
    </div>
    <div class="visual-card">
      <img src="{maracoos_map_uri}" alt="MARACOOS coverage map">
      <p class="caption">MARACOOS coverage map, used here to localize the IOOS value story for the Mid-Atlantic.</p>
    </div>
  </div>

  <div class="state-box">
    <h3>Why this matters for Mid-Atlantic states - placeholder relevance map</h3>
    <div class="state-grid">
{state_relevance}
    </div>
  </div>

  <h2 class="section">Why It Matters: Three MARACOOS Examples</h2>
  <div class="pillars">
{item_cards}
  </div>
</div>

<div class="page">
  <div class="masthead">
    <div class="logos">
      <img class="logo-ucar" src="{ucar_logo_uri}" alt="UCAR">
      <div class="divider"></div>
      <img class="logo-col" src="{col_logo_uri}" alt="Center for Ocean Leadership">
    </div>
    <div class="doc-label">MARACOOS Brief</div>
  </div>

  <h2 class="section" style="margin-top:0;">The Economy MARACOOS Serves</h2>
  <p>MARACOOS is regional data infrastructure for the Mid-Atlantic ocean economy and coastal safety mission. The rows above point to the decision contexts where that infrastructure is most visible.</p>
  <div class="flow-visual">
    <img src="{flow_chart_uri}" alt="Data to decision flow chart">
    <p class="caption">Data-to-decision pathway: observations and forecasts become regional products, then operational decisions and economic relevance.</p>
  </div>

  <h2 class="section">The Legislative Moment</h2>
  <p>Use MARACOOS as the regional example inside the broader IOOS reauthorization conversation. The national brief makes the overall funding case; this brief shows what the same infrastructure looks like in the Mid-Atlantic evidence rows.</p>
  <p>Legislative status, bill numbers, authorization levels, and appropriations language are placeholder slots in this draft and must be verified immediately before external use.</p>
  <p>This preview is currently wired to {len(maracoos_df):,} MARACOOS rows and {source_count:,} represented source slots. Treat row-specific caveats, counts, source labels, and example language as draft placeholders until reviewed.</p>

  <h2 class="section">What Federal Funding Protects</h2>
  <p><b>Draft funding-to-outcome connection:</b> {brief_escape(FUNDING_TO_OUTCOME_STATEMENT)}</p>
  <div class="funding-grid">
    <div class="funding-panel">
      <h3>Placeholder: federal funding protects</h3>
      <ul class="compact-list">
{funding_protect_items}
      </ul>
    </div>
    <div class="funding-panel">
      <h3>Placeholder: what is at risk if funding is flat or reduced</h3>
      <p>{brief_escape(FLAT_OR_REDUCED_FUNDING_RISK)}</p>
      <ul class="compact-list">
{funding_risk_items}
      </ul>
    </div>
  </div>

  <h2 class="section">Staff Takeaway</h2>
  <p><b>Do not make this complicated:</b> MARACOOS is the Mid-Atlantic version of the IOOS story. Its value is clearest when staff can see specific regional decisions supported by ocean observations, forecasts, web tools, and partner systems.</p>
  <p>This brief mirrors the main congressional brief structure, but its evidence examples are drawn only from the MARACOOS rows displayed above.</p>

  <h2 class="section">Caveats Staff Should Keep With The Claims</h2>
  <div class="caveat-grid">
{caveat_cards}
  </div>

  <div class="ask-box">
    <div class="label">The Ask</div>
    Support floor action on IOOS reauthorization &nbsp; | &nbsp; Defend IOOS funding in CJS appropriations at or above current levels &nbsp; | &nbsp; Request a MARACOOS-specific briefing on how IOOS serves Mid-Atlantic coastal, port, fisheries, or emergency management stakeholders.
  </div>

  <div class="footnote">Source note: Draft placeholder only. The metric strip, examples, caveats, source counts, legislative references, and regional relevance statements are not verification findings and should not be used externally until reviewed against source records.</div>

  <div class="footer">
    <span>IOOS Economic Impact Evidence Matrix | MARACOOS regional placeholder brief</span>
    <span>Source slots: {source_count} | Row slots: {len(maracoos_df)}</span>
  </div>
</div>
</body>
</html>"""


def filter_maracoos_briefing_rows(df: pd.DataFrame) -> pd.DataFrame:
    search_text = st.text_input("Search MARACOOS rows", key="maracoos_brief_search")
    filtered = search_dataframe(df, search_text)

    filter_columns = [
        ("impact_domain", "Impact Domain"),
        ("evidence_strength", "Evidence Strength"),
        ("ioos_attribution_strength", "Attribution Strength"),
        ("source_verification_needed", "Verification Needed"),
    ]
    filter_layout = st.columns(len(filter_columns))
    for container, (column, label) in zip(filter_layout, filter_columns):
        if column not in filtered.columns:
            continue
        options = sorted(value for value in filtered[column].dropna().unique() if normalize_text(value))
        selected = container.multiselect(label, options, key=f"maracoos_brief_{column}")
        if selected:
            filtered = filtered[filtered[column].isin(selected)]

    return filtered


def render_maracoos_congressional_tab(
    evidence_df: pd.DataFrame,
    staged_df: pd.DataFrame,
    prepared_for: str,
    prepared_date: date,
) -> None:
    maracoos_df, source_label, note = maracoos_briefing_data(evidence_df, staged_df)

    st.subheader("MARACOOS Congressional Brief")
    st.caption(f"Data source: {source_label}")
    if note:
        st.info(note)

    if maracoos_df.empty:
        st.warning("No MARACOOS rows are available for this briefing tab.")
        return

    source_count = count_distinct_row_values(maracoos_df, ["source", "source_id", "source_url"])
    verified_count = (
        int((maracoos_df["source_verification_needed"].map(normalize_text) == "No").sum())
        if "source_verification_needed" in maracoos_df.columns
        else 0
    )
    strong_or_medium_count = (
        int(maracoos_df["evidence_strength"].map(normalize_text).isin({"Strong", "Medium"}).sum())
        if "evidence_strength" in maracoos_df.columns
        else 0
    )
    strong_attribution_count = (
        int((maracoos_df["ioos_attribution_strength"].map(normalize_text) == "Strong").sum())
        if "ioos_attribution_strength" in maracoos_df.columns
        else 0
    )

    metric_columns = st.columns(4)
    metric_columns[0].metric("MARACOOS rows", f"{len(maracoos_df):,}")
    metric_columns[1].metric("Sources", f"{source_count:,}")
    metric_columns[2].metric("Strong/medium evidence", f"{strong_or_medium_count:,}")
    metric_columns[3].metric("Strong attribution", f"{strong_attribution_count:,}")

    st.write(
        "Use this tab as the Mid-Atlantic briefing workspace: it pulls MARACOOS-tagged evidence "
        "into one place, highlights cautious claim language, and keeps caveats visible for staff review."
    )

    summary_col, claims_col = st.columns([0.9, 1.1])
    with summary_col:
        st.subheader("Briefing Focus")
        if "impact_domain" in maracoos_df.columns:
            domain_summary = count_summary(maracoos_df, "impact_domain")
            st.dataframe(
                domain_summary,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Rows": st.column_config.NumberColumn(format="%d", width="small"),
                    "Share": st.column_config.ProgressColumn(
                        "Share",
                        format="%.0f%%",
                        min_value=0,
                        max_value=100,
                    ),
                },
            )
        else:
            st.info("No impact-domain column is available.")

        if verified_count == 0:
            st.warning("All rows still need source verification before external use.")

    with claims_col:
        st.subheader("Cautious Claims")
        if "claim_allowed" not in maracoos_df.columns:
            st.info("No claim_allowed column is available.")
        else:
            claim_rows = maracoos_df[maracoos_df["claim_allowed"].map(normalize_text) != ""].head(5)
            if claim_rows.empty:
                st.info("No usable claim language is available yet.")
            for _, row in claim_rows.iterrows():
                label = first_row_value(row, ["impact_domain", "row_id"]) or "MARACOOS row"
                st.markdown(f"**{label}**")
                st.write(normalize_text(row.get("claim_allowed")))
                details = []
                source_value = first_row_value(row, ["source", "source_id"])
                metric_value = normalize_text(row.get("metric"))
                if source_value:
                    details.append(source_value)
                if metric_value:
                    details.append(metric_value)
                if details:
                    st.caption(" | ".join(details))

    st.subheader("MARACOOS Rows")
    filtered = filter_maracoos_briefing_rows(maracoos_df)
    st.caption(f"Showing {len(filtered):,} of {len(maracoos_df):,} rows")

    display_columns = [column for column in MARACOOS_DISPLAY_COLUMNS if column in filtered.columns]
    remaining_columns = [column for column in filtered.columns if column not in display_columns]
    display_df = filtered[display_columns + remaining_columns]
    column_config = {}
    if "source_url" in display_df.columns:
        column_config["source_url"] = st.column_config.LinkColumn("Source URL")
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
    )
    st.download_button(
        "Download MARACOOS briefing rows",
        filtered.to_csv(index=False).encode("utf-8"),
        file_name="maracoos_congressional_briefing_rows.csv",
        mime="text/csv",
    )

    st.subheader("MARACOOS Briefing Preview")
    st.caption("Generated only from the MARACOOS evidence rows shown above.")
    if filtered.empty:
        st.info("No filtered MARACOOS rows are available for the briefing preview.")
        return

    maracoos_briefing_html = build_maracoos_congressional_briefing_html(
        filtered,
        prepared_for,
        prepared_date,
    )
    components.html(maracoos_briefing_html, height=1700, scrolling=True)
    st.download_button(
        "Download MARACOOS congressional brief HTML",
        maracoos_briefing_html.encode("utf-8"),
        file_name="maracoos_congressional_brief_live.html",
        mime="text/html",
    )


def congressional_briefing_context(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    prepared_for: str,
    prepared_date: date,
) -> dict[str, object]:
    """Collect the short text values used by both HTML and PDF brief exports."""
    rows = {
        row_id: evidence_row_by_id(evidence_df, row_id)
        for row_id in BRIEFING_ROW_IDS.values()
    }
    prepared_for = normalize_text(prepared_for) or "Congressional Staff"
    date_label = prepared_date.strftime("%B %#d, %Y") if os.name == "nt" else prepared_date.strftime("%B %-d, %Y")

    return {
        "prepared_for": prepared_for,
        "date_label": date_label,
        "evidence_count": len(evidence_df),
        "source_count": len(source_df),
        "ocean_enterprise_metric": row_field(
            rows[BRIEFING_ROW_IDS["ocean_enterprise"]],
            "metric",
            "Ocean Enterprise business, employment, revenue, and export metrics are tracked in the evidence matrix.",
        ),
        "tampa_metric": row_field(
            rows[BRIEFING_ROW_IDS["ports"]],
            "metric",
            "Tampa Bay PORTS case-study benefits are tracked in the matrix.",
        ),
        "hab_forecast_claim": row_field(
            rows[BRIEFING_ROW_IDS["habs"]],
            "claim_allowed",
            "HAB forecasts help managers focus testing and guide closure/advisory decisions.",
        ),
        "hf_radar_claim": row_field(
            rows[BRIEFING_ROW_IDS["hf_radar"]],
            "claim_allowed",
            "HF radar surface-current data support USCG search planning through SAROPS.",
        ),
    }


def congressional_brief_item(
    row: pd.Series | None,
    source_df: pd.DataFrame,
    fallback_title: str,
    fallback_body: str,
    fallback_metric: str = "",
    fallback_source: str = "",
    fallback_caveat: str = "",
) -> dict[str, str]:
    if row is None:
        return {
            "title": fallback_title,
            "claim": fallback_body,
            "metric": fallback_metric,
            "source": fallback_source,
            "caveat": fallback_caveat,
        }

    source_row = source_for_row(row, source_df)
    return {
        "title": row_field(row, "impact_domain", row_field(row, "ioos_component", fallback_title)),
        "claim": row_field(row, "claim_allowed", row_field(row, "decision_supported", fallback_body)),
        "metric": row_field(row, "metric", fallback_metric),
        "source": row_field(source_row, "source_name", row_field(row, "source_id", fallback_source)),
        "caveat": row_field(row, "limitations", fallback_caveat),
    }


def congressional_brief_metric_cards(evidence_df: pd.DataFrame, benefit_sources_df: pd.DataFrame) -> list[dict[str, str]]:
    """Use the dashboard evidence-signal data for the brief's top metric strip."""
    verified_use_count, _ = decision_use_counts(evidence_df)
    benefit_count = quantified_benefit_study_count(benefit_sources_df, evidence_df)
    safety_value, safety_unit, _, _ = operational_safety_signal(evidence_df, benefit_sources_df)
    ocean_value, _ = ocean_enterprise_signal(benefit_sources_df, evidence_df)
    return [
        {
            "value": f"{verified_use_count:,}",
            "label": pluralized_label(verified_use_count, "placeholder decision-use slot"),
        },
        {
            "value": f"{benefit_count:,}",
            "label": pluralized_label(
                benefit_count,
                "placeholder benefit-study slot",
                "placeholder benefit-study slots",
            ),
        },
        {
            "value": safety_value,
            "label": f"placeholder {safety_unit}",
        },
        {
            "value": ocean_value,
            "label": "placeholder Ocean Enterprise slot",
        },
    ]


def build_congressional_briefing_html(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    prepared_for: str,
    prepared_date: date,
    benefit_sources_df: pd.DataFrame | None = None,
) -> str:
    """Build a two-page print-friendly congressional brief from the current matrix rows."""
    context = congressional_briefing_context(evidence_df, source_df, prepared_for, prepared_date)
    prepared_for = str(context["prepared_for"])
    date_label = str(context["date_label"])
    evidence_count = int(context["evidence_count"])
    source_count = int(context["source_count"])
    ocean_enterprise_metric = str(context["ocean_enterprise_metric"])

    rows = {
        key: evidence_row_by_id(evidence_df, row_id)
        for key, row_id in BRIEFING_ROW_IDS.items()
    }
    disaster = congressional_brief_item(
        rows["hf_radar"],
        source_df,
        "Disaster Response",
        "IOOS real-time coastal and surface-current data support emergency response, search planning, storm decisions, and maritime safety operations.",
        "HF radar and emergency-response evidence is tracked in the matrix.",
        "IOOS evidence matrix",
        "Retain row-specific limitations before treating emergency-response examples as quantified dollar claims.",
    )
    ports = congressional_brief_item(
        rows["ports"],
        source_df,
        "Port and Navigation Decisions",
        "IOOS water-level and current data helps port pilots optimize vessel drafts, reduce delays, and minimize costly lightering operations.",
        "PORTS benefit evidence is tracked in the matrix.",
        "IOOS evidence matrix",
        "Keep port examples tied to the geography and operating assumptions in the underlying source.",
    )
    communities = congressional_brief_item(
        rows["habs"],
        source_df,
        "Coastal Communities",
        "IOOS powers HAB early-warning systems, supports fisheries decisions, and feeds coastal water-quality and public-health decision support.",
        "HAB and coastal community evidence is tracked in the matrix.",
        "IOOS evidence matrix",
        "Do not overstate avoided costs where the source supports decision support rather than a hard-dollar return.",
    )
    economy = congressional_brief_item(
        rows["ocean_enterprise"],
        source_df,
        "Ocean Enterprise Context",
        "The Ocean Enterprise row frames the private-sector and employment context for IOOS-enabled ocean data services.",
        ocean_enterprise_metric,
        "IOOS evidence matrix",
        "Use Ocean Enterprise figures as sector context, not as a claim that IOOS directly caused all revenue or jobs.",
    )
    pillar_items = [
        (
            "1. Disaster Response",
            disaster,
            "During major storms, IOOS-supported information helps ports and vessel operators make pre-storm decisions.",
        ),
        (
            "2. Port Efficiency",
            ports,
            "Real-time water level, current, and air-gap observations support safer navigation in high-value port and shipping corridors.",
        ),
        (
            "3. Coastal Communities",
            communities,
            "Regional ocean data improves coastal hazard awareness for emergency managers and communities.",
        ),
    ]
    item_cards = "\n".join(
        f"""
    <div class="pillar">
      <h3>{brief_escape(title)}</h3>
      <p class="action"><b>Placeholder action statement:</b> {brief_escape(action)}</p>
      <p><b>Placeholder evidence slot:</b> {brief_escape(item['claim'])}</p>
      <p><b>Placeholder metric slot:</b> {brief_escape(item['metric'] or "Qualitative IOOS evidence row")}</p>
      <p><b>Placeholder source slot:</b> {brief_escape(item['source'] or "IOOS evidence matrix")}</p>
    </div>"""
        for title, item, action in pillar_items
    )
    caveat_cards = "\n".join(
        f"""
    <div class="caveat">
      <h3>{brief_escape(item['title'])}</h3>
      <p>{brief_escape(item['caveat'] or "Placeholder caveat slot; verify before external distribution.")}</p>
    </div>"""
        for item in [disaster, ports, communities, economy]
    )
    metric_source_df = benefit_sources_df if benefit_sources_df is not None else source_df
    metric_strip = "\n".join(
        f"""    <div class="metric"><div class="value">{brief_escape(card['value'])}</div><div class="label">{brief_escape(card['label'])}</div></div>"""
        for card in congressional_brief_metric_cards(evidence_df, metric_source_df)
    )

    ucar_logo_uri = asset_data_uri(UCAR_LOGO_PATH, "image/avif")
    col_logo_uri = asset_data_uri(COL_LOGO_PATH, "image/avif")
    hero_image_uri = asset_data_uri(IOOS_HERO_IMAGE_PATH, "image/png")
    ioos_map_uri = asset_data_uri(IOOS_COVERAGE_MAP_PATH, "image/png")
    flow_chart_uri = asset_data_uri(DATA_TO_DECISION_FLOW_PATH, "image/png")
    funding_protect_items = "\n".join(
        f"""          <li>{brief_escape(item)}</li>"""
        for item in FEDERAL_FUNDING_PROTECTS
    )
    funding_risk_items = "\n".join(
        f"""          <li>{brief_escape(item)}</li>"""
        for item in FEDERAL_FUNDING_RISKS
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  :root {{
    --teal: #00A3B4;
    --teal-dark: #007785;
    --blue: #4A94B1;
    --gold: #F2A93B;
    --ink: #222;
    --gray: #5E6A71;
    --line: #D7E1E5;
    --panel: #EFF7F8;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Helvetica Neue", Arial, sans-serif;
    color: var(--ink);
    background: #888;
    margin: 0;
    padding: 20px 0 56px;
  }}
  .page {{
    width: 8.5in;
    min-height: 11in;
    margin: 0 auto 28px;
    background: #fff;
    padding: 0.5in 0.62in;
    box-shadow: 0 4px 18px rgba(0,0,0,0.25);
    font-size: 10.2pt;
    line-height: 1.32;
  }}
  .masthead {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 3px solid var(--teal);
    padding-bottom: 9px;
    margin-bottom: 12px;
  }}
  .logos {{ display: flex; align-items: center; gap: 18px; }}
  .logos img.logo-ucar {{ height: 26px; width: auto; }}
  .logos img.logo-col {{ height: 46px; width: auto; }}
  .logos .divider {{ width: 1px; height: 36px; background: var(--line); }}
  .doc-label {{
    text-align: right;
    font-size: 8.5pt;
    color: var(--gray);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}
  .hero {{
    background:
      linear-gradient(90deg, rgba(0, 48, 63, 0.86) 0%, rgba(0, 88, 104, 0.64) 34%, rgba(0, 119, 133, 0.22) 60%, rgba(0, 119, 133, 0.04) 82%),
      url("{hero_image_uri}") center 45%/100% auto no-repeat;
    color: #fff;
    min-height: 2.08in;
    padding: 14px 16px;
    border-radius: 3px;
    margin-bottom: 10px;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    overflow: hidden;
  }}
  .hero .kicker,
  .hero h1,
  .hero .subtitle {{
    max-width: 4.35in;
    text-shadow: 0 1.5px 4px rgba(0, 0, 0, 0.64);
  }}
  .hero .kicker {{
    font-size: 8.5pt;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #DFF6F9;
    margin-bottom: 5px;
    font-weight: 700;
  }}
  .hero h1 {{ font-size: 24pt; line-height: 1.05; margin: 0 0 5px; }}
  .hero .subtitle {{ font-size: 10.4pt; margin: 0 0 6px; color: #F2FCFD; }}
  .brief-meta {{
    display: flex;
    justify-content: space-between;
    color: var(--gray);
    font-size: 8.8pt;
    margin: -3px 0 10px;
  }}
  .metric-strip {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin: 10px 0 12px;
  }}
  .metric {{
    border: 1px solid var(--line);
    border-top: 4px solid var(--gold);
    padding: 8px 9px;
    min-height: 58px;
  }}
  .metric .value {{ color: var(--teal-dark); font-weight: 800; font-size: 16.5pt; line-height: 1.06; overflow-wrap: anywhere; }}
  .metric .label {{ color: var(--gray); font-size: 8.5pt; margin-top: 4px; }}
  h2.section {{
    font-size: 10.8pt;
    color: var(--teal-dark);
    border-bottom: 1.5px solid var(--teal);
    padding-bottom: 3px;
    margin: 12px 0 7px;
    font-weight: 800;
    letter-spacing: 0.02em;
    text-transform: uppercase;
  }}
  p {{ margin: 0 0 8px; }}
  .bottom-line {{
    background: var(--panel);
    border-left: 5px solid var(--teal);
    padding: 10px 13px;
    margin: 8px 0 12px;
    font-weight: 700;
    font-size: 11.2pt;
  }}
  .top-statement {{
    background: var(--panel);
    border-left: 5px solid var(--teal);
    padding: 10px 13px;
    margin: 8px 0 10px;
    font-weight: 700;
    font-size: 11.2pt;
  }}
  .placeholder-note {{
    border: 1px solid var(--gold);
    background: #FFF8EB;
    color: #4F3A12;
    padding: 7px 10px;
    margin: 6px 0 9px;
    font-size: 8.9pt;
    font-weight: 700;
  }}
  .pillars {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-top: 8px;
  }}
  .pillar {{
    border: 1px solid var(--line);
    border-left: 4px solid var(--blue);
    padding: 8px 9px;
    min-height: 185px;
  }}
  .pillar h3, .caveat h3 {{
    margin: 0 0 5px;
    color: var(--teal-dark);
    font-size: 10.2pt;
  }}
  .pillar p, .caveat p {{ font-size: 9.1pt; margin-bottom: 6px; }}
  .pillar .action {{ font-weight: 700; }}
  .highlight {{ color: var(--teal-dark); font-weight: 800; }}
  .two-col {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin: 8px 0 12px;
  }}
  .map-row {{
    grid-template-columns: 1.06fr 0.94fr;
    gap: 12px;
    align-items: start;
  }}
  .visual-card {{
    border: 1px solid var(--line);
    padding: 7px;
    background: #fff;
  }}
  .visual-card img {{
    display: block;
    width: 100%;
    height: auto;
    max-height: 1.75in;
    object-fit: contain;
  }}
  .visual-card .caption {{
    color: var(--gray);
    font-size: 7.8pt;
    margin: 5px 0 0;
    line-height: 1.2;
  }}
  .funding-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin: 6px 0 9px;
  }}
  .funding-panel {{
    border: 1px solid var(--line);
    padding: 8px 9px;
    background: #fff;
  }}
  .funding-panel h3 {{
    margin: 0 0 5px;
    color: var(--teal-dark);
    font-size: 10pt;
  }}
  .compact-list {{
    margin: 0;
    padding-left: 16px;
    font-size: 8.7pt;
    line-height: 1.25;
  }}
  .caveat-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }}
  .caveat {{
    border: 1px solid var(--line);
    padding: 8px 9px;
  }}
  .flow-visual {{
    margin: 6px 0 10px;
  }}
  .flow-visual img {{
    display: block;
    width: 100%;
    max-height: 3.05in;
    object-fit: contain;
    border: 1px solid var(--line);
    background: #fff;
  }}
  .flow-visual .caption {{
    color: var(--gray);
    font-size: 7.8pt;
    line-height: 1.2;
    margin: 4px 0 0;
  }}
  .ask-box {{
    background: var(--teal-dark);
    color: #fff;
    padding: 13px 15px;
    border-radius: 3px;
    margin-top: 12px;
    font-weight: 700;
  }}
  .ask-box .label {{
    color: #DFF6F9;
    font-size: 9pt;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 5px;
  }}
  .footnote {{ font-size: 8.1pt; color: var(--gray); font-style: italic; margin-top: 10px; }}
  .footer {{
    border-top: 1px solid var(--line);
    margin-top: 14px;
    padding-top: 7px;
    display: flex;
    justify-content: space-between;
    font-size: 8.2pt;
    color: var(--gray);
  }}
</style>
</head>
<body>
<div class="page">
  <div class="masthead">
    <div class="logos">
      <img class="logo-ucar" src="{ucar_logo_uri}" alt="UCAR">
      <div class="divider"></div>
      <img class="logo-col" src="{col_logo_uri}" alt="Center for Ocean Leadership">
    </div>
    <div class="doc-label">Congressional Brief</div>
  </div>

  <div class="hero">
    <div class="kicker">IOOS Reauthorization Brief</div>
    <h1>America&rsquo;s Ocean Intelligence System</h1>
    <p class="subtitle">The case for reauthorizing the Integrated Ocean Observing System (IOOS)</p>
  </div>
  <div class="brief-meta">
    <span>Prepared for: {brief_escape(prepared_for)}</span>
    <span>{brief_escape(date_label)}</span>
  </div>

  <div class="placeholder-note">{brief_escape(PLACEHOLDER_BRIEF_NOTICE)}</div>
  <div class="top-statement">Draft top statement: {brief_escape(IOOS_TOP_STATEMENT)}</div>

  <div class="metric-strip">
{metric_strip}
  </div>

  <div class="bottom-line">Draft funding-to-outcome connection: {brief_escape(FUNDING_TO_OUTCOME_STATEMENT)}</div>

  <h2 class="section">What IOOS Is</h2>
  <div class="two-col map-row">
    <div>
      <p><b>Draft framing:</b> IOOS can be described as the United States&rsquo; national network of ocean sensors, buoys, radar systems, satellites, and data platforms for coastal, Great Lakes, and ocean information.</p>
      <p><b>Placeholder analogy:</b> Think of it as the interstate highway system for ocean data: a federal investment that can enable private-sector activity, operational decisions, and public safety outcomes through shared data infrastructure.</p>
    </div>
    <div class="visual-card">
      <img src="{ioos_map_uri}" alt="IOOS regional coverage map">
      <p class="caption">IOOS regional coverage, used here to localize the national value story across U.S. coastal and Great Lakes regions.</p>
    </div>
  </div>

  <h2 class="section">Why It Matters: Three Things Only IOOS Can Do</h2>
  <div class="pillars">
{item_cards}
  </div>
</div>

<div class="page">
  <div class="masthead">
    <div class="logos">
      <img class="logo-ucar" src="{ucar_logo_uri}" alt="UCAR">
      <div class="divider"></div>
      <img class="logo-col" src="{col_logo_uri}" alt="Center for Ocean Leadership">
    </div>
    <div class="doc-label">Congressional Brief</div>
  </div>

  <h2 class="section" style="margin-top:0;">The Economy IOOS Enables</h2>
  <p><b>Placeholder economy framing:</b> IOOS can be positioned as public data infrastructure for ocean economy users, including commercial shipping, offshore energy, recreational boating, coastal tourism, and seafood.</p>
  <p><b>Placeholder sector context slot:</b> <span class="highlight">{brief_escape(ocean_enterprise_metric)}</span>. Do not treat this as verified or as a claim that IOOS directly caused revenue or jobs.</p>
  <div class="flow-visual">
    <img src="{flow_chart_uri}" alt="Data to decision flow chart">
    <p class="caption">Data-to-decision pathway: observations and forecasts become regional products, then operational decisions and economic relevance.</p>
  </div>

  <h2 class="section">The Legislative Moment</h2>
  <p>Legislative status, bill numbers, authorization levels, and appropriations language are placeholder slots in this draft and must be verified immediately before external use.</p>
  <p>This section should hold the current reauthorization and appropriations frame after review, but this preview does not certify those facts.</p>

  <h2 class="section">What Federal Funding Protects</h2>
  <p><b>Draft funding-to-outcome connection:</b> {brief_escape(FUNDING_TO_OUTCOME_STATEMENT)}</p>
  <div class="funding-grid">
    <div class="funding-panel">
      <h3>Placeholder: federal funding protects</h3>
      <ul class="compact-list">
{funding_protect_items}
      </ul>
    </div>
    <div class="funding-panel">
      <h3>Placeholder: what is at risk if funding is flat or reduced</h3>
      <p>{brief_escape(FLAT_OR_REDUCED_FUNDING_RISK)}</p>
      <ul class="compact-list">
{funding_risk_items}
      </ul>
    </div>
  </div>

  <h2 class="section">Staff Takeaway</h2>
  <p><b>Draft takeaway:</b> IOOS can be framed as a modest federal investment serving coastal states, ports, emergency managers, scientists, and ocean businesses. The policy choice can be framed around whether to keep that infrastructure stable.</p>
  <p>This brief mirrors the MARACOOS brief structure, but its examples are placeholder slots drawn from national IOOS briefing rows in the current matrix.</p>

  <h2 class="section">Caveats Staff Should Keep With The Claims</h2>
  <div class="caveat-grid">
{caveat_cards}
  </div>

  <div class="ask-box">
    <div class="label">The Ask</div>
    Placeholder ask: Support floor action on IOOS reauthorization &nbsp; | &nbsp; Defend IOOS funding in CJS appropriations at or above current levels &nbsp; | &nbsp; Request a district-specific briefing on how IOOS serves coastal, port, fisheries, or emergency management stakeholders.
  </div>

  <div class="footnote">Source note: Draft placeholder only. The metric strip, examples, caveats, source counts, legislative references, and national framing statements are not verification findings and should not be used externally until reviewed against source records.</div>

  <div class="footer">
    <span>IOOS Economic Impact Evidence Matrix | national placeholder brief</span>
    <span>Source slots: {source_count} | Row slots: {evidence_count}</span>
  </div>
</div>
</body>
</html>"""


def pdf_markup(value: object) -> str:
    """Escape text for ReportLab paragraphs and normalize glyphs for built-in fonts."""
    text = normalize_text(value)
    replacements = {
        "\u00ae": "(R)",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return html_lib.escape(text, quote=False)


def pdf_logo_image(path: Path, height: float):
    """Convert AVIF logos to PNG-backed ReportLab images."""
    from PIL import Image as PILImage
    from reportlab.platypus import Image as ReportLabImage

    try:
        with PILImage.open(path) as image:
            if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                white = PILImage.new("RGBA", rgba.size, "WHITE")
                white.alpha_composite(rgba)
                converted = white.convert("RGB")
            else:
                converted = image.convert("RGB")

            png_bytes = io.BytesIO()
            converted.save(png_bytes, format="PNG")
            png_bytes.seek(0)
            width = height * (converted.width / converted.height)
            return ReportLabImage(png_bytes, width=width, height=height)
    except Exception:
        return None


def build_congressional_briefing_pdf(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    prepared_for: str,
    prepared_date: date,
    benefit_sources_df: pd.DataFrame | None = None,
) -> bytes:
    """Build a two-page PDF version of the congressional brief."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    context = congressional_briefing_context(evidence_df, source_df, prepared_for, prepared_date)
    metric_source_df = benefit_sources_df if benefit_sources_df is not None else source_df
    content_width = 7.26 * inch
    teal = colors.HexColor("#00A3B4")
    teal_dark = colors.HexColor("#007785")
    blue = colors.HexColor("#4A94B1")
    gold = colors.HexColor("#F2A93B")
    gray = colors.HexColor("#5E6A71")
    line = colors.HexColor("#D7E1E5")
    panel = colors.HexColor("#EFF7F8")

    styles = {
        "doc_label": ParagraphStyle(
            "DocLabel",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            textColor=gray,
            alignment=TA_RIGHT,
            uppercase=True,
        ),
        "hero_kicker": ParagraphStyle(
            "HeroKicker",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            textColor=colors.HexColor("#DFF6F9"),
            spaceAfter=3,
        ),
        "hero_h1": ParagraphStyle(
            "HeroH1",
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=24,
            textColor=colors.white,
            spaceAfter=3,
        ),
        "hero_subtitle": ParagraphStyle(
            "HeroSubtitle",
            fontName="Helvetica",
            fontSize=11,
            leading=13,
            textColor=colors.HexColor("#F2FCFD"),
        ),
        "meta": ParagraphStyle(
            "Meta",
            fontName="Helvetica",
            fontSize=8.8,
            leading=10.5,
            textColor=gray,
        ),
        "metric_value": ParagraphStyle(
            "MetricValue",
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=16,
            textColor=teal_dark,
            alignment=TA_CENTER,
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel",
            fontName="Helvetica",
            fontSize=8.4,
            leading=10,
            textColor=gray,
            alignment=TA_CENTER,
        ),
        "body": ParagraphStyle(
            "Body",
            fontName="Helvetica",
            fontSize=9.8,
            leading=12.4,
            textColor=colors.HexColor("#222222"),
            spaceAfter=6,
        ),
        "body_small": ParagraphStyle(
            "BodySmall",
            fontName="Helvetica",
            fontSize=8.7,
            leading=10.8,
            textColor=colors.HexColor("#222222"),
            spaceAfter=5,
        ),
        "section": ParagraphStyle(
            "Section",
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=12,
            textColor=teal_dark,
            spaceBefore=8,
            spaceAfter=2,
        ),
        "bottom_line": ParagraphStyle(
            "BottomLine",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=13.5,
            textColor=colors.HexColor("#222222"),
        ),
        "placeholder_note": ParagraphStyle(
            "PlaceholderNote",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10.5,
            textColor=colors.HexColor("#4F3A12"),
        ),
        "pillar_heading": ParagraphStyle(
            "PillarHeading",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            textColor=teal_dark,
            spaceAfter=4,
        ),
        "ask_label": ParagraphStyle(
            "AskLabel",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            textColor=colors.HexColor("#DFF6F9"),
            spaceAfter=4,
        ),
        "ask": ParagraphStyle(
            "Ask",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12.5,
            textColor=colors.white,
        ),
        "footnote": ParagraphStyle(
            "Footnote",
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=9.6,
            textColor=gray,
        ),
        "footer": ParagraphStyle(
            "Footer",
            fontName="Helvetica",
            fontSize=8,
            leading=9.5,
            textColor=gray,
        ),
    }

    def paragraph(text: object, style_name: str) -> Paragraph:
        return Paragraph(pdf_markup(text), styles[style_name])

    def rich_paragraph(markup: str, style_name: str) -> Paragraph:
        return Paragraph(markup, styles[style_name])

    def masthead() -> list[object]:
        ucar_logo = pdf_logo_image(UCAR_LOGO_PATH, 24)
        col_logo = pdf_logo_image(COL_LOGO_PATH, 44)
        logo_cells = []
        if ucar_logo is not None:
            logo_cells.append(ucar_logo)
        else:
            logo_cells.append(paragraph("UCAR", "body_small"))
        logo_cells.append("")
        if col_logo is not None:
            logo_cells.append(col_logo)
        else:
            logo_cells.append(paragraph("Center for Ocean Leadership", "body_small"))

        logo_table = Table([logo_cells], colWidths=[96, 14, 64])
        logo_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LINEBEFORE", (2, 0), (2, 0), 1, line),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        head = Table(
            [[logo_table, paragraph("CONGRESSIONAL BRIEF", "doc_label")]],
            colWidths=[content_width - 150, 150],
        )
        head.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return [
            head,
            HRFlowable(width="100%", thickness=3, color=teal, spaceBefore=0, spaceAfter=9),
        ]

    def section(title: str) -> list[object]:
        return [
            paragraph(title.upper(), "section"),
            HRFlowable(width="100%", thickness=1.2, color=teal, spaceBefore=0, spaceAfter=5),
        ]

    story: list[object] = []
    story.extend(masthead())

    hero = Table(
        [
            [
                [
                    rich_paragraph("IOOS REAUTHORIZATION BRIEF", "hero_kicker"),
                    rich_paragraph("America's Ocean Intelligence System", "hero_h1"),
                    rich_paragraph(
                        "The case for reauthorizing the Integrated Ocean Observing System (IOOS)",
                        "hero_subtitle",
                    ),
                ]
            ]
        ],
        colWidths=[content_width],
    )
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), teal),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.extend([hero, Spacer(1, 7)])

    meta = Table(
        [
            [
                paragraph(f"Prepared for: {context['prepared_for']}", "meta"),
                Paragraph(pdf_markup(context["date_label"]), styles["meta"].clone("MetaRight", alignment=TA_RIGHT)),
            ]
        ],
        colWidths=[content_width / 2, content_width / 2],
    )
    meta.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.extend([meta, Spacer(1, 7)])

    placeholder_note = Table(
        [[paragraph(PLACEHOLDER_BRIEF_NOTICE, "placeholder_note")]],
        colWidths=[content_width],
    )
    placeholder_note.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF8EB")),
                ("BOX", (0, 0), (-1, -1), 0.7, gold),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    top_statement = Table(
        [[paragraph(f"Draft top statement: {IOOS_TOP_STATEMENT}", "bottom_line")]],
        colWidths=[content_width],
    )
    top_statement.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), panel),
                ("LINEBEFORE", (0, 0), (0, 0), 5, teal),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([placeholder_note, Spacer(1, 6), top_statement, Spacer(1, 7)])

    metric_cells = []
    for card in congressional_brief_metric_cards(evidence_df, metric_source_df):
        metric_cells.append(
            [
                rich_paragraph(pdf_markup(card["value"]), "metric_value"),
                paragraph(card["label"], "metric_label"),
            ]
        )

    metric_table = Table([metric_cells], colWidths=[content_width / 4] * 4)
    metric_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, line),
                ("INNERGRID", (0, 0), (-1, -1), 0.7, line),
                ("LINEABOVE", (0, 0), (-1, -1), 3, gold),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([metric_table, Spacer(1, 8)])

    bottom_line = Table(
        [[paragraph(f"Draft funding-to-outcome connection: {FUNDING_TO_OUTCOME_STATEMENT}", "bottom_line")]],
        colWidths=[content_width],
    )
    bottom_line.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), panel),
                ("LINEBEFORE", (0, 0), (0, 0), 5, teal),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([bottom_line, Spacer(1, 3)])

    story.extend(section("What IOOS Is"))
    story.append(paragraph("Draft framing: IOOS can be described as the United States' national network of ocean sensors, buoys, radar systems, satellites, and data platforms for coastal, Great Lakes, and ocean information.", "body"))
    story.append(rich_paragraph("Placeholder analogy: Think of it as the <b>interstate highway system for ocean data</b>: a federal investment that can enable private-sector activity, operational decisions, and public safety outcomes through shared data infrastructure.", "body"))

    story.extend(section("Why It Matters: Three Things Only IOOS Can Do"))
    pillar_cells = [
        [
            rich_paragraph("1. Disaster Response", "pillar_heading"),
            rich_paragraph("<b>Placeholder action statement:</b> During major storms, IOOS-supported information helps ports and vessel operators make pre-storm decisions.", "body_small"),
            rich_paragraph("<b>Placeholder evidence slot:</b> Add reviewed storm, port, or vessel decision example here before external use.", "body_small"),
        ],
        [
            rich_paragraph("2. Port Efficiency", "pillar_heading"),
            rich_paragraph("<b>Placeholder action statement:</b> Real-time water level, current, and air-gap observations support safer navigation in high-value port and shipping corridors.", "body_small"),
            rich_paragraph(f"<b>Placeholder metric slot:</b> {pdf_markup(context['tampa_metric'])}.", "body_small"),
        ],
        [
            rich_paragraph("3. Coastal Communities", "pillar_heading"),
            rich_paragraph("<b>Placeholder action statement:</b> Regional ocean data improves coastal hazard awareness for emergency managers and communities.", "body_small"),
            rich_paragraph(f"<b>Placeholder evidence slot:</b> {pdf_markup(context['hab_forecast_claim'])} {pdf_markup(context['hf_radar_claim'])}", "body_small"),
        ],
    ]
    pillars = Table([pillar_cells], colWidths=[content_width / 3] * 3)
    pillars.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, line),
                ("INNERGRID", (0, 0), (-1, -1), 0.7, line),
                ("LINEBEFORE", (0, 0), (-1, -1), 3, blue),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([pillars, PageBreak()])

    story.extend(masthead())
    story.extend(section("The Economy IOOS Enables"))
    story.append(paragraph("Placeholder economy framing: IOOS can be positioned as public data infrastructure for ocean economy users, including commercial shipping, offshore energy, recreational boating, coastal tourism, and seafood.", "body"))
    story.append(rich_paragraph(f"<b>Placeholder sector context slot:</b> <font color='#007785'>{pdf_markup(context['ocean_enterprise_metric'])}</font>. Do not treat this as verified or as a claim that IOOS directly caused revenue or jobs.", "body"))

    sector_rows = [
        ["Commercial shipping and port operations", "Offshore energy development"],
        ["Recreational boating and coastal tourism", "Commercial and recreational fisheries"],
        ["Coastal hazard and emergency management", "U.S. Navy and Coast Guard operations"],
        ["Marine technology industry", "Shellfish and aquaculture businesses"],
    ]
    sector_table = Table(
        [[paragraph(left, "body_small"), paragraph(right, "body_small")] for left, right in sector_rows],
        colWidths=[content_width / 2, content_width / 2],
    )
    sector_table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.6, line),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.extend([sector_table, Spacer(1, 6)])

    story.extend(section("The Legislative Moment"))
    story.append(paragraph("Legislative status, bill numbers, authorization levels, and appropriations language are placeholder slots in this draft and must be verified immediately before external use.", "body"))
    story.append(paragraph("This section should hold the current reauthorization and appropriations frame after review, but this preview does not certify those facts.", "body"))

    story.extend(section("What Federal Funding Protects"))
    story.append(rich_paragraph(f"<b>Draft funding-to-outcome connection:</b> {pdf_markup(FUNDING_TO_OUTCOME_STATEMENT)}", "body"))
    funding_rows = [
        [
            rich_paragraph("<b>Placeholder: federal funding protects</b><br/>" + "<br/>".join(f"- {pdf_markup(item)}" for item in FEDERAL_FUNDING_PROTECTS[:4]), "body_small"),
            rich_paragraph("<b>Placeholder: what is at risk if funding is flat or reduced</b><br/>" + pdf_markup(FLAT_OR_REDUCED_FUNDING_RISK), "body_small"),
        ]
    ]
    funding_table = Table(funding_rows, colWidths=[content_width / 2, content_width / 2])
    funding_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, line),
                ("INNERGRID", (0, 0), (-1, -1), 0.7, line),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([funding_table, Spacer(1, 6)])

    story.extend(section("Staff Takeaway"))
    story.append(rich_paragraph("<b>Draft takeaway:</b> IOOS can be framed as a modest federal investment serving coastal states, ports, emergency managers, scientists, and ocean businesses. The policy choice can be framed around whether to keep that infrastructure stable.", "body"))

    ask_box = Table(
        [
            [
                [
                    rich_paragraph("THE ASK", "ask_label"),
                    paragraph(
                        "Placeholder ask: Support floor action on IOOS reauthorization | Defend IOOS funding in CJS appropriations at or above current levels | Request a district-specific briefing on how IOOS serves coastal, port, fisheries, or emergency management stakeholders.",
                        "ask",
                    ),
                ]
            ]
        ],
        colWidths=[content_width],
    )
    ask_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), teal_dark),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.extend([ask_box, Spacer(1, 10)])
    story.append(paragraph("Source note: Draft placeholder only. The metric strip, examples, caveats, source counts, legislative references, and national framing statements are not verification findings and should not be used externally until reviewed against source records.", "footnote"))
    story.extend([Spacer(1, 10), HRFlowable(width="100%", thickness=0.7, color=line, spaceBefore=0, spaceAfter=5)])
    footer = Table(
        [
            [
                paragraph("IOOS Economic Impact Evidence Matrix | national placeholder brief", "footer"),
                Paragraph(
                    pdf_markup(f"Source slots: {context['source_count']} | Row slots: {context['evidence_count']}"),
                    styles["footer"].clone("FooterRight", alignment=TA_RIGHT),
                ),
            ]
        ],
        colWidths=[content_width * 0.65, content_width * 0.35],
    )
    footer.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(footer)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.62 * inch,
        rightMargin=0.62 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    doc.build(story)
    return buffer.getvalue()


def row_warning_map(review_df: pd.DataFrame) -> dict[str, dict[str, object]]:
    """Group validator issues by evidence row_id for dashboard-only rollups."""
    if review_df.empty or "row_id" not in review_df.columns:
        return {}

    warning_map: dict[str, dict[str, object]] = {}
    for _, issue in review_df.iterrows():
        row_id = normalize_text(issue.get("row_id"))
        if not row_id:
            continue
        entry = warning_map.setdefault(
            row_id,
            {"checks": set(), "errors": 0, "warnings": 0, "messages": []},
        )
        severity = normalize_text(issue.get("severity")).lower()
        check = normalize_text(issue.get("check"))
        message = normalize_text(issue.get("message"))
        if check:
            entry["checks"].add(check)
        if message:
            entry["messages"].append(message)
        if severity == "error":
            entry["errors"] += 1
        elif severity == "warning":
            entry["warnings"] += 1
    return warning_map


def has_unclear_limitations(value: object) -> bool:
    """Flag limitations that are blank or too vague to support report drafting."""
    text = normalize_text(value).lower()
    return text in {"", "none", "n/a", "na", "not applicable", "unknown", "unclear", "tbd"}


def has_causal_language(value: object) -> bool:
    text = normalize_text(value)
    return any(re.search(pattern, text, re.I) for pattern in CAUSAL_TERMS)


def has_conservative_claim_language(row: pd.Series, checks: set[str]) -> bool:
    """Return True when claim text is cautious enough for shortlist review."""
    claim = normalize_text(row.get("claim_allowed"))
    if not claim:
        return False
    if "unsupported_causal_language" in checks:
        return False
    if not has_causal_language(claim):
        return True
    return any(re.search(pattern, claim, re.I) for pattern in CONSERVATIVE_CLAIM_TERMS)


def infer_report_status(row: pd.Series, checks: set[str], errors: int) -> str:
    """Infer report-readiness when the matrix has no explicit status column."""
    evidence = normalize_text(row.get("evidence_strength"))
    attribution = normalize_text(row.get("ioos_attribution_strength"))
    verification_needed = normalize_text(row.get("source_verification_needed")) == "Yes"
    claim_missing = not normalize_text(row.get("claim_allowed"))
    limitations_unclear = has_unclear_limitations(row.get("limitations"))

    if (
        errors
        or verification_needed
        or evidence == "Needs verification"
        or attribution == "Needs verification"
        or "source_verification_needed" in checks
        or "quantified_metric_needs_verification" in checks
        or "unsupported_causal_language" in checks
        or claim_missing
        or limitations_unclear
    ):
        return "needs-follow-up"

    if evidence == "Contextual" or attribution == "Contextual":
        return "background-only"

    if (
        evidence in {"Strong", "Medium"}
        and attribution in {"Strong", "Medium"}
        and not checks
    ):
        return "report-ready"

    return "use-with-caution"


def add_dashboard_fields(evidence_df: pd.DataFrame, review_df: pd.DataFrame) -> pd.DataFrame:
    """Add derived fields used only for dashboard display and filtering."""
    if evidence_df.empty:
        return evidence_df.copy()

    enriched = evidence_df.copy()
    warnings_by_row = row_warning_map(review_df)
    status_column = next((column for column in enriched.columns if column.lower() == "status"), None)

    statuses: list[str] = []
    warning_counts: list[int] = []
    error_counts: list[int] = []
    warning_checks: list[str] = []

    for _, row in enriched.iterrows():
        row_id = normalize_text(row.get("row_id"))
        issues = warnings_by_row.get(row_id, {})
        checks = set(issues.get("checks", set()))
        errors = int(issues.get("errors", 0))
        warnings = int(issues.get("warnings", 0))

        if status_column:
            status = normalize_text(row.get(status_column)) or "Unspecified"
        else:
            status = infer_report_status(row, checks, errors)

        statuses.append(status)
        warning_counts.append(warnings)
        error_counts.append(errors)
        warning_checks.append("; ".join(sorted(checks)))

    enriched["dashboard_status"] = statuses
    enriched["validation_warning_count"] = warning_counts
    enriched["validation_error_count"] = error_counts
    enriched["validation_warning_types"] = warning_checks
    return enriched


def display_verification_flag_mask(
    df: pd.DataFrame,
    column: str = "source_verification_needed",
    display_value: str = APP_DISPLAY_SOURCE_VERIFICATION_NEEDED_VALUE,
) -> pd.Series:
    """Return rows matching the app-level source_verification_needed display rule."""
    if df.empty:
        return pd.Series(dtype=bool)
    if column not in df.columns:
        return pd.Series(False, index=df.index)
    return df[column].map(normalize_text).str.lower().eq(display_value.lower())


def staged_rows_for_evidence_display(staged_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize staged_evidence rows into the evidence-style dataframe used by public pages."""
    if staged_df.empty:
        return pd.DataFrame()

    normalized = normalize_intake_df(staged_df)
    rows: list[dict[str, str]] = []
    for _, row in normalized.iterrows():
        source_name = normalize_text(row.get("Source"))
        rows.append(
            {
                "row_id": normalize_text(row.get("row_id")),
                "date_record_created": normalize_text(row.get("Date record created")),
                "impact_domain": normalize_text(row.get("Impact domain")),
                "ioos_component": normalize_text(row.get("IOOS component")),
                "region": normalize_text(row.get("Region")),
                "ioos_region_code": normalize_text(row.get("IOOS region code")),
                "user_group": normalize_text(row.get("User group")),
                "decision_supported": normalize_text(row.get("Decision supported")),
                "economic_pathway": normalize_text(row.get("Economic pathway")),
                "metric": normalize_text(row.get("Metric")),
                "metric_year_or_dollar_year": normalize_text(row.get("Metric year / dollar year")),
                "source_id": source_name,
                "source_name": source_name,
                "source_url": normalize_text(row.get("Source URL")),
                "source_type": "staged evidence source",
                "source_verification_status": f"source_verification_needed={normalize_text(row.get('Source verification needed'))}",
                "evidence_strength": normalize_text(row.get("Evidence strength")),
                "ioos_attribution_strength": normalize_text(row.get("IOOS attribution strength")),
                "economic_number_type": normalize_text(row.get("Economic number type")),
                "ioos_role_type": normalize_text(row.get("IOOS role type")),
                "source_verification_needed": normalize_text(row.get("Source verification needed")),
                "allowed_use": normalize_text(row.get("Allowed use")),
                "not_allowed_use": normalize_text(row.get("Not allowed use")),
                "limitations": normalize_text(row.get("Limitations")),
                "claim_allowed": normalize_text(row.get("Claim allowed")),
                "update_frequency": normalize_text(row.get("Update frequency")),
                "ai_extraction_notes": normalize_text(row.get("AI extraction notes")),
                "data_origin": "staged_evidence",
            }
        )
    return pd.DataFrame(rows).fillna("")


def source_registry_from_two_table_model(staged_display_df: pd.DataFrame, best_sources_df: pd.DataFrame) -> pd.DataFrame:
    """Build source-like records from staged evidence and best_sources for display joins/counts."""
    records: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for _, row in staged_display_df.iterrows():
        source_name = normalize_text(row.get("source_name"))
        source_url = normalize_text(row.get("source_url"))
        if not source_name and not source_url:
            continue
        key = (source_name.lower(), source_url.lower())
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "source_id": source_name or source_url,
                "source_name": source_name or "Source pending",
                "source_url": source_url,
                "source_type": normalize_text(row.get("source_type")) or "staged evidence source",
                "verification_status": normalize_text(row.get("source_verification_status")),
                "rows_supported": normalize_text(row.get("row_id")),
                "notes": normalize_text(row.get("allowed_use")),
            }
        )

    if not best_sources_df.empty:
        for _, row in best_sources_df.iterrows():
            source_name = normalize_text(row.get("source_name"))
            source_url = normalize_text(row.get("source_url"))
            key = (source_name.lower(), source_url.lower())
            if not source_name and not source_url:
                continue
            if key in seen:
                continue
            seen.add(key)
            records.append(
                {
                    "source_id": normalize_text(row.get("source_id")) or source_name or source_url,
                    "source_name": source_name or "Source pending",
                    "source_url": source_url,
                    "source_type": normalize_text(row.get("source_type")),
                    "verification_status": f"source_verification_needed={normalize_text(row.get('source_verification_needed'))}",
                    "rows_supported": normalize_text(row.get("staged_row_ids")),
                    "notes": normalize_text(row.get("briefing_role")),
                }
            )

    return pd.DataFrame(records, columns=[
        "source_id",
        "source_name",
        "source_url",
        "source_type",
        "verification_status",
        "rows_supported",
        "notes",
    ]).fillna("")


def filter_review_to_rows(review_df: pd.DataFrame, row_ids: set[str]) -> pd.DataFrame:
    if review_df.empty or "row_id" not in review_df.columns:
        return review_df.head(0).copy()
    return review_df[review_df["row_id"].map(normalize_text).isin(row_ids)].copy()


def public_two_table_views(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    review_df: pd.DataFrame,
    staged_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build app-facing dataframes from the two retained Supabase tables."""
    staged_display = staged_rows_for_evidence_display(staged_df)
    public_evidence = staged_display[display_verification_flag_mask(staged_display)].copy()
    public_review = review_df.head(0).copy()
    public_staged = staged_df[display_verification_flag_mask(staged_df, "Source verification needed")].copy()
    public_best_sources = best_sources_df[display_verification_flag_mask(best_sources_df)].copy()
    public_sources = source_registry_from_two_table_model(public_evidence, public_best_sources)
    return public_evidence, public_sources, public_review, public_staged, public_best_sources


def status_counts_table(evidence_df: pd.DataFrame) -> pd.DataFrame:
    counts = evidence_df["dashboard_status"].value_counts().rename_axis("Status").reset_index(name="Rows")
    order = {status: index for index, status in enumerate(REPORT_STATUS_ORDER)}
    counts["_order"] = counts["Status"].map(lambda status: order.get(status, len(order)))
    return counts.sort_values(["_order", "Status"]).drop(columns="_order")


def render_status_cards(evidence_df: pd.DataFrame, source_df: pd.DataFrame, review_df: pd.DataFrame) -> None:
    status_counts = evidence_df["dashboard_status"].value_counts() if "dashboard_status" in evidence_df else {}
    unique_sources = evidence_df["source_id"].replace("", pd.NA).dropna().nunique() if "source_id" in evidence_df else len(source_df)
    errors = int((review_df["severity"].str.lower() == "error").sum()) if "severity" in review_df.columns else 0
    warnings = int((review_df["severity"].str.lower() == "warning").sum()) if "severity" in review_df.columns else 0

    cards = [
        ("Total evidence rows", len(evidence_df)),
        ("Unique sources", unique_sources),
        ("Report-ready rows", int(status_counts.get("report-ready", 0))),
        ("Use-with-caution rows", int(status_counts.get("use-with-caution", 0))),
        ("Background-only rows", int(status_counts.get("background-only", 0))),
        ("Needs-follow-up rows", int(status_counts.get("needs-follow-up", 0))),
        ("Validation errors", errors),
        ("Validation warnings", warnings),
    ]

    for row_start in range(0, len(cards), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, cards[row_start : row_start + 4]):
            column.metric(label, f"{value:,}")


def render_report_readiness_breakdown(evidence_df: pd.DataFrame) -> None:
    st.subheader("Report-Readiness Breakdown")
    if evidence_df.empty:
        st.info("No evidence rows available.")
        return

    counts = status_counts_table(evidence_df)
    chart_data = counts.set_index("Status")
    st.bar_chart(chart_data, y="Rows")
    st.dataframe(counts, use_container_width=True, hide_index=True)


def render_strength_crosstab(evidence_df: pd.DataFrame) -> None:
    st.subheader("Evidence Strength x IOOS Attribution Strength")
    required = {"evidence_strength", "ioos_attribution_strength"}
    if evidence_df.empty or not required.issubset(evidence_df.columns):
        st.info("Evidence and attribution strength columns are required for this table.")
        return

    crosstab = pd.crosstab(
        evidence_df["evidence_strength"].replace("", "Blank"),
        evidence_df["ioos_attribution_strength"].replace("", "Blank"),
        margins=True,
        margins_name="Total",
    )
    crosstab.index.name = "Evidence strength"
    st.dataframe(crosstab, use_container_width=True)


def domain_notes(domain_df: pd.DataFrame) -> str:
    notes: list[str] = []
    warning_count = int(domain_df["validation_warning_count"].sum()) if "validation_warning_count" in domain_df else 0
    if warning_count:
        notes.append("Warnings present")
    if "source_verification_needed" in domain_df and (domain_df["source_verification_needed"] == "Yes").any():
        notes.append("Source verification needed")
    if "ioos_attribution_strength" in domain_df and domain_df["ioos_attribution_strength"].isin(["Contextual", "Needs verification"]).any():
        notes.append("Weak or unverified attribution")
    if "evidence_strength" in domain_df and domain_df["evidence_strength"].isin(["Contextual", "Modeled", "Needs verification"]).any():
        notes.append("Contextual, modeled, or unverified evidence")
    return "; ".join(notes) if notes else "No current flags"


def render_domain_coverage(evidence_df: pd.DataFrame) -> None:
    st.subheader("Domain Coverage")
    if evidence_df.empty or "impact_domain" not in evidence_df.columns:
        st.info("No impact domain data available.")
        return

    rows: list[dict[str, object]] = []
    for domain, domain_df in evidence_df.groupby("impact_domain", dropna=False):
        rows.append(
            {
                "Impact domain": domain or "Blank",
                "total rows": len(domain_df),
                "strong evidence rows": int((domain_df["evidence_strength"] == "Strong").sum()) if "evidence_strength" in domain_df else 0,
                "strong IOOS attribution rows": int((domain_df["ioos_attribution_strength"] == "Strong").sum()) if "ioos_attribution_strength" in domain_df else 0,
                "report-ready rows": int((domain_df["dashboard_status"] == "report-ready").sum()),
                "warnings": int(domain_df["validation_warning_count"].sum()) if "validation_warning_count" in domain_df else 0,
                "notes": domain_notes(domain_df),
            }
        )

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_review_workload(review_df: pd.DataFrame) -> None:
    st.subheader("Review Workload by Warning Type")
    if review_df.empty:
        st.success("No review workload is currently listed.")
        return
    if "check" not in review_df.columns:
        st.info("review_needed.csv does not include a check column.")
        return

    grouped = (
        review_df.assign(
            severity=review_df.get("severity", "").replace("", "unspecified"),
            row_id=review_df.get("row_id", "").astype(str),
        )
        .groupby(["check", "severity"], dropna=False)
        .agg(
            items=("check", "size"),
            affected_rows=("row_id", lambda values: ", ".join(sorted({value for value in values if value}))),
        )
        .reset_index()
        .sort_values(["severity", "items", "check"], ascending=[True, False, True])
    )
    st.dataframe(grouped, use_container_width=True, hide_index=True)


def display_columns(df: pd.DataFrame) -> list[str]:
    preferred = [
        "row_id",
        "dashboard_status",
        "impact_domain",
        "ioos_component",
        "region",
        "ioos_region_code",
        "metric",
        "evidence_strength",
        "ioos_attribution_strength",
        "source_verification_needed",
        "claim_allowed",
        "limitations",
        "validation_warning_types",
    ]
    return [column for column in preferred if column in df.columns]


def render_best_candidates(evidence_df: pd.DataFrame) -> None:
    st.subheader("Best Candidate Rows for Final Report")
    if evidence_df.empty:
        st.info("No evidence rows available.")
        return

    mask = evidence_df["dashboard_status"] == "report-ready"
    for index, row in evidence_df.iterrows():
        checks = set(filter(None, normalize_text(row.get("validation_warning_types")).split("; ")))
        strong_or_medium = (
            normalize_text(row.get("evidence_strength")) in {"Strong", "Medium"}
            and normalize_text(row.get("ioos_attribution_strength")) in {"Strong", "Medium"}
        )
        if strong_or_medium and has_conservative_claim_language(row, checks):
            mask.loc[index] = True

    candidates = evidence_df[mask].copy()
    if candidates.empty:
        st.info("No rows currently meet the candidate criteria.")
        return
    st.dataframe(candidates[display_columns(candidates)], use_container_width=True, hide_index=True)


def follow_up_reasons(row: pd.Series) -> str:
    reasons: list[str] = []
    checks = set(filter(None, normalize_text(row.get("validation_warning_types")).split("; ")))
    attribution = normalize_text(row.get("ioos_attribution_strength"))

    if normalize_text(row.get("source_verification_needed")) == "Yes" or "source_verification_needed" in checks:
        reasons.append("source verification")
    if attribution in {"Contextual", "Needs verification"} or "weak_attribution" in checks:
        reasons.append("weak attribution")
    if "unsupported_causal_language" in checks:
        reasons.append("risky language")
    if has_unclear_limitations(row.get("limitations")):
        reasons.append("missing/unclear limitations")
    if normalize_text(row.get("evidence_strength")) == "Needs verification":
        reasons.append("evidence needs verification")
    return "; ".join(reasons)


def render_follow_up_rows(evidence_df: pd.DataFrame) -> None:
    st.subheader("Rows Needing Follow-Up")
    if evidence_df.empty:
        st.info("No evidence rows available.")
        return

    follow_up = evidence_df.copy()
    follow_up["follow_up_reasons"] = follow_up.apply(follow_up_reasons, axis=1)
    follow_up = follow_up[follow_up["follow_up_reasons"] != ""]
    if follow_up.empty:
        st.success("No rows currently match the follow-up criteria.")
        return

    columns = ["follow_up_reasons"] + display_columns(follow_up)
    st.dataframe(follow_up[columns], use_container_width=True, hide_index=True)


def render_update_frequency_breakdown(evidence_df: pd.DataFrame) -> None:
    st.subheader("Update-Frequency Breakdown")
    if evidence_df.empty or "update_frequency" not in evidence_df.columns:
        st.info("No update_frequency column available.")
        return

    rows: list[dict[str, object]] = []
    for bucket, patterns in UPDATE_FREQUENCY_BUCKETS.items():
        count = int(
            evidence_df["update_frequency"].apply(
                lambda value: any(re.search(pattern, normalize_text(value), re.I) for pattern in patterns)
            ).sum()
        )
        rows.append({"Update frequency": bucket, "Rows": count})

    st.caption("Rows can count in more than one category when the update_frequency field names multiple cadences.")
    frequency_df = pd.DataFrame(rows)
    st.bar_chart(frequency_df.set_index("Update frequency"), y="Rows")
    st.dataframe(frequency_df, use_container_width=True, hide_index=True)


def render_source_type_breakdown(source_df: pd.DataFrame) -> None:
    st.subheader("Source-Type Breakdown")
    if source_df.empty or "source_type" not in source_df.columns:
        st.info("No source_type data available.")
        return

    source_counts = count_summary(source_df, "source_type")
    st.dataframe(source_counts, use_container_width=True, hide_index=True)


def short_date(value: date) -> str:
    return f"{value.strftime('%b')} {value.day}"


def active_project_phase_index(today: date) -> int | None:
    active_indexes = [
        index
        for index, phase in enumerate(PROJECT_TIMELINE)
        if phase["start"] <= today <= phase["end"]
    ]
    if active_indexes:
        return active_indexes[-1]
    return None


def project_timeline_df(today: date) -> pd.DataFrame:
    active_index = active_project_phase_index(today)
    rows: list[dict[str, str]] = []
    for index, phase in enumerate(PROJECT_TIMELINE):
        if active_index is not None:
            status = "Active" if index == active_index else "Complete" if index < active_index else "Upcoming"
        elif today < PROJECT_TIMELINE[0]["start"]:
            status = "Upcoming"
        else:
            status = "Complete"

        rows.append(
            {
                "Dates": f"{short_date(phase['start'])} - {short_date(phase['end'])}",
                "Milestone": phase["milestone"],
                "Status": status,
                "Focus": phase["focus"],
            }
        )
    return pd.DataFrame(rows)


def project_table_status(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    review_df: pd.DataFrame,
    staged_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Table": "source_registry",
                "Rows": len(source_df),
                "Purpose": "Authoritative source metadata and URLs.",
            },
            {
                "Table": "evidence_matrix",
                "Rows": len(evidence_df),
                "Purpose": "Certified master matrix for report-ready claims.",
            },
            {
                "Table": "staged_evidence",
                "Rows": len(staged_df),
                "Purpose": "Temporary holding area for AI-generated candidate rows.",
            },
            {
                "Table": "review_needed",
                "Rows": len(review_df),
                "Purpose": "Validation issues and operator follow-up tasks.",
            },
            {
                "Table": "best_sources",
                "Rows": len(best_sources_df),
                "Purpose": "Curated shortlist for policy briefs and final materials.",
            },
        ]
    )


def page_project_roadmap(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    review_df: pd.DataFrame,
    staged_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> None:
    st.title("Project Roadmap")
    st.caption("Proposal-aligned control center for the IOOS Matrix field project.")

    today = date.today()
    active_index = active_project_phase_index(today)
    if active_index is None:
        current_phase = "Complete" if today > PROJECT_TIMELINE[-1]["end"] else "Not started"
    else:
        current_phase = PROJECT_TIMELINE[active_index]["milestone"]

    metric_columns = st.columns(4)
    metric_columns[0].metric("Current phase", current_phase)
    metric_columns[1].metric("Core tables", "5")
    metric_columns[2].metric("Evidence rows", f"{len(evidence_df):,}")
    metric_columns[3].metric("Briefing sources", f"{len(best_sources_df):,}")

    objective_col, governance_col = st.columns([1, 1])
    with objective_col:
        st.subheader("Project Objectives")
        for objective in PROJECT_OBJECTIVES:
            st.write(f"- {objective}")

    with governance_col:
        st.subheader("Governance Rules")
        st.dataframe(
            pd.DataFrame(PROJECT_GOVERNANCE_RULES),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Timeline")
    st.dataframe(
        project_timeline_df(today),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Dates": st.column_config.TextColumn(width="small"),
            "Status": st.column_config.TextColumn(width="small"),
            "Focus": st.column_config.TextColumn(width="large"),
        },
    )

    table_col, priority_col = st.columns([0.9, 1.1])
    with table_col:
        st.subheader("Operational Tables")
        st.dataframe(
            project_table_status(evidence_df, source_df, review_df, staged_df, best_sources_df),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rows": st.column_config.NumberColumn(format="%d", width="small"),
                "Purpose": st.column_config.TextColumn(width="large"),
            },
        )

    with priority_col:
        st.subheader("Evidence Build Priorities")
        st.dataframe(
            pd.DataFrame(PROJECT_EVIDENCE_PRIORITIES),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Priority": st.column_config.TextColumn(width="medium"),
                "Need": st.column_config.TextColumn(width="large"),
            },
        )


def coverage_matrix(evidence_df: pd.DataFrame) -> pd.DataFrame:
    required = {"impact_domain", "ioos_region_code"}
    if evidence_df.empty or not required.issubset(evidence_df.columns):
        return pd.DataFrame()
    matrix = pd.crosstab(
        evidence_df["impact_domain"].replace("", "Unspecified sector"),
        evidence_df["ioos_region_code"].replace("", "Unspecified region"),
    )
    matrix.index.name = "Sector"
    return matrix.sort_index()


def render_coverage_matrix(evidence_df: pd.DataFrame) -> None:
    st.subheader("Coverage Matrix")
    matrix = coverage_matrix(evidence_df)
    if matrix.empty:
        st.info("Sector and region fields are required for the coverage matrix.")
        return
    st.markdown(
        """
        <div class="coverage-key">
            <span>0 = gap</span>
            <span>1-2 = thin</span>
            <span>3+ = richer coverage</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    max_value = int(matrix.to_numpy().max()) if matrix.size else 0

    def cell_color(value: int) -> str:
        if value <= 0:
            return "#f6f8f9"
        if value == 1:
            return "#dff0f2"
        if value == 2:
            return "#b8dfe2"
        if max_value <= 3:
            return "#79bec9"
        return "#4fa8b6" if value < max_value else "#1f7a68"

    header_cells = "".join(f"<th>{hub_escape(column)}</th>" for column in matrix.columns)
    body_rows = []
    for sector, row in matrix.iterrows():
        cells = [f"<td>{hub_escape(sector)}</td>"]
        for value in row:
            numeric_value = int(value)
            text_color = "#ffffff" if numeric_value and cell_color(numeric_value) in {"#4fa8b6", "#1f7a68"} else "#10212b"
            cells.append(
                f'<td style="background:{cell_color(numeric_value)};color:{text_color};font-weight:760;">{numeric_value}</td>'
            )
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    st.markdown(
        f"""
        <div class="coverage-matrix-wrap">
            <table class="coverage-matrix-table">
                <thead><tr><th>Sector</th>{header_cells}</tr></thead>
                <tbody>{''.join(body_rows)}</tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def lower_text_series(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    """Return lower-cased row text from the columns that exist in a dataframe."""
    if df.empty:
        return pd.Series(dtype=str)
    available_columns = [column for column in columns if column in df.columns]
    if not available_columns:
        return pd.Series("", index=df.index)
    return df[available_columns].apply(
        lambda row: " ".join(normalize_text(value) for value in row),
        axis=1,
    ).str.lower()


def keyword_mask(df: pd.DataFrame, columns: list[str], keywords: list[str]) -> pd.Series:
    text = lower_text_series(df, columns)
    if text.empty:
        return pd.Series(False, index=df.index)
    normalized_keywords = [keyword.lower() for keyword in keywords]
    return text.map(lambda value: any(keyword in value for keyword in normalized_keywords))


def unique_row_count(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    if "row_id" not in df.columns:
        return len(df)
    row_ids = df["row_id"].map(normalize_text)
    nonblank_ids = row_ids[row_ids != ""]
    return int(nonblank_ids.nunique() + (row_ids == "").sum())


def source_backed_rows(evidence_df: pd.DataFrame) -> pd.DataFrame:
    if evidence_df.empty:
        return evidence_df.copy()
    source_columns = [column for column in ["source_url", "source_id", "source_name"] if column in evidence_df.columns]
    if not source_columns:
        return evidence_df.copy()
    source_mask = pd.Series(False, index=evidence_df.index)
    for column in source_columns:
        source_mask = source_mask | (evidence_df[column].map(normalize_text) != "")
    return evidence_df[source_mask].copy()


def decision_use_counts(evidence_df: pd.DataFrame) -> tuple[int, dict[str, int]]:
    source_checked = source_backed_rows(evidence_df)
    if source_checked.empty:
        return 0, {category: 0 for category in DECISION_USE_CATEGORY_KEYWORDS}

    category_counts: dict[str, int] = {}
    any_category_mask = pd.Series(False, index=source_checked.index)
    for category, keywords in DECISION_USE_CATEGORY_KEYWORDS.items():
        mask = keyword_mask(source_checked, DECISION_USE_TEXT_COLUMNS, keywords)
        category_counts[category] = unique_row_count(source_checked[mask])
        any_category_mask = any_category_mask | mask

    return unique_row_count(source_checked[any_category_mask]), category_counts


def quantified_benefit_study_count(best_sources_df: pd.DataFrame, evidence_df: pd.DataFrame) -> int:
    if not best_sources_df.empty:
        source_type = (
            best_sources_df["source_type"].map(normalize_text).str.lower()
            if "source_type" in best_sources_df.columns
            else pd.Series("", index=best_sources_df.index)
        )
        text = lower_text_series(best_sources_df, BENEFIT_STUDY_TEXT_COLUMNS)
        included_type = source_type.map(lambda value: any(keyword in value for keyword in BENEFIT_STUDY_SOURCE_TYPES))
        excluded_type = source_type.map(lambda value: any(keyword in value for keyword in BENEFIT_STUDY_EXCLUDED_SOURCE_TYPES))
        quantified_text = text.str.contains(
            r"\$|million|billion|dollar|cost|savings?|avoided|benefits?|value",
            regex=True,
        )
        benefit_framed = text.str.contains(
            r"benefit|valuation|value-of-information|user value|avoided|savings?|scenario|modeled",
            regex=True,
        )
        return int((included_type & quantified_text & benefit_framed & ~excluded_type).sum())

    text = lower_text_series(evidence_df, DECISION_USE_TEXT_COLUMNS + ["source_id", "source_url"])
    if text.empty:
        return 0
    quantified_rows = text.str.contains(
        r"\$|million|billion|dollar|cost|savings?|avoided|benefits?|value",
        regex=True,
    )
    context_only = text.str.contains(r"sector baseline|sector context|marine economy|ocean enterprise", regex=True)
    return unique_row_count(evidence_df[quantified_rows & ~context_only])


def operational_safety_signal(evidence_df: pd.DataFrame, best_sources_df: pd.DataFrame) -> tuple[str, str, str, int]:
    safety_df = pd.concat(
        [
            evidence_df[[column for column in DECISION_USE_TEXT_COLUMNS if column in evidence_df.columns]],
            best_sources_df[[column for column in BENEFIT_STUDY_TEXT_COLUMNS if column in best_sources_df.columns]],
        ],
        ignore_index=True,
    )
    text = " ".join(lower_text_series(safety_df, list(safety_df.columns)).tolist())

    if re.search(r"\b66\s*%|66 percent|two[- ]thirds", text):
        return "~66%", "smaller SAR search areas", "HF radar / SAROPS performance metric from source-checked rows.", 66
    if "three times smaller" in text:
        return "~67%", "smaller SAR search areas", "HF radar / SAROPS performance metric from source-checked rows.", 67
    if re.search(r"\b59\s*%|59 percent", text) and "ground" in text:
        return "59%", "lower vessel-grounding risk", "PORTS safety evidence documents reduced vessel-risk outcomes.", 59
    if re.search(r"\b50\s*%|50 percent", text) and "ground" in text:
        return "50%", "lower vessel-grounding risk", "PORTS safety evidence documents reduced vessel-risk outcomes.", 50
    return "Documented", "vessel-risk reductions", "HF radar / SAR and PORTS safety rows are tracked without monetizing every outcome.", 45


def ocean_enterprise_signal(best_sources_df: pd.DataFrame, evidence_df: pd.DataFrame) -> tuple[str, str]:
    ocean_sources = best_sources_df[keyword_mask(best_sources_df, BENEFIT_STUDY_TEXT_COLUMNS, ["ocean enterprise"])]
    ocean_rows = evidence_df[keyword_mask(evidence_df, DECISION_USE_TEXT_COLUMNS + ["source_id"], ["ocean enterprise"])]
    text_parts = []
    if not ocean_sources.empty:
        text_parts.extend(lower_text_series(ocean_sources, BENEFIT_STUDY_TEXT_COLUMNS).tolist())
    if not ocean_rows.empty:
        text_parts.extend(lower_text_series(ocean_rows, DECISION_USE_TEXT_COLUMNS).tolist())
    text = " ".join(text_parts)

    has_businesses = bool(re.search(r"\b814\b", text))
    has_revenue = bool(re.search(r"\$8\s*b|\$8\s+billion|8 billion", text))
    if has_businesses and has_revenue:
        return "814 businesses / $8B revenue", "Ocean Enterprise market footprint; sector context only, not attribution."
    if has_businesses:
        return "814 businesses", "Ocean Enterprise market footprint; sector context only, not attribution."
    if has_revenue:
        return "$8B revenue", "Ocean Enterprise market footprint; sector context only, not attribution."
    return "Sector context", "Ocean Enterprise market footprint; use as context rather than attribution."


def evidence_signal_tags_html(category_counts: dict[str, int]) -> str:
    tags = [
        f"<span>{hub_escape(category)} {count:,}</span>"
        for category, count in category_counts.items()
        if count
    ]
    return "".join(tags) or "<span>Coverage pending</span>"


def pluralized_label(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


def render_evidence_signal_chart(evidence_df: pd.DataFrame, best_sources_df: pd.DataFrame) -> None:
    verified_use_count, category_counts = decision_use_counts(evidence_df)
    benefit_count = quantified_benefit_study_count(best_sources_df, evidence_df)
    safety_value, safety_unit, safety_note, safety_width = operational_safety_signal(evidence_df, best_sources_df)
    ocean_value, ocean_note = ocean_enterprise_signal(best_sources_df, evidence_df)
    category_tags = evidence_signal_tags_html(category_counts)
    chart_label = (
        f"{verified_use_count} verified decision use cases; "
        f"{benefit_count} quantified benefit studies; "
        f"{safety_value} {safety_unit}; "
        f"{ocean_value} Ocean Enterprise market footprint."
    )

    st.markdown(
        f"""
        <div class="evidence-signal-chart" role="img" aria-label="{hub_escape(chart_label)}">
            <div class="evidence-signal-header">
                <div>
                    <div class="hub-kicker">Evidence signals</div>
                    <h2>Verified use and benefit evidence</h2>
                </div>
                <p>Decision-use counts, quantified studies, safety performance, and market footprint are kept as separate signals.</p>
            </div>
            <div class="evidence-signal-grid">
                <div class="evidence-signal-card signal-uses">
                    <div class="evidence-signal-title">Verified Decision Uses</div>
                    <div class="evidence-signal-value">{verified_use_count:,}</div>
                    <div class="evidence-signal-unit">{hub_escape(pluralized_label(verified_use_count, "verified use case"))}</div>
                    <div class="evidence-signal-tags">{category_tags}</div>
                </div>
                <div class="evidence-signal-card signal-benefits">
                    <div class="evidence-signal-title">Economic Benefit Evidence</div>
                    <div class="evidence-signal-value">{benefit_count:,}</div>
                    <div class="evidence-signal-unit">{hub_escape(pluralized_label(benefit_count, "quantified benefit study", "quantified benefit studies"))}</div>
                    <p class="evidence-signal-note">Monetized case studies and modeled benefit studies are counted, not combined into one ROI.</p>
                </div>
                <div class="evidence-signal-card signal-safety">
                    <div class="evidence-signal-title">Operational Safety Improvement</div>
                    <div class="evidence-signal-value">{hub_escape(safety_value)}</div>
                    <div class="evidence-signal-unit">{hub_escape(safety_unit)}</div>
                    <div class="evidence-signal-meter" aria-hidden="true"><span style="width:{safety_width}%;"></span></div>
                    <p class="evidence-signal-note">{hub_escape(safety_note)}</p>
                </div>
                <div class="evidence-signal-card signal-market">
                    <div class="evidence-signal-title">Ocean Enterprise Market Footprint</div>
                    <div class="evidence-signal-value">{hub_escape(ocean_value)}</div>
                    <div class="evidence-signal-unit">sector context</div>
                    <p class="evidence-signal-note">{hub_escape(ocean_note)}</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_strength_distribution(evidence_df: pd.DataFrame) -> None:
    st.subheader("Evidence Strength Distribution")
    if evidence_df.empty or "evidence_strength" not in evidence_df.columns:
        st.info("No evidence strength data is available.")
        return
    counts = count_summary(evidence_df, "evidence_strength")
    st.bar_chart(counts.set_index("Category"), y="Rows")
    st.dataframe(counts, use_container_width=True, hide_index=True)


def render_freshness_indicators(evidence_df: pd.DataFrame) -> None:
    st.subheader("Freshness Indicators")
    if evidence_df.empty:
        st.info("No evidence rows are available.")
        return
    with_year = add_metric_year_column(evidence_df)
    year_series = pd.to_numeric(with_year.get("metric_year", pd.Series(dtype=float)), errors="coerce")
    rows_with_year = with_year[year_series.notna()].copy()
    if rows_with_year.empty:
        st.info("Metric years are not structured enough to compute freshness indicators.")
        return
    rows_with_year["metric_year"] = pd.to_numeric(rows_with_year["metric_year"], errors="coerce").astype("Int64")
    oldest = rows_with_year.sort_values("metric_year").head(8)
    current_year = date.today().year
    rows_with_year["age_years"] = current_year - rows_with_year["metric_year"].astype(int)
    stale_count = int((rows_with_year["age_years"] >= 10).sum())
    missing_limitations = (
        int((with_year["limitations"].map(normalize_text) == "").sum())
        if "limitations" in with_year.columns
        else 0
    )
    metric_cols = st.columns(3)
    metric_cols[0].metric("Oldest metric year", f"{int(rows_with_year['metric_year'].min())}")
    metric_cols[1].metric("Rows 10+ years old", f"{stale_count:,}")
    metric_cols[2].metric("Missing limitations", f"{missing_limitations:,}")
    st.dataframe(
        oldest[[column for column in ["row_id", "impact_domain", "ioos_region_code", "metric_year", "metric", "source_id"] if column in oldest.columns]],
        use_container_width=True,
        hide_index=True,
    )


def page_dashboard_summary(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    review_df: pd.DataFrame,
    staged_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> None:
    evidence_dashboard_df = add_dashboard_fields(evidence_df, review_df)
    status_counts = evidence_dashboard_df["dashboard_status"].value_counts() if "dashboard_status" in evidence_dashboard_df else {}
    unique_sources = (
        evidence_dashboard_df["source_id"].replace("", pd.NA).dropna().nunique()
        if "source_id" in evidence_dashboard_df
        else len(source_df)
    )
    review_errors = count_value(review_df, "severity", "error")
    review_warnings = count_value(review_df, "severity", "warning")

    metric_columns = st.columns(4)
    metric_columns[0].metric("Evidence rows", f"{len(evidence_dashboard_df):,}")
    metric_columns[1].metric("Unique sources", f"{unique_sources:,}")
    metric_columns[2].metric("Report-ready rows", f"{int(status_counts.get('report-ready', 0)):,}")
    metric_columns[3].metric("Needs follow-up", f"{int(status_counts.get('needs-follow-up', 0)):,}")

    metric_columns = st.columns(4)
    metric_columns[0].metric("Staged rows", f"{len(staged_df):,}")
    metric_columns[1].metric("Review items", f"{len(review_df):,}")
    metric_columns[2].metric("Briefing sources", f"{len(best_sources_df):,}")
    metric_columns[3].metric("Current phase", active_phase_label())

    render_evidence_signal_chart(evidence_dashboard_df, best_sources_df)

    if review_df.empty:
        st.success("No validation review items are currently listed.")
    else:
        st.warning(f"Validation review shows {review_errors} errors and {review_warnings} warnings.")

    overview_tab, coverage_tab, freshness_tab = st.tabs(
        ["Health Check", "Coverage Matrix", "Freshness"]
    )
    with overview_tab:
        top_left, top_right = st.columns([1.15, 1])
        with top_left:
            render_report_readiness_breakdown(evidence_dashboard_df)
            render_strength_distribution(evidence_dashboard_df)
        with top_right:
            render_strength_crosstab(evidence_dashboard_df)
    with coverage_tab:
        render_coverage_matrix(evidence_dashboard_df)
        render_domain_coverage(evidence_dashboard_df)
        bottom_left, bottom_right = st.columns(2)
        with bottom_left:
            render_update_frequency_breakdown(evidence_dashboard_df)
        with bottom_right:
            render_source_type_breakdown(source_df)
    with freshness_tab:
        render_freshness_indicators(evidence_dashboard_df)


def page_evidence_atlas(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    review_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> None:
    st.markdown(
        """
        <div class="hub-page-title">
            <div class="hub-kicker">Financial Evidence</div>
            <h1>Financial Evidence</h1>
            <p>Chart published IOOS value evidence by category, sector, geography, confidence, and claim-use boundary without turning context into a national total.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    explorer_df = enrich_evidence_with_source_fields(evidence_df, source_df)
    explorer_df = add_dashboard_fields(explorer_df, review_df)
    explorer_df = add_metric_year_column(explorer_df)
    atlas_df = add_evidence_atlas_fields(explorer_df)
    level_counts = atlas_level_count_table(atlas_df)
    count_by_level = {
        row["Category"]: int(row["Rows"])
        for _, row in level_counts.iterrows()
    }

    metric_cols = st.columns(4)
    for index, level in enumerate(EVIDENCE_ATLAS_LEVELS):
        label = atlas_level_label(level["key"])
        metric_cols[index].metric(level["title"], f"{count_by_level.get(label, 0):,}")

    st.caption(
        "Financial evidence categories are evidence tags, not additive totals. A row can appear in more than one category when, for example, a published dollar estimate is also an avoided-loss case."
    )

    level_tabs = st.tabs(
        [level["label"] for level in EVIDENCE_ATLAS_LEVELS]
        + ["Explorer", "Source Shelf", "Methodology"]
    )

    for tab, level in zip(level_tabs[: len(EVIDENCE_ATLAS_LEVELS)], EVIDENCE_ATLAS_LEVELS):
        with tab:
            render_financial_evidence_level_tab(atlas_df, level)

    with level_tabs[-3]:
        if atlas_df.empty:
            st.info("No evidence rows are available under the current public display rule.")
        else:
            search_text = st.text_input(
                "Search financial evidence",
                placeholder="Try avoided loss, fuel, port, fisheries, cargo, storm, SAROPS...",
                key="atlas_search",
            )
            filtered = search_dataframe(atlas_df, search_text)

            filter_cols = st.columns(4)
            level_options = {
                atlas_level_label(level["key"]): level["key"]
                for level in EVIDENCE_ATLAS_LEVELS
            }
            selected_level_labels = filter_cols[0].multiselect("Financial evidence category", list(level_options))
            selected_level_keys = [level_options[label] for label in selected_level_labels]
            selected_domains = filter_cols[1].multiselect(
                "Sector",
                atlas_option_values(filtered, "impact_domain"),
            )
            selected_regions = filter_cols[2].multiselect(
                "IOOS region",
                atlas_option_values(filtered, "ioos_region_code"),
            )
            selected_number_types = filter_cols[3].multiselect(
                "Economic number",
                atlas_option_values(filtered, "economic_number_type"),
            )

            filtered = atlas_filtered_by_levels(filtered, selected_level_keys)
            if selected_domains and "impact_domain" in filtered.columns:
                filtered = filtered[filtered["impact_domain"].isin(selected_domains)]
            if selected_regions and "ioos_region_code" in filtered.columns:
                filtered = filtered[filtered["ioos_region_code"].isin(selected_regions)]
            if selected_number_types and "economic_number_type" in filtered.columns:
                filtered = filtered[filtered["economic_number_type"].isin(selected_number_types)]

            st.caption(f"Showing {len(filtered):,} of {len(atlas_df):,} financial evidence rows")
            if filtered.empty:
                st.info("No rows match the current financial evidence filters.")
            else:
                display_columns = [
                    "row_id",
                    "atlas_levels",
                    "atlas_pathway",
                    "atlas_claim_boundary",
                    "economic_number_type",
                    "impact_domain",
                    "ioos_region_code",
                    "metric",
                    "metric_year_or_dollar_year",
                    "claim_allowed",
                    "source_name",
                    "source_url",
                    "limitations",
                ]
                st.dataframe(
                    filtered[[column for column in display_columns if column in filtered.columns]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "atlas_levels": st.column_config.TextColumn("Financial evidence categories", width="large"),
                        "atlas_claim_boundary": st.column_config.TextColumn("Claim boundary", width="medium"),
                        "metric": st.column_config.TextColumn(width="large"),
                        "claim_allowed": st.column_config.TextColumn("Claim allowed", width="large"),
                        "source_url": st.column_config.LinkColumn("Source URL"),
                        "limitations": st.column_config.TextColumn(width="large"),
                    },
                )
                st.download_button(
                    "Download financial evidence CSV",
                    filtered.to_csv(index=False).encode("utf-8"),
                    file_name="ioos_financial_evidence.csv",
                    mime="text/csv",
                )

    with level_tabs[-2]:
        if best_sources_df.empty:
            st.info("No best-source records are available under the current public display rule.")
        else:
            source_view = best_sources_df.copy()
            source_view["atlas_use"] = source_view.apply(best_source_atlas_use, axis=1)
            source_search = st.text_input("Search source shelf", key="atlas_source_search")
            source_view = search_dataframe(source_view, source_search)
            source_view = add_multiselect_filter(source_view, "ioos_region_code", "IOOS Region Code")
            source_view = add_multiselect_filter(source_view, "priority_tier", "Priority Tier")
            source_view = add_multiselect_filter(source_view, "source_type", "Source Type")
            st.caption(f"Showing {len(source_view):,} of {len(best_sources_df):,} source records")
            source_columns = [
                "source_name",
                "atlas_use",
                "source_type",
                "ioos_region_code",
                "priority_tier",
                "impact_domains",
                "key_metrics",
                "recommended_claim_language",
                "caveats",
                "source_url",
            ]
            st.dataframe(
                source_view[[column for column in source_columns if column in source_view.columns]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "source_url": st.column_config.LinkColumn("Source URL"),
                    "atlas_use": st.column_config.TextColumn("Evidence use", width="medium"),
                    "key_metrics": st.column_config.TextColumn(width="large"),
                    "recommended_claim_language": st.column_config.TextColumn(width="large"),
                    "caveats": st.column_config.TextColumn(width="large"),
                },
            )

    with level_tabs[-1]:
        st.markdown(atlas_level_cards_html(atlas_df), unsafe_allow_html=True)
        st.subheader("Category Coverage")
        st.dataframe(
            level_counts,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rows": st.column_config.NumberColumn(format="%d", width="small"),
                "Share of rows": st.column_config.ProgressColumn(
                    "Share of rows",
                    format="%.0f%%",
                    min_value=0,
                    max_value=100,
                    width="medium",
                ),
                "Safe use": st.column_config.TextColumn(width="large"),
            },
        )
        st.markdown(
            """
            <div class="atlas-method-grid">
                <div class="atlas-method-card">
                    <b>What The Atlas Can Say</b>
                    <ul class="atlas-boundary-list">
                        <li>Documented reported benefits from published sources.</li>
                        <li>Operational metrics such as hours saved, closures avoided, or search areas reduced.</li>
                        <li>Economic activity supported by IOOS information, clearly labeled as context.</li>
                        <li>Inflation-adjusted values only when original value, dollar year, and method are stored.</li>
                    </ul>
                </div>
                <div class="atlas-method-card">
                    <b>What The Atlas Should Not Say</b>
                    <ul class="atlas-boundary-list">
                        <li>Total national value of IOOS.</li>
                        <li>IOOS contributes a single dollar total annually.</li>
                        <li>Return on investment created by aggregating unrelated studies.</li>
                        <li>Economic activity supported is the same thing as IOOS-created benefit.</li>
                    </ul>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.subheader("Inflation-Adjustment Fields To Add")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Field": "original_dollar_value",
                        "Purpose": "The published dollar value exactly as reported by the source.",
                    },
                    {
                        "Field": "dollar_year",
                        "Purpose": "The source year or dollar year needed for comparison.",
                    },
                    {
                        "Field": "annual_or_one_time",
                        "Purpose": "Separates recurring annual values from event or one-time benefits.",
                    },
                    {
                        "Field": "adjusted_2026_value",
                        "Purpose": "A CPI-adjusted comparison value, calculated only from stored source fields.",
                    },
                    {
                        "Field": "adjustment_method",
                        "Purpose": "The inflation method and index used so the calculation is auditable.",
                    },
                    {
                        "Field": "confidence",
                        "Purpose": "A reviewer-facing confidence label for the value, source, and IOOS attribution.",
                    },
                ]
            ),
            use_container_width=True,
            hide_index=True,
            column_config={"Purpose": st.column_config.TextColumn(width="large")},
        )


def render_record_detail(
    row: pd.Series,
    source_df: pd.DataFrame,
    all_rows: pd.DataFrame | None = None,
) -> None:
    source_row = source_for_row(row, source_df)
    row_id = row_field(row, "row_id", "Selected record")
    claim = row_field(row, "claim_allowed", row_field(row, "metric", "No claim recorded."))
    metric = row_field(row, "metric", "Metric not recorded.")
    limitations = row_field(row, "limitations", "No limitations recorded.")
    economic_type = row_field(row, "economic_number_type", "Unclassified")
    ioos_role = row_field(row, "ioos_role_type", "Unclassified")
    allowed_use = row_field(row, "allowed_use", "Not classified.")
    not_allowed_use = row_field(row, "not_allowed_use", "Not classified.")
    source_name = row_field(source_row, "source_name", row_field(row, "source_name", row_field(row, "source_id", "Source pending")))
    source_url = row_field(source_row, "source_url", row_field(row, "source_url"))
    source_type = row_field(source_row, "source_type", row_field(row, "source_type", "Source type pending"))
    verification_status = row_field(source_row, "verification_status", row_field(row, "source_verification_status", "Not recorded"))
    provenance_items = [
        f"Official row: {row_id}",
        f"Date record created: {row_field(row, 'date_record_created', 'Not recorded')}",
        f"Source verification needed: {row_field(row, 'source_verification_needed', 'Not recorded')}",
        f"Update frequency: {row_field(row, 'update_frequency', 'Not recorded')}",
    ]
    if row_field(row, "ai_extraction_notes"):
        provenance_items.append(f"AI notes: {truncate_text(row_field(row, 'ai_extraction_notes'), 120)}")
    provenance_html = "".join(f"<span>{hub_escape(item)}</span>" for item in provenance_items)
    source_link_html = (
        f'<p><a href="{hub_escape(source_url)}" target="_blank" rel="noopener">Open source</a></p>'
        if source_url
        else "<p>Source link not recorded.</p>"
    )

    st.markdown(
        f"""
        <div class="detail-panel">
            <span class="hub-chip neutral">{hub_escape(row_id)}</span>
            <h2>{hub_escape(claim)}</h2>
            <div class="row-meta">
                <span>{hub_escape(row_field(row, "impact_domain", "Domain pending"))}</span>
                <span>{hub_escape(row_field(row, "region", "Region pending"))}</span>
                <span>{hub_escape(row_field(row, "ioos_region_code", "Region code pending"))}</span>
            </div>
            {trust_signal_cluster_html(row)}
            <div class="detail-section">
                <b>Metric Details</b>
                <p>{hub_escape(metric)}</p>
                <p class="row-meta"><span>{hub_escape(row_field(row, "metric_year_or_dollar_year", "Year pending"))}</span><span>{hub_escape(row_field(row, "user_group", "Users pending"))}</span></p>
            </div>
            <div class="detail-section">
                <b>Claim Use Classification</b>
                <p class="row-meta"><span>{hub_escape(economic_type)}</span><span>{hub_escape(ioos_role)}</span></p>
                <p><b>Allowed:</b> {hub_escape(allowed_use)}</p>
                <p><b>Not allowed:</b> {hub_escape(not_allowed_use)}</p>
            </div>
            <div class="detail-section">
                <b>Source</b>
                <p>{hub_escape(source_name)}</p>
                <p class="row-meta"><span>{hub_escape(source_type)}</span><span>{hub_escape(verification_status)}</span></p>
                {source_link_html}
            </div>
            <div class="detail-section">
                <b>Limitations</b>
                <p>{hub_escape(limitations)}</p>
            </div>
            <div class="detail-section">
                <b>Provenance Trail</b>
                <div class="row-meta">{provenance_html}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    copy_text = claim_copy_block(row, source_df)
    render_copy_button(copy_text)
    st.text_area("Copy-ready claim block", value=copy_text, height=210)

    if all_rows is not None and not all_rows.empty and "source_id" in all_rows.columns:
        source_id = row_field(row, "source_id")
        if source_id:
            related = all_rows[
                (all_rows["source_id"].map(normalize_text) == source_id)
                & (all_rows.get("row_id", pd.Series(dtype=str)).map(normalize_text) != row_id)
            ]
            if not related.empty:
                st.subheader("Related Claims From This Source")
                st.dataframe(
                    evidence_display_dataframe(related.head(5)),
                    use_container_width=True,
                    hide_index=True,
                    column_config={"source_url": st.column_config.LinkColumn("Source URL")}
                    if "source_url" in related.columns
                    else {},
                )


def enrich_evidence_with_source_fields(evidence_df: pd.DataFrame, source_df: pd.DataFrame) -> pd.DataFrame:
    """Attach source names and URLs so users do not need a separate registry page."""
    if evidence_df.empty or source_df.empty or "source_id" not in evidence_df.columns or "source_id" not in source_df.columns:
        return evidence_df.copy()

    source_columns = [
        column
        for column in ["source_id", "source_name", "source_url", "source_type", "verification_status"]
        if column in source_df.columns
    ]
    source_lookup = source_df[source_columns].copy()
    if "verification_status" in source_lookup.columns:
        source_lookup = source_lookup.rename(columns={"verification_status": "source_verification_status"})

    merged = evidence_df.merge(source_lookup, how="left", on="source_id")
    return merged.fillna("")


def page_evidence_matrix(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    review_df: pd.DataFrame,
) -> None:
    st.markdown(
        """
        <div class="hub-page-title">
            <div class="hub-kicker">Official promoted evidence</div>
            <h1>Evidence Database</h1>
            <p>Search source-backed economic impact claims, inspect trust signals, and copy verified claim blocks for briefs, reports, and presentations.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if evidence_df.empty:
        st.warning(f"No evidence matrix found at {EVIDENCE_PATH}")
        return

    explorer_df = enrich_evidence_with_source_fields(evidence_df, source_df)
    explorer_df = add_dashboard_fields(explorer_df, review_df)
    explorer_df = add_metric_year_column(explorer_df)

    ready_count = int(explorer_df.apply(is_external_ready_row, axis=1).sum()) if not explorer_df.empty else 0
    metric_cols = st.columns(4)
    metric_cols[0].metric("Promoted rows", f"{len(explorer_df):,}")
    metric_cols[1].metric("Ready for external use", f"{ready_count:,}")
    metric_cols[2].metric("Unique sources", f"{explorer_df['source_id'].replace('', pd.NA).dropna().nunique():,}" if "source_id" in explorer_df else "0")
    metric_cols[3].metric("Validation items", f"{len(review_df):,}")

    st.subheader("Search And Filters")
    saved_filter = st.selectbox("Saved filter set", list(SAVED_FILTER_SETS), index=0)
    saved_defaults = SAVED_FILTER_SETS.get(saved_filter, {})
    search_text = st.text_input(
        "Search claims, metrics, sources, sectors, regions, and limitations",
        value=normalize_text(saved_defaults.get("search")),
        placeholder="Try PORTS, fisheries, avoided cost, MARACOOS...",
    )

    quick_col, view_col = st.columns([1, 1])
    with quick_col:
        external_ready = st.checkbox(
            "External-use ready only",
            value=bool(saved_defaults.get("external_ready", False)),
        )
    with view_col:
        view_mode = st.radio("View mode", ["Dense table", "Evidence cards"], horizontal=True)

    filter_cols = st.columns(5)

    def multiselect_filter(column: str, label: str, slot: int) -> list[str]:
        if column not in explorer_df.columns:
            return []
        options = sorted(value for value in explorer_df[column].dropna().unique() if normalize_text(value))
        default = [
            value
            for value in saved_defaults.get(column, [])
            if value in options
        ]
        return filter_cols[slot].multiselect(label, options, default=default)

    impact_domain = multiselect_filter("impact_domain", "Sector", 0)
    region = multiselect_filter("ioos_region_code", "Region", 1)
    source_type = multiselect_filter("source_type", "Source type", 2)
    evidence_strength = multiselect_filter("evidence_strength", "Evidence strength", 3)
    attribution = multiselect_filter("ioos_attribution_strength", "Attribution", 4)

    year_values = sorted(
        int(value)
        for value in pd.to_numeric(explorer_df.get("metric_year", pd.Series(dtype=float)), errors="coerce").dropna().unique()
    )
    year_range: tuple[int, int] | None = None
    if year_values:
        year_range = st.slider(
            "Metric or dollar-year range",
            min_value=min(year_values),
            max_value=max(year_values),
            value=(min(year_values), max(year_values)),
        )

    filter_state: dict[str, object] = {
        "search": search_text,
        "external_ready": external_ready,
        "impact_domain": impact_domain,
        "ioos_region_code": region,
        "source_type": source_type,
        "evidence_strength": evidence_strength,
        "ioos_attribution_strength": attribution,
        "impact_domain_contains": saved_defaults.get("impact_domain_contains"),
        "status": saved_defaults.get("status"),
        "verification_needed": saved_defaults.get("verification_needed"),
        "year_range": year_range,
    }
    filtered = apply_evidence_filters(explorer_df, filter_state)

    st.caption(f"Showing {len(filtered):,} of {len(explorer_df):,} promoted evidence rows")
    if filtered.empty or "row_id" not in filtered.columns:
        st.info("No promoted rows match the current filters.")
        return

    results_col, detail_col = st.columns([1.45, 0.9], gap="large")
    filtered_reset = filtered.reset_index(drop=True)
    table_selected_row_id = ""

    with results_col:
        if view_mode == "Dense table":
            display_df = evidence_display_dataframe(filtered_reset)
            table_state = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "claim": st.column_config.TextColumn("Claim", width="large"),
                    "metric": st.column_config.TextColumn("Metric", width="large"),
                    "source_url": st.column_config.LinkColumn("Source URL"),
                    "economic_number_type": st.column_config.TextColumn("Economic number", width="medium"),
                    "ioos_role_type": st.column_config.TextColumn("IOOS role", width="medium"),
                    "external_use_ready": st.column_config.TextColumn("External use", width="small"),
                },
                on_select="rerun",
                selection_mode="single-row",
                key="evidence_database_results",
            )
            selected_positions = getattr(getattr(table_state, "selection", None), "rows", [])
            if selected_positions:
                table_selected_row_id = row_field(filtered_reset.iloc[selected_positions[0]], "row_id")
        else:
            for _, row in filtered_reset.head(16).iterrows():
                st.markdown(evidence_card_html(row, source_df), unsafe_allow_html=True)
            if len(filtered_reset) > 16:
                st.info("Showing the first 16 cards. Tighten filters or use dense table view for the full result set.")

        st.download_button(
            "Download filtered CSV",
            filtered.to_csv(index=False).encode("utf-8"),
            file_name="ioos_evidence_filtered.csv",
            mime="text/csv",
        )

    with detail_col:
        row_options = filtered_reset["row_id"].map(normalize_text).tolist()
        selected_index = row_options.index(table_selected_row_id) if table_selected_row_id in row_options else 0
        selected_row_id = st.selectbox("Detail panel", row_options, index=selected_index)
        selected_rows = filtered_reset[filtered_reset["row_id"].map(normalize_text) == selected_row_id]
        if not selected_rows.empty:
            render_record_detail(selected_rows.iloc[0], source_df, explorer_df)


NARRATIVE_TEXT_COLUMNS = [
    "impact_domain",
    "ioos_component",
    "region",
    "ioos_region_code",
    "user_group",
    "decision_supported",
    "economic_pathway",
    "metric",
    "economic_number_type",
    "ioos_role_type",
    "allowed_use",
    "not_allowed_use",
    "claim_allowed",
    "limitations",
    "ai_extraction_notes",
    "source_id",
    "source_name",
]

BEST_SOURCE_TEXT_COLUMNS = [
    "source_id",
    "source_name",
    "source_type",
    "ioos_region_code",
    "briefing_role",
    "impact_domains",
    "key_metrics",
    "evidence_profile",
    "attribution_profile",
    "recommended_claim_language",
    "caveats",
]


def keyword_filter(df: pd.DataFrame, keywords: list[str], columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    available_columns = [column for column in columns if column in df.columns]
    if not available_columns:
        return df.head(0).copy()
    lowered_keywords = [keyword.lower() for keyword in keywords]
    mask = df.apply(
        lambda row: any(keyword in combined_row_text(row, available_columns) for keyword in lowered_keywords),
        axis=1,
    )
    return df[mask].copy()


def unique_region_code_count(df: pd.DataFrame) -> int:
    if df.empty or "ioos_region_code" not in df.columns:
        return 0
    codes: set[str] = set()
    for value in df["ioos_region_code"]:
        codes.update(split_ioos_region_codes(value))
    return len(codes)


def source_count_for_rows(df: pd.DataFrame) -> int:
    if df.empty or "source_id" not in df.columns:
        return 0
    return int(df["source_id"].replace("", pd.NA).dropna().nunique())


def regional_handoff_table(
    regional_targets_df: pd.DataFrame,
    evidence_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, target in regional_targets_df.iterrows():
        code = normalize_text(target.get("ioos_region_code"))
        region_evidence = rows_for_region_code(evidence_df, code)
        region_sources = rows_for_region_code(best_sources_df, code)
        status_label, _ = regional_section_status(target, len(region_evidence), len(region_sources))
        rows.append(
            {
                "Region code": code,
                "Association": normalize_text(target.get("ioos_association")),
                "Region": normalize_text(target.get("region_name")),
                "Build status": status_label,
                "Public evidence rows": len(region_evidence),
                "Best sources": len(region_sources),
                "Priority domains": normalize_text(target.get("priority_domains")),
                "Evidence gap": normalize_text(target.get("evidence_gap")),
            }
        )
    return pd.DataFrame(rows)


def region_detail_card_html(target: pd.Series) -> str:
    priority_items = split_semicolon_items(target.get("priority_domains"))
    source_items = split_semicolon_items(target.get("source_targets"))
    return f"""
    <div class="region-detail-card">
        <b>Regional Build Notes</b>
        <p><strong>Evidence gap:</strong> {hub_escape(row_field(target, "evidence_gap", "Regional evidence gap pending."))}</p>
        <p><strong>Starter question:</strong> {hub_escape(row_field(target, "starter_research_question", "Starter research question pending."))}</p>
        <p><strong>Priority domains</strong></p>
        <ul>{html_list_items(priority_items, "Priority domains pending")}</ul>
        <p><strong>Source targets</strong></p>
        <ul>{html_list_items(source_items[:5], "Source targets pending")}</ul>
    </div>
    """


def render_region_section(
    target: pd.Series,
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> None:
    code = normalize_text(target.get("ioos_region_code"))
    association = normalize_text(target.get("ioos_association")) or code
    region_name = normalize_text(target.get("region_name")) or IOOS_REGION_OPTIONS.get(code, code)
    region_evidence = rows_for_region_code(evidence_df, code)
    region_sources = rows_for_region_code(best_sources_df, code)
    region_evidence = add_dashboard_fields(region_evidence, pd.DataFrame())
    ready_count = int(region_evidence.apply(is_external_ready_row, axis=1).sum()) if not region_evidence.empty else 0
    status_label, status_class = regional_section_status(target, len(region_evidence), len(region_sources))

    if code == MARACOOS_CODE and MARACOOS_COVERAGE_MAP_PATH.exists():
        _, map_col, _ = st.columns([0.08, 0.84, 0.08])
        with map_col:
            st.image(str(MARACOOS_COVERAGE_MAP_PATH), caption="MARACOOS coverage map", use_container_width=True)

    st.markdown(
        f"""
        <div class="hub-page-title">
            <div class="hub-kicker">{hub_escape(association)}</div>
            <h1>{hub_escape(region_name)}</h1>
            <p>
                <span class="hub-chip {hub_escape(status_class)}">{hub_escape(status_label)}</span>
                <span style="margin-left:0.45rem;">{hub_escape(row_field(target, "phase", "Regional build queue"))}</span>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("Public rows", f"{len(region_evidence):,}")
    metric_cols[1].metric("Ready claims", f"{ready_count:,}")
    metric_cols[2].metric("Best sources", f"{len(region_sources):,}")
    metric_cols[3].metric("Priority areas", f"{len(split_semicolon_items(target.get('priority_domains'))):,}")

    st.markdown(region_detail_card_html(target), unsafe_allow_html=True)

    evidence_tab, source_tab, prompt_tab = st.tabs(["Evidence Rows", "Source Shelf", "Handoff Prompt"])
    with evidence_tab:
        if region_evidence.empty:
            st.info("No public evidence rows are loaded for this region yet.")
        else:
            display_df = evidence_display_dataframe(region_evidence)
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "claim": st.column_config.TextColumn("Claim", width="large"),
                    "metric": st.column_config.TextColumn("Metric", width="large"),
                    "source_url": st.column_config.LinkColumn("Source URL"),
                    "external_use_ready": st.column_config.TextColumn("External use", width="small"),
                    "limitations": st.column_config.TextColumn(width="large"),
                },
            )
            st.download_button(
                f"Download {code} evidence CSV",
                region_evidence.to_csv(index=False).encode("utf-8"),
                file_name=f"ioos_{code.lower()}_evidence.csv",
                mime="text/csv",
                key=f"download_{code}_evidence",
            )

    with source_tab:
        if region_sources.empty:
            st.info("No best-source records are loaded for this region yet.")
        else:
            source_columns = [
                "source_id",
                "source_name",
                "source_type",
                "priority_tier",
                "briefing_role",
                "impact_domains",
                "key_metrics",
                "recommended_claim_language",
                "caveats",
                "source_url",
            ]
            st.dataframe(
                region_sources[[column for column in source_columns if column in region_sources.columns]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "source_url": st.column_config.LinkColumn("Source URL"),
                    "briefing_role": st.column_config.TextColumn(width="large"),
                    "key_metrics": st.column_config.TextColumn(width="large"),
                    "recommended_claim_language": st.column_config.TextColumn(width="large"),
                    "caveats": st.column_config.TextColumn(width="large"),
                },
            )
            st.download_button(
                f"Download {code} source CSV",
                region_sources.to_csv(index=False).encode("utf-8"),
                file_name=f"ioos_{code.lower()}_best_sources.csv",
                mime="text/csv",
                key=f"download_{code}_sources",
            )

    with prompt_tab:
        prompt = regional_research_prompt(
            target,
            normalize_text(target.get("starter_research_question")),
            "",
            8,
        )
        st.text_area(
            "Copy-ready regional research prompt",
            value=prompt,
            height=620,
            key=f"regional_prompt_{code}",
        )
        st.download_button(
            f"Download {code} prompt",
            prompt.encode("utf-8"),
            file_name=f"ioos_{code.lower()}_regional_research_prompt.txt",
            mime="text/plain",
            key=f"download_{code}_prompt",
        )


def page_regions(
    regional_targets_df: pd.DataFrame,
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> None:
    regions_df = association_regional_targets(regional_targets_df)
    st.markdown(
        """
        <div class="hub-page-title">
            <div class="hub-kicker">Regional evidence buildout</div>
            <h1>IOOS Regions</h1>
            <p>Each Regional Association has its own section, while all evidence still flows through the shared staged evidence and best-source tables. MARACOOS is the pilot build to complete first.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if regions_df.empty:
        st.warning(f"No IOOS Regional Association targets found at {REGIONAL_TARGETS_PATH}")
        return

    st.subheader("Regional Sections")
    tabs = st.tabs(regions_df["ioos_region_code"].map(normalize_text).tolist())
    for tab, (_, target) in zip(tabs, regions_df.iterrows()):
        with tab:
            render_region_section(target, evidence_df, source_df, best_sources_df)

    regions_with_rows = sum(
        1
        for code in regions_df["ioos_region_code"].map(normalize_text)
        if len(rows_for_region_code(evidence_df, code)) > 0
    )
    maracoos_rows = len(rows_for_region_code(evidence_df, MARACOOS_CODE))
    handoff_df = regional_handoff_table(regions_df, evidence_df, best_sources_df)
    with st.expander("Regional summary", expanded=False):
        metric_cols = st.columns(4)
        metric_cols[0].metric("Regional sections", f"{len(regions_df):,}")
        metric_cols[1].metric("Regions with rows", f"{regions_with_rows:,}")
        metric_cols[2].metric("MARACOOS rows", f"{maracoos_rows:,}")
        metric_cols[3].metric("Best-source records", f"{len(best_sources_df):,}")

    with st.expander("Regional handoff table", expanded=False):
        st.dataframe(
            handoff_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Priority domains": st.column_config.TextColumn(width="large"),
                "Evidence gap": st.column_config.TextColumn(width="large"),
            },
        )
        st.download_button(
            "Download regional handoff table",
            handoff_df.to_csv(index=False).encode("utf-8"),
            file_name="ioos_regional_handoff_table.csv",
            mime="text/csv",
        )


def sector_story_table(evidence_df: pd.DataFrame, review_df: pd.DataFrame) -> pd.DataFrame:
    evidence_dashboard_df = add_dashboard_fields(evidence_df, review_df)
    rows: list[dict[str, object]] = []
    for story in SECTOR_STORYLINES:
        matches = keyword_filter(evidence_dashboard_df, story["keywords"], NARRATIVE_TEXT_COLUMNS)
        if matches.empty:
            sample_decision = "Evidence rows for this sector have not been loaded yet."
        else:
            sample_decision = first_row_value(
                matches.iloc[0],
                ["decision_supported", "economic_pathway", "claim_allowed"],
            )
        rows.append(
            {
                "Sector": story["name"],
                "Rows": len(matches),
                "Sources": source_count_for_rows(matches),
                "External-ready rows": int(matches.apply(is_external_ready_row, axis=1).sum()) if not matches.empty else 0,
                "Why it matters": story["why"],
                "Example decision": sample_decision,
            }
        )
    return pd.DataFrame(rows)


def render_overview_stat_cards(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    review_df: pd.DataFrame,
    staged_df: pd.DataFrame,
) -> None:
    evidence_dashboard_df = add_dashboard_fields(evidence_df, review_df)
    ready_count = int(evidence_dashboard_df.apply(is_external_ready_row, axis=1).sum()) if not evidence_dashboard_df.empty else 0
    stats = [
        ("Evidence rows", len(evidence_df), "Promoted rows in the evidence matrix."),
        ("Source records", len(source_df), "Registered sources and URLs."),
        ("IOOS regions", unique_region_code_count(evidence_df), "Regional and national coverage represented."),
        ("Ready claims", ready_count, "Rows with enough evidence and attribution for reuse."),
        ("Staged drafts", len(staged_df), "Candidate rows held outside the official matrix."),
    ]
    card_html = "".join(
        (
            '<div class="overview-card">'
            f"<b>{hub_escape(label)}</b>"
            f'<span class="overview-stat">{value:,}</span>'
            f"<p>{hub_escape(description)}</p>"
            "</div>"
        )
        for label, value, description in stats
    )
    st.markdown(f'<div class="overview-grid">{card_html}</div>', unsafe_allow_html=True)


def render_ioos_system_tab(evidence_df: pd.DataFrame, source_df: pd.DataFrame, review_df: pd.DataFrame, staged_df: pd.DataFrame) -> None:
    st.markdown(
        """
        <p class="overview-intro">
            IOOS is shared ocean information infrastructure: observing assets, regional associations,
            data systems, models, and products that turn ocean conditions into decisions people can use.
            This app explains that system through the evidence base you are building.
        </p>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("The Value Chain")
    value_chain_nodes = "".join(
        f"""
        <div class="value-chain-node">
            <span class="hub-chip neutral">{index}</span>
            <b>{hub_escape(label)}</b>
            <span>{hub_escape(description)}</span>
        </div>
        """
        for index, (_, label, description) in enumerate(VALUE_CHAIN_LAYERS, start=1)
    )
    st.markdown(
        f"""
        <p class="overview-intro">
            The app scores evidence by how far a source traces this chain: from observation, through
            products and decisions, toward economic value.
        </p>
        <div class="value-chain-full">{value_chain_nodes}</div>
        """,
        unsafe_allow_html=True,
    )

    system_col, map_col = st.columns([1.05, 0.95], gap="large")
    with system_col:
        st.subheader("What The System Does")
        system_cards = [
            ("Observe", "Collects real-time and historical ocean, coastal, Great Lakes, and meteorological conditions."),
            ("Integrate", "Connects federal, regional, academic, state, local, and private-sector data streams."),
            ("Translate", "Turns observations and models into forecasts, maps, dashboards, alerts, and APIs."),
            ("Support decisions", "Helps users make navigation, safety, fisheries, hazard, planning, and operations decisions."),
        ]
        card_html = "".join(
            (
                '<div class="overview-card">'
                f"<b>{hub_escape(title)}</b>"
                f"<p>{hub_escape(body)}</p>"
                "</div>"
            )
            for title, body in system_cards
        )
        st.markdown(f'<div class="cost-grid">{card_html}</div>', unsafe_allow_html=True)
    with map_col:
        if IOOS_COVERAGE_MAP_PATH.exists():
            st.image(str(IOOS_COVERAGE_MAP_PATH), caption="IOOS regional coverage", use_container_width=True)
        elif IOOS_OCEAN_SYSTEMS_PATH.exists():
            st.image(str(IOOS_OCEAN_SYSTEMS_PATH), use_container_width=True)
        else:
            st.info("IOOS system image is not available.")


def render_sectors_supported_tab(evidence_df: pd.DataFrame, review_df: pd.DataFrame) -> None:
    st.markdown(
        """
        <p class="overview-intro">
            The economy IOOS supports is not one industry. It is a portfolio of decisions across
            ports, fisheries, emergency response, coastal resilience, ocean technology, and marine
            operations. The counts below are calculated from the current evidence matrix.
        </p>
        """,
        unsafe_allow_html=True,
    )
    sector_df = sector_story_table(evidence_df, review_df)
    card_html = "".join(
        (
            '<div class="sector-card">'
            f'<span class="hub-chip neutral">{int(row["Rows"]):,} rows</span>'
            f'<b>{hub_escape(row["Sector"])}</b>'
            f'<p>{hub_escape(row["Why it matters"])}</p>'
            f'<p><strong>Example:</strong> {hub_escape(row["Example decision"])}</p>'
            "</div>"
        )
        for _, row in sector_df.iterrows()
    )
    st.markdown(f'<div class="sector-grid">{card_html}</div>', unsafe_allow_html=True)

    if not sector_df.empty:
        chart_df = sector_df.set_index("Sector")[["Rows", "External-ready rows"]]
        st.subheader("Sector Coverage In The Matrix")
        st.bar_chart(chart_df)
        st.dataframe(
            sector_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rows": st.column_config.NumberColumn(format="%d", width="small"),
                "Sources": st.column_config.NumberColumn(format="%d", width="small"),
                "External-ready rows": st.column_config.NumberColumn(format="%d", width="small"),
                "Why it matters": st.column_config.TextColumn(width="large"),
                "Example decision": st.column_config.TextColumn(width="large"),
            },
        )


def system_cost_matches(evidence_df: pd.DataFrame, best_sources_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cost_keywords = [
        "appropriation",
        "budget",
        "federal funding",
        "funding level",
        "funding levels",
        "reauthorization",
        "current levels",
        "system cost",
        "program cost",
    ]
    return (
        keyword_filter(evidence_df, cost_keywords, NARRATIVE_TEXT_COLUMNS),
        keyword_filter(best_sources_df, cost_keywords, BEST_SOURCE_TEXT_COLUMNS),
    )


def render_system_cost_tab(evidence_df: pd.DataFrame, best_sources_df: pd.DataFrame) -> None:
    st.markdown(
        """
        <p class="overview-intro">
            This tab is where the app should answer the investment question: what does it currently
            cost to keep IOOS operating, and what return stories can responsibly be compared against
            that cost? Right now the local database does not contain a verified current operating-cost row.
        </p>
        """,
        unsafe_allow_html=True,
    )

    cost_evidence_df, cost_source_df = system_cost_matches(evidence_df, best_sources_df)
    metric_cols = st.columns(3)
    metric_cols[0].metric("Verified current-cost figure", "Pending")
    metric_cols[1].metric("Matching evidence rows", f"{len(cost_evidence_df):,}")
    metric_cols[2].metric("Matching source leads", f"{len(cost_source_df):,}")

    if cost_evidence_df.empty and cost_source_df.empty:
        st.markdown(
            """
            <div class="evidence-empty-state">
                <strong>Cost figure not yet loaded.</strong>
                Add a source-backed row before the app states a current annual cost. Best source candidates
                would be a NOAA budget justification, enacted CJS appropriation, congressional report language,
                IOOS Association funding summary, or official program operating plan.
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info("Potential cost-related records were found. Verify that they are actually about maintaining IOOS before using them as the cost denominator.")

    card_html = "".join(
        (
            '<div class="cost-card">'
            f'<b>{hub_escape(component["name"])}</b>'
            f'<p>{hub_escape(component["description"])}</p>'
            "</div>"
        )
        for component in SYSTEM_COST_COMPONENTS
    )
    st.subheader("What The Cost Needs To Cover")
    st.markdown(f'<div class="cost-grid">{card_html}</div>', unsafe_allow_html=True)

    st.subheader("Database Row To Add")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Needed field": "Current annual operating cost",
                    "What to capture": "Most recent enacted or official current-year IOOS funding level, including what is and is not included.",
                },
                {
                    "Needed field": "Source and dollar year",
                    "What to capture": "Source URL, fiscal year, appropriation or budget line, and whether the number is enacted, requested, or authorized.",
                },
                {
                    "Needed field": "Maintenance scope",
                    "What to capture": "Whether the figure covers Regional Associations, federal program office, sensors, DMAC, models, operations, or only part of the system.",
                },
                {
                    "Needed field": "Use rule",
                    "What to capture": "Whether the figure can be used as a return-on-investment denominator or only as funding context.",
                },
            ]
        ),
        use_container_width=True,
        hide_index=True,
        column_config={"What to capture": st.column_config.TextColumn(width="large")},
    )

    if not cost_evidence_df.empty:
        st.subheader("Potential Cost Evidence Rows")
        st.dataframe(cost_evidence_df, use_container_width=True, hide_index=True)
    if not cost_source_df.empty:
        st.subheader("Potential Cost Source Leads")
        st.dataframe(cost_source_df, use_container_width=True, hide_index=True)


def sort_best_source_matches(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    sorted_df = df.copy()
    sorted_df["_priority_rank"] = sorted_df.get("priority_tier", pd.Series("", index=sorted_df.index)).map(
        lambda value: 0 if normalize_text(value).lower() == "primary" else 1
    )
    sorted_df["_verification_rank"] = sorted_df.get(
        "source_verification_needed",
        pd.Series("", index=sorted_df.index),
    ).map(lambda value: 1 if normalize_text(value).lower() == "yes" else 0)
    return sorted_df.sort_values(["_priority_rank", "_verification_rank", "source_name"]).drop(
        columns=["_priority_rank", "_verification_rank"],
        errors="ignore",
    )


def case_study_cards(best_sources_df: pd.DataFrame, evidence_df: pd.DataFrame, source_df: pd.DataFrame) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    used_keys: set[str] = set()
    evidence_dashboard_df = add_dashboard_fields(evidence_df, pd.DataFrame())

    for theme in CASE_STUDY_THEMES:
        source_matches = sort_best_source_matches(keyword_filter(best_sources_df, theme["keywords"], BEST_SOURCE_TEXT_COLUMNS))
        source_matches = source_matches[
            ~source_matches.get("source_id", pd.Series("", index=source_matches.index)).map(normalize_text).isin(used_keys)
        ]
        if not source_matches.empty:
            row = source_matches.iloc[0]
            key = row_field(row, "source_id", row_field(row, "source_name"))
            used_keys.add(key)
            cards.append(
                {
                    "theme": theme["name"],
                    "title": row_field(row, "source_name", theme["name"]),
                    "metric": row_field(row, "key_metrics", "Metrics pending."),
                    "claim": row_field(row, "recommended_claim_language", row_field(row, "briefing_role")),
                    "caveat": row_field(row, "caveats", "Keep source limitations attached."),
                    "source_url": row_field(row, "source_url"),
                    "status": row_field(row, "source_verification_needed", "Unknown"),
                }
            )
            continue

        evidence_matches = keyword_filter(evidence_dashboard_df, theme["keywords"], NARRATIVE_TEXT_COLUMNS)
        if evidence_matches.empty:
            continue
        row = evidence_matches.iloc[0]
        source_row = source_for_row(row, source_df)
        cards.append(
            {
                "theme": theme["name"],
                "title": row_field(source_row, "source_name", row_field(row, "ioos_component", theme["name"])),
                "metric": row_field(row, "metric", "Metric pending."),
                "claim": row_field(row, "claim_allowed", row_field(row, "decision_supported")),
                "caveat": row_field(row, "limitations", "Keep source limitations attached."),
                "source_url": row_field(source_row, "source_url", row_field(row, "source_url")),
                "status": row_field(row, "source_verification_needed", "Unknown"),
            }
        )
    return cards


def render_return_case_studies_tab(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> None:
    st.markdown(
        """
        <p class="overview-intro">
            Case studies are the clearest way to show return: a named IOOS component, a decision,
            an economic pathway, a metric, a source, and a caveat. These cards are selected from
            the current best-source shortlist first, then from promoted evidence rows if needed.
        </p>
        """,
        unsafe_allow_html=True,
    )
    cards = case_study_cards(best_sources_df, evidence_df, source_df)
    if not cards:
        st.info("No case-study records are available yet.")
        return

    card_html = "".join(
        (
            '<div class="case-card">'
            f'<span class="hub-chip {"warning" if card["status"] == "Yes" else "neutral"}">{hub_escape(card["theme"])}</span>'
            f'<b>{hub_escape(card["title"])}</b>'
            f'<p><strong>Metric:</strong> {hub_escape(truncate_text(card["metric"], 220))}</p>'
            f'<p><strong>Use claim:</strong> {hub_escape(truncate_text(card["claim"], 230))}</p>'
            f'<p><strong>Caveat:</strong> {hub_escape(truncate_text(card["caveat"], 210))}</p>'
            + (
                f'<a class="overview-link" href="{hub_escape(card["source_url"])}" target="_blank" rel="noopener">Open source</a>'
                if card["source_url"]
                else ""
            )
            + "</div>"
        )
        for card in cards
    )
    st.markdown(f'<div class="case-grid">{card_html}</div>', unsafe_allow_html=True)

    st.subheader("Best-Source Shortlist")
    if best_sources_df.empty:
        st.info("No best_sources.csv table is loaded.")
    else:
        display_columns = [
            column
            for column in [
                "source_name",
                "source_type",
                "ioos_region_code",
                "priority_tier",
                "impact_domains",
                "key_metrics",
                "recommended_claim_language",
                "caveats",
                "source_url",
            ]
            if column in best_sources_df.columns
        ]
        st.dataframe(
            best_sources_df[display_columns],
            use_container_width=True,
            hide_index=True,
            column_config={
                "source_url": st.column_config.LinkColumn("Source URL"),
                "key_metrics": st.column_config.TextColumn(width="large"),
                "recommended_claim_language": st.column_config.TextColumn(width="large"),
                "caveats": st.column_config.TextColumn(width="large"),
            },
        )


def render_how_we_work_tab(
    evidence_df: pd.DataFrame,
    review_df: pd.DataFrame,
    staged_df: pd.DataFrame,
    source_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> None:
    st.markdown(
        """
        <p class="overview-intro">
            The app is intentionally conservative. AI can help discover candidate evidence, but the
            official matrix only gets rows after source, attribution, limitation, and claim-language review.
        </p>
        """,
        unsafe_allow_html=True,
    )

    method_cards = [
        ("1. Collect", "Gather source leads, metrics, claims, regions, user groups, and decision pathways."),
        ("2. Stage", "Hold AI-assisted or newly imported evidence outside the official matrix."),
        ("3. Review", "Check source support, attribution strength, limitations, and claim language."),
        ("4. Promote", "Move verified rows into the official evidence matrix with durable IDs."),
        ("5. Use", "Export trusted claims, case studies, citations, and briefing materials."),
        ("6. Update", "Run validation, clear review items, and refresh source records as evidence changes."),
    ]
    card_html = "".join(
        (
            '<div class="method-card">'
            f"<b>{hub_escape(title)}</b>"
            f"<p>{hub_escape(body)}</p>"
            "</div>"
        )
        for title, body in method_cards
    )
    st.markdown(f'<div class="method-grid">{card_html}</div>', unsafe_allow_html=True)

    data_col, rubric_col = st.columns([0.95, 1.05], gap="large")
    with data_col:
        st.subheader("Data Layers")
        st.dataframe(
            project_table_status(evidence_df, source_df, review_df, staged_df, best_sources_df),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rows": st.column_config.NumberColumn(format="%d", width="small"),
                "Purpose": st.column_config.TextColumn(width="large"),
            },
        )
    with rubric_col:
        st.subheader("Trust Signals")
        sample_rows = [
            pd.Series(
                {
                    "evidence_strength": "Strong",
                    "ioos_attribution_strength": "Strong",
                    "dashboard_status": "report-ready",
                }
            ),
            pd.Series(
                {
                    "evidence_strength": "Modeled",
                    "ioos_attribution_strength": "Medium",
                    "dashboard_status": "use-with-caution",
                }
            ),
            pd.Series(
                {
                    "evidence_strength": "Needs verification",
                    "ioos_attribution_strength": "Contextual",
                    "dashboard_status": "needs-follow-up",
                }
            ),
        ]
        trust_examples = "".join(
            (
                '<div class="metric-panel">'
                f"<b>{hub_escape(status_definition(row_review_status(row))[0])}</b>"
                "<span>Evidence strength, IOOS attribution, and review status travel with every reusable claim.</span>"
                f"{trust_signal_cluster_html(row)}"
                "</div>"
            )
            for row in sample_rows
        )
        st.markdown(f'<div class="trust-demo-grid">{trust_examples}</div>', unsafe_allow_html=True)

    rubric_col, attribution_col = st.columns(2, gap="large")
    with rubric_col:
        st.subheader("Evidence Strength Rubric")
        strength_rows = []
        for key in ["strong", "medium", "modeled", "contextual", "needs verification"]:
            label, description, _ = STRENGTH_DEFINITIONS[key]
            strength_rows.append({"Rating": label, "How to interpret it": description})
        st.dataframe(pd.DataFrame(strength_rows), use_container_width=True, hide_index=True)

    with attribution_col:
        st.subheader("IOOS Attribution Rubric")
        attribution_rows = []
        for key in ["strong", "medium", "modeled", "contextual", "needs verification"]:
            label, active_count, description = ATTRIBUTION_DEFINITIONS[key]
            attribution_rows.append(
                {
                    "Level": label,
                    "Chain depth": f"{active_count} of 5 layers",
                    "How to interpret it": description,
                }
            )
        st.dataframe(pd.DataFrame(attribution_rows), use_container_width=True, hide_index=True)


def page_about_data(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    review_df: pd.DataFrame,
    staged_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> None:
    st.markdown(
        """
        <p class="overview-intro">
            Use these tabs as the app's front door. They explain the system first, then move from
            sectors, to cost, to return evidence, to the workflow that keeps claims defensible.
        </p>
        """,
        unsafe_allow_html=True,
    )

    system_tab, sectors_tab, cost_tab, cases_tab, workflow_tab = st.tabs(
        NARRATIVE_TAB_LABELS
    )

    with system_tab:
        render_ioos_system_tab(evidence_df, source_df, review_df, staged_df)
    with sectors_tab:
        render_sectors_supported_tab(evidence_df, review_df)
    with cost_tab:
        render_system_cost_tab(evidence_df, best_sources_df)
    with cases_tab:
        render_return_case_studies_tab(evidence_df, source_df, best_sources_df)
    with workflow_tab:
        render_how_we_work_tab(evidence_df, review_df, staged_df, source_df, best_sources_df)


def page_how_to_use() -> None:
    st.title("How to Use")
    st.caption("The main workflows for employees using the IOOS Economic Impact Hub.")

    role_rows = [
        {"Role": role, "Primary use": description}
        for role, description in APP_ROLES.items()
    ]
    st.dataframe(pd.DataFrame(role_rows), use_container_width=True, hide_index=True)

    viewer_tab, contributor_tab, reviewer_tab, export_tab = st.tabs(
        ["Explore", "Add Data", "Review", "Export"]
    )

    with viewer_tab:
        st.subheader("Explore Trusted Evidence")
        st.write("Start on the Dashboard to see readiness and workload. Use Data Explorer to search by domain, region, source, strength rating, or claim language.")
        st.write("Open a record before copying a number. The detail view keeps the metric, allowed claim, limitation, and source together.")
        if IOOS_COVERAGE_MAP_PATH.exists():
            st.image(str(IOOS_COVERAGE_MAP_PATH), use_container_width=True)

    with contributor_tab:
        st.subheader("Add Candidate Evidence")
        st.write("Use Evidence Intake for research prompts and candidate CSV uploads. New AI-assisted rows belong in Staged Evidence until their sources are checked.")
        st.write("If adding a single verified row directly, use Add Evidence Row and then run validation.")
        st.dataframe(pd.DataFrame(METHOD_STEPS), use_container_width=True, hide_index=True)

    with reviewer_tab:
        st.subheader("Review and Promote")
        st.write("Use Review Needed to clear validation warnings and Staged Evidence to approve rows whose source verification is complete.")
        st.write("Keep limitations attached to claims, especially when evidence is modeled, contextual, or older.")
        if IOOS_OCEAN_SYSTEMS_PATH.exists():
            st.image(str(IOOS_OCEAN_SYSTEMS_PATH), use_container_width=True)

    with export_tab:
        st.subheader("Create Reusable Outputs")
        st.write("Use each table's download button for CSV exports. Use Best Sources and Congressional Brief for communication-ready source shortlists and brief drafts.")
        st.write("Before using data externally, confirm the row is report-ready or preserve its caveats in the exported material.")


def page_review_needed(review_df: pd.DataFrame) -> None:
    st.title("Review Needed")
    if not REVIEW_PATH.exists():
        st.info("No review_needed.csv found. Run validation first.")
        return
    if review_df.empty:
        st.success("Validation review file exists and contains no flagged rows.")
        return
    st.dataframe(review_df, use_container_width=True, hide_index=True)
    st.download_button(
        "Download review_needed.csv",
        review_df.to_csv(index=False).encode("utf-8"),
        file_name="review_needed.csv",
        mime="text/csv",
    )


def page_source_registry(source_df: pd.DataFrame) -> None:
    st.title("Source Registry")
    if source_df.empty:
        st.warning(f"No source registry found at {SOURCE_PATH}")
        return

    search_text = st.text_input("Search sources", key="source_search")
    filtered = search_dataframe(source_df, search_text)
    filtered = add_multiselect_filter(filtered, "source_type", "Source Type")
    filtered = add_multiselect_filter(filtered, "verification_status", "Verification Status")

    st.caption(f"Showing {len(filtered):,} of {len(source_df):,} sources")
    column_config = {}
    if "source_url" in filtered.columns:
        column_config["source_url"] = st.column_config.LinkColumn("Source URL")
    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
    )


def page_best_sources(best_sources_df: pd.DataFrame) -> None:
    st.markdown(
        """
        <div class="hub-page-title">
            <div class="hub-kicker">Curated source shelf</div>
            <h1>Best Sources</h1>
            <p>Profile the highest-value studies and reports before pulling them into briefs, reports, or regional case studies.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if best_sources_df.empty:
        st.warning(f"No best sources table found at {BEST_SOURCES_PATH}")
        return

    primary_count = (
        int((best_sources_df["priority_tier"].map(normalize_text) == "primary").sum())
        if "priority_tier" in best_sources_df.columns
        else 0
    )
    verified_count = (
        int((best_sources_df["source_verification_needed"].map(normalize_text) == "No").sum())
        if "source_verification_needed" in best_sources_df.columns
        else 0
    )
    planned_count = (
        int((best_sources_df["status"].map(normalize_text) == "planned").sum())
        if "status" in best_sources_df.columns
        else 0
    )

    metric_columns = st.columns(4)
    metric_columns[0].metric("Shortlist sources", f"{len(best_sources_df):,}")
    metric_columns[1].metric("Primary tier", f"{primary_count:,}")
    metric_columns[2].metric("Verified", f"{verified_count:,}")
    metric_columns[3].metric("Planned", f"{planned_count:,}")

    search_text = st.text_input("Search best sources", key="best_sources_search")
    filtered = search_dataframe(best_sources_df, search_text)
    filtered = add_multiselect_filter(filtered, "ioos_region_code", "IOOS Region Code")
    filtered = add_multiselect_filter(filtered, "priority_tier", "Priority Tier")
    filtered = add_multiselect_filter(filtered, "source_type", "Source Type")
    filtered = add_multiselect_filter(filtered, "source_verification_needed", "Verification Needed")
    filtered = add_multiselect_filter(filtered, "status", "Status")

    st.caption(f"Showing {len(filtered):,} of {len(best_sources_df):,} sources")
    if not filtered.empty:
        profile_cards = []
        for _, row in filtered.head(6).iterrows():
            verification = "Verification needed" if row_field(row, "source_verification_needed") == "Yes" else "Verified source"
            caveats = row_field(row, "caveats", "No limitations recorded.")
            source_url = row_field(row, "source_url")
            source_link = (
                f'<a href="{hub_escape(source_url)}" target="_blank" rel="noopener">Open source</a>'
                if source_url
                else "Source link pending"
            )
            profile_cards.append(
                f"""
                <div class="source-profile">
                    <span class="hub-chip {'warning' if row_field(row, 'source_verification_needed') == 'Yes' else ''}">{hub_escape(verification)}</span>
                    <b>{hub_escape(row_field(row, "source_name", row_field(row, "source_id", "Untitled source")))}</b>
                    <span>{hub_escape(row_field(row, "source_type", "Source type pending"))} / {hub_escape(row_field(row, "ioos_region_code", "Region pending"))}</span>
                    <div class="detail-section">
                        <b>What it covers</b>
                        <p>{hub_escape(row_field(row, "briefing_role", row_field(row, "impact_domains", "Coverage pending.")))}</p>
                    </div>
                    <div class="detail-section">
                        <b>Headline numbers</b>
                        <p>{hub_escape(row_field(row, "key_metrics", "Metrics pending."))}</p>
                    </div>
                    <div class="detail-section">
                        <b>Strengths / limitations</b>
                        <p>{hub_escape(row_field(row, "evidence_profile", ""))} {hub_escape(caveats)}</p>
                    </div>
                    <div class="detail-section">
                        <b>Claims citing it</b>
                        <p>{hub_escape(row_field(row, "staged_row_ids", "Claim links pending."))}</p>
                        <p>{source_link}</p>
                    </div>
                </div>
                """
            )
        st.markdown(f'<div class="source-grid">{"".join(profile_cards)}</div>', unsafe_allow_html=True)
        st.divider()

    column_config = {
        "source_url": st.column_config.LinkColumn("Source URL"),
        "briefing_role": st.column_config.TextColumn(width="large"),
        "key_metrics": st.column_config.TextColumn(width="large"),
        "recommended_claim_language": st.column_config.TextColumn(width="large"),
        "caveats": st.column_config.TextColumn(width="large"),
    }
    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True,
        column_config={
            column: config for column, config in column_config.items() if column in filtered.columns
        },
    )
    st.download_button(
        "Download best_sources.csv",
        filtered.to_csv(index=False).encode("utf-8"),
        file_name="best_sources.csv",
        mime="text/csv",
    )


def page_congressional_briefing(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    staged_df: pd.DataFrame,
    best_sources_df: pd.DataFrame | None = None,
) -> None:
    st.markdown(
        """
        <div class="hub-page-title">
            <div class="hub-kicker">Briefs & Outputs</div>
            <h1>Claim Basket And Exports</h1>
            <p>Select trusted claims, generate copy-ready citation blocks, preview a congressional one-pager, and download reusable evidence exports.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if evidence_df.empty:
        st.warning("No evidence matrix rows are available for the national brief preview.")

    brief_metric_sources_df = best_sources_df if best_sources_df is not None else source_df
    export_df = enrich_evidence_with_source_fields(evidence_df, source_df)
    export_df = add_dashboard_fields(export_df, pd.DataFrame())
    ready_df = export_df[export_df.apply(is_external_ready_row, axis=1)].copy()
    basket_source = ready_df if not ready_df.empty else export_df

    prepared_cols = st.columns([1, 1, 1])
    prepared_for = prepared_cols[0].text_input("Prepared for", value="Congressional Staff")
    prepared_date = prepared_cols[1].date_input("Brief date", value=date.today())
    basket_mode = prepared_cols[2].selectbox("Basket starter", ["Ready external claims", "Briefing default rows", "All promoted rows"])

    if basket_mode == "Briefing default rows" and "row_id" in export_df.columns:
        default_ids = [row_id for row_id in BRIEFING_ROW_IDS.values() if row_id in set(export_df["row_id"].map(normalize_text))]
        option_df = export_df
    elif basket_mode == "All promoted rows":
        option_df = export_df
        default_ids = option_df["row_id"].map(normalize_text).head(4).tolist() if "row_id" in option_df else []
    else:
        option_df = basket_source
        default_ids = option_df["row_id"].map(normalize_text).head(4).tolist() if "row_id" in option_df else []

    option_labels: dict[str, str] = {}
    for _, row in option_df.iterrows():
        row_id = row_field(row, "row_id")
        if row_id:
            option_labels[row_id] = f"{row_id} - {truncate_text(row_field(row, 'claim_allowed', row_field(row, 'metric')), 92)}"

    selected_ids = st.multiselect(
        "Claim basket",
        list(option_labels),
        default=[row_id for row_id in default_ids if row_id in option_labels],
        format_func=lambda row_id: option_labels.get(row_id, row_id),
    )
    basket_df = option_df[option_df["row_id"].map(normalize_text).isin(selected_ids)].copy() if selected_ids else option_df.head(0)

    basket_tab, one_pager_tab, source_tab, generated_tab, maracoos_tab = st.tabs(
        ["Claim Basket", "One-Pager Preview", "Citation List", "Generated Brief", "MARACOOS"]
    )

    with basket_tab:
        if basket_df.empty:
            st.info("No claims are in the basket. Select one or more promoted evidence rows above.")
        else:
            copy_blocks = [
                claim_copy_block(row, source_df)
                for _, row in basket_df.iterrows()
            ]
            basket_text = "\n\n---\n\n".join(copy_blocks)
            st.subheader("Copy-Ready Claim Blocks")
            render_copy_button(basket_text, "Copy basket")
            st.text_area("Claim + citation blocks", value=basket_text, height=360)
            st.download_button(
                "Download basket text",
                basket_text.encode("utf-8"),
                file_name="ioos_claim_basket.txt",
                mime="text/plain",
            )
            st.download_button(
                "Download basket CSV",
                basket_df.to_csv(index=False).encode("utf-8"),
                file_name="ioos_claim_basket.csv",
                mime="text/csv",
            )
            st.dataframe(
                evidence_display_dataframe(basket_df),
                use_container_width=True,
                hide_index=True,
                column_config={"source_url": st.column_config.LinkColumn("Source URL")}
                if "source_url" in basket_df.columns
                else {},
            )

    with one_pager_tab:
        if basket_df.empty:
            st.info("Add claims to the basket to preview a one-pager.")
        else:
            number_blocks = "".join(
                f"""
                <div class="brief-number">
                    <b>{hub_escape(truncate_text(row_field(row, "metric"), 90))}</b>
                    <span>{hub_escape(row_field(row, "claim_allowed"))}</span>
                </div>
                """
                for _, row in basket_df.head(4).iterrows()
            )
            source_line = "; ".join(
                sorted(
                    {
                        row_field(source_for_row(row, source_df), "source_name", row_field(row, "source_id"))
                        for _, row in basket_df.iterrows()
                        if row_field(row, "source_id")
                    }
                )
            )
            st.markdown(
                f"""
                <div class="brief-preview">
                    <div class="hub-kicker">Congressional one-pager preview</div>
                    <h2>IOOS Economic Impact Evidence</h2>
                    <p style="color:#405760;line-height:1.55;margin:0;">Prepared for {hub_escape(prepared_for)} on {hub_escape(prepared_date.strftime('%B %d, %Y'))}. Claims below are selected from promoted evidence rows and should retain their limitations when quoted.</p>
                    {number_blocks}
                    <div class="detail-section">
                        <b>Source shelf</b>
                        <p>{hub_escape(source_line or "Sources pending.")}</p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with source_tab:
        if basket_df.empty:
            st.info("No citation list is available until the basket has claims.")
        else:
            citation_rows = []
            for _, row in basket_df.iterrows():
                source_row = source_for_row(row, source_df)
                citation_rows.append(
                    {
                        "row_id": row_field(row, "row_id"),
                        "source": row_field(source_row, "source_name", row_field(row, "source_id")),
                        "source_type": row_field(source_row, "source_type", row_field(row, "source_type")),
                        "source_url": row_field(source_row, "source_url", row_field(row, "source_url")),
                        "evidence_strength": row_field(row, "evidence_strength"),
                        "ioos_attribution_strength": row_field(row, "ioos_attribution_strength"),
                        "limitations": row_field(row, "limitations"),
                    }
                )
            citation_df = pd.DataFrame(citation_rows)
            st.dataframe(
                citation_df,
                use_container_width=True,
                hide_index=True,
                column_config={"source_url": st.column_config.LinkColumn("Source URL")},
            )
            citation_text = "\n".join(
                f"{row['row_id']}: {row['source']}. {row['source_type']}. {row['source_url']}"
                for row in citation_rows
            )
            st.download_button(
                "Download citation list",
                citation_text.encode("utf-8"),
                file_name="ioos_citations.txt",
                mime="text/plain",
            )

    with generated_tab:
        briefing_html = build_congressional_briefing_html(
            evidence_df,
            source_df,
            prepared_for,
            prepared_date,
            brief_metric_sources_df,
        )
        components.html(briefing_html, height=1700, scrolling=True)
        st.download_button(
            "Download live congressional brief HTML",
            briefing_html.encode("utf-8"),
            file_name="ioos_congressional_brief_live.html",
            mime="text/html",
        )
        if st.button("Build PDF export"):
            try:
                briefing_pdf = build_congressional_briefing_pdf(
                    evidence_df,
                    source_df,
                    prepared_for,
                    prepared_date,
                    brief_metric_sources_df,
                )
            except Exception as exc:
                st.warning(f"PDF export is unavailable: {exc}")
            else:
                st.download_button(
                    "Download live congressional brief PDF",
                    briefing_pdf,
                    file_name="ioos_congressional_brief_live.pdf",
                    mime="application/pdf",
                )

        if FILLED_BRIEFING_PATH.exists():
            st.download_button(
                "Download generated congressional brief draft",
                briefing_html.encode("utf-8"),
                file_name=FILLED_BRIEFING_PATH.name,
                mime="text/html",
            )

    with maracoos_tab:
        render_maracoos_congressional_tab(evidence_df, staged_df, prepared_for, prepared_date)


def render_intake_upload() -> None:
    st.subheader("Import Candidate CSV")
    if supabase_enabled():
        st.caption("Storage: Supabase live tables, with local CSV mirror.")
    else:
        missing = "; ".join(supabase_missing_settings())
        st.warning(f"Supabase upload is not configured in this runtime. Missing: {missing}.")

    uploaded_file = st.file_uploader("Upload AI-generated candidate rows", type=["csv"])
    if uploaded_file is None:
        return

    file_bytes = uploaded_file.getvalue()
    csv_shape_errors = validate_intake_csv_shape(file_bytes)
    if csv_shape_errors:
        st.error("Candidate CSV was not staged.")
        st.write("Fix these issues and upload again:")
        for error in csv_shape_errors:
            st.write(f"- {error}")
        return

    try:
        candidate_df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
    except Exception as exc:
        st.error(f"Could not read CSV: {exc}")
        return

    errors = validate_intake_df(candidate_df)
    if errors:
        st.error("Candidate CSV was not staged.")
        st.write("Fix these issues and upload again:")
        for error in errors:
            st.write(f"- {error}")
        return

    normalized = normalize_intake_df(candidate_df)
    st.success(f"CSV passed intake validation with {len(normalized):,} candidate rows.")
    st.dataframe(normalized, use_container_width=True, hide_index=True)

    if supabase_enabled():
        if st.button(f"Upload {len(normalized):,} rows to Supabase staged_evidence", type="primary"):
            try:
                append_rows(STAGED_EVIDENCE_PATH, normalized.to_dict("records"), INTAKE_SCHEMA)
            except Exception as exc:
                st.error(f"Supabase upload failed: {exc}")
                return
            else:
                clear_data_cache()
                st.success(f"Uploaded {len(normalized):,} candidate rows to Supabase staged_evidence.")
    else:
        st.button("Upload rows to Supabase staged_evidence", disabled=True, type="primary")
        if st.button(f"Save {len(normalized):,} rows to local staged_evidence.csv only"):
            try:
                append_rows(STAGED_EVIDENCE_PATH, normalized.to_dict("records"), INTAKE_SCHEMA)
            except Exception as exc:
                st.error(f"Local CSV save failed: {exc}")
                return
            else:
                clear_data_cache()
                st.success(f"Saved {len(normalized):,} candidate rows to local staged_evidence.csv.")

    st.caption("Open Staged Evidence in the sidebar to review, edit, and accept verified rows.")


def render_ai_staging_comparison(staged_df: pd.DataFrame, review_df: pd.DataFrame) -> None:
    st.subheader("AI Staging Comparison")
    if staged_df.empty:
        st.markdown(
            """
            <div class="hub-callout">
                No staged rows are waiting. When AI-extracted candidates arrive, this panel compares the extracted row against source support and validation warnings before promotion.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    staged_normalized = normalize_intake_df(staged_df)
    labels = [
        f"{row_field(row, 'row_id', f'Candidate {index + 1}')} - {truncate_text(row_field(row, 'Claim allowed', row_field(row, 'Metric')), 70)}"
        for index, row in staged_normalized.iterrows()
    ]
    selected_label = st.selectbox("Candidate row", labels)
    selected_index = labels.index(selected_label)
    row = staged_normalized.iloc[selected_index]
    row_id = row_field(row, "row_id")
    warnings = (
        review_df[review_df["row_id"].map(normalize_text) == row_id]
        if row_id and not review_df.empty and "row_id" in review_df.columns
        else pd.DataFrame()
    )
    warning_text = "; ".join(warnings.get("message", pd.Series(dtype=str)).map(normalize_text).head(4)) or "No validation warnings are currently attached to this row."

    st.markdown(
        f"""
        <div class="comparison-grid">
            <div class="comparison-pane">
                <span class="ai-label">Machine-drafted</span>
                <h3>Extracted Evidence Row</h3>
                <p><b>Claim</b><br>{hub_escape(row_field(row, "Claim allowed", "Claim pending."))}</p>
                <p><b>Metric</b><br>{hub_escape(row_field(row, "Metric", "Metric pending."))}</p>
                <p><b>Strength / attribution</b><br>{hub_escape(row_field(row, "Evidence strength", "Unrated"))} / {hub_escape(row_field(row, "IOOS attribution strength", "Unrated"))}</p>
            </div>
            <div class="comparison-pane">
                <h3>Source Support And Review Notes</h3>
                <p><b>Source</b><br>{hub_escape(row_field(row, "Source", "Source pending."))}</p>
                <p><b>Source URL</b><br>{hub_escape(row_field(row, "Source URL", "URL pending."))}</p>
                <p><b>Warnings</b><br>{hub_escape(warning_text)}</p>
                <p><b>Limitations</b><br>{hub_escape(row_field(row, "Limitations", "Limitations pending."))}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def review_claim_label(row: pd.Series, index: int) -> str:
    row_id = row_field(row, "row_id", f"Candidate {index + 1}")
    claim = row_field(row, "Claim allowed", row_field(row, "Metric", "Claim pending"))
    return f"{row_id} - {truncate_text(claim, 86)}"


def render_claim_source_review(staged_df: pd.DataFrame, best_sources_df: pd.DataFrame) -> None:
    st.subheader("Source Review")

    if not STAGED_EVIDENCE_PATH.exists() and staged_df.empty:
        st.info("No staged evidence file exists yet. Use Evidence Intake to stage candidate rows.")
        return

    pending = pending_source_review_rows(staged_df)
    if pending.empty:
        st.success("No generated claims are waiting for source verification.")
        if not best_sources_df.empty:
            st.caption(f"{len(best_sources_df):,} rows are already available in best_sources.")
        return

    total_staged = len(normalize_intake_df(staged_df))
    verified_sources = (
        int((best_sources_df["source_verification_needed"].map(normalize_text) == "No").sum())
        if not best_sources_df.empty and "source_verification_needed" in best_sources_df.columns
        else 0
    )
    metric_columns = st.columns(3)
    metric_columns[0].metric("Generated claims waiting", f"{len(pending):,}")
    metric_columns[1].metric("Total staged claims", f"{total_staged:,}")
    metric_columns[2].metric("Verified best sources", f"{verified_sources:,}")

    options = [int(index) for index in pending.index.tolist()]
    current_index = st.session_state.get("review_claim_row_index", options[0])
    if current_index not in options:
        current_index = options[0]
        st.session_state["review_claim_row_index"] = current_index

    selected_index = st.selectbox(
        "Generated claim",
        options,
        index=options.index(current_index),
        format_func=lambda index: review_claim_label(pending.loc[index], index),
        key="review_claim_row_index",
    )
    row = pending.loc[selected_index]

    claim = row_field(row, "Claim allowed", row_field(row, "Metric", "Claim pending."))
    source_name = row_field(row, "Source", "Source pending")
    source_url = row_field(row, "Source URL")
    source_link = (
        f'<a class="source-review-link" href="{hub_escape(source_url)}" target="_blank" rel="noopener">Open source link</a>'
        if source_url
        else '<span class="source-review-missing">No source link is recorded.</span>'
    )
    row_id = row_field(row, "row_id", "Candidate row")

    st.markdown(
        f"""
        <div class="claim-review-panel">
            <div class="claim-review-topline">
                <span class="ai-label">Generated claim</span>
                <span class="hub-chip warning">{hub_escape(row_id)}</span>
            </div>
            <div class="claim-review-main">
                <div>
                    <h2>{hub_escape(claim)}</h2>
                    <p><b>Metric:</b> {hub_escape(row_field(row, "Metric", "Metric pending."))}</p>
                    <p><b>Source:</b> {hub_escape(source_name)}</p>
                </div>
                <div class="source-review-box">
                    <b>Verify this source</b>
                    {source_link}
                </div>
            </div>
            <div class="claim-review-meta">
                <div><b>Evidence</b>{hub_escape(row_field(row, "Evidence strength", "Unrated"))}</div>
                <div><b>IOOS attribution</b>{hub_escape(row_field(row, "IOOS attribution strength", "Unrated"))}</div>
                <div><b>Region</b>{hub_escape(row_field(row, "IOOS region code", "Unknown"))}</div>
            </div>
            <p><b>Limitations:</b> {hub_escape(row_field(row, "Limitations", "No limitations recorded."))}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="claim-review-actions-marker"></div>', unsafe_allow_html=True)
    verify_column, reject_column = st.columns(2)
    with verify_column:
        if st.button("Yes - verified source", type="primary", use_container_width=True, key=f"verify_source_{selected_index}"):
            try:
                records, source_id = upsert_best_source_from_staged_row(row, best_sources_df)
                write_csv(BEST_SOURCES_PATH, records, BEST_SOURCE_SCHEMA)
                review_note = f"Source verified on {date.today().isoformat()}; copied to best_sources as {source_id}."
                updated_staged = update_staged_review_row(staged_df, selected_index, "No", review_note)
                write_csv(STAGED_EVIDENCE_PATH, updated_staged.to_dict("records"), INTAKE_SCHEMA)
            except Exception as exc:
                st.error(f"Could not save verification: {exc}")
            else:
                st.session_state.pop("review_rejection_row_index", None)
                clear_data_cache()
                st.success(f"Verified {row_id} and copied the source record to best_sources.")
                st.rerun()

    with reject_column:
        if st.button("No - not verified", use_container_width=True, key=f"reject_source_{selected_index}"):
            st.session_state["review_rejection_row_index"] = selected_index
            st.rerun()

    if st.session_state.get("review_rejection_row_index") == selected_index:
        with st.form(f"reject_source_reason_{selected_index}"):
            st.warning("Tell future reviewers why this source should not be trusted for the claim.")
            reason = st.selectbox("Reason", REJECTION_REASON_OPTIONS)
            details = st.text_area(
                "Reviewer note",
                placeholder="Add page numbers, missing evidence, broken-link detail, or the corrected metric if you found one.",
                height=120,
            )
            save_rejection = st.form_submit_button("Save rejection reason", type="primary")
            cancel_rejection = st.form_submit_button("Cancel")

        if cancel_rejection:
            st.session_state.pop("review_rejection_row_index", None)
            st.rerun()

        if save_rejection:
            if reason == "Other" and not normalize_text(details):
                st.error("Add a short note when the reason is Other.")
                return
            review_note = f"Source rejected on {date.today().isoformat()}: {reason}."
            if normalize_text(details):
                review_note = f"{review_note} {normalize_text(details)}"
            try:
                updated_staged = update_staged_review_row(staged_df, selected_index, "Yes", review_note)
                write_csv(STAGED_EVIDENCE_PATH, updated_staged.to_dict("records"), INTAKE_SCHEMA)
            except Exception as exc:
                st.error(f"Could not save rejection: {exc}")
            else:
                st.session_state.pop("review_rejection_row_index", None)
                clear_data_cache()
                st.success(f"Saved rejection reason for {row_id}.")
                st.rerun()


def page_regional_builds(regional_targets_df: pd.DataFrame, evidence_df: pd.DataFrame) -> None:
    st.title("Regional Builds")
    st.caption("Work one IOOS region at a time, starting with MARACOOS, before promoting verified rows into the master matrix.")

    if regional_targets_df.empty:
        st.warning(f"No regional research targets found at {REGIONAL_TARGETS_PATH}")
        return

    target = selected_regional_target(regional_targets_df, "regional_build_target")
    if target is None:
        return

    st.info(
        "Use the regional target table to plan research. Add new master evidence rows only after "
        "candidate rows have sources, limitations, attribution ratings, and human verification."
    )

    target_df = pd.DataFrame([target.to_dict()])
    st.subheader("Regional Target")
    st.dataframe(target_df, use_container_width=True, hide_index=True)

    matched_evidence = evidence_rows_for_regional_target(evidence_df, target)
    st.subheader("Current Master Rows Matching This Region")
    if matched_evidence.empty:
        st.write("No current master evidence rows match this regional target yet.")
    else:
        display = matched_evidence[
            [
                column
                for column in [
                    "row_id",
                    "impact_domain",
                    "ioos_component",
                    "region",
                    "ioos_region_code",
                    "metric",
                    "evidence_strength",
                    "ioos_attribution_strength",
                    "source_verification_needed",
                    "claim_allowed",
                ]
                if column in matched_evidence.columns
            ]
        ]
        st.dataframe(display, use_container_width=True, hide_index=True)

    st.subheader("Copy-Ready Regional Research Prompt")
    rows_requested = st.number_input(
        "Candidate rows to request",
        min_value=3,
        max_value=20,
        value=8,
        step=1,
    )
    research_focus = st.text_area(
        "Research focus",
        value=normalize_text(target.get("starter_research_question")),
        height=110,
    )
    source_leads = st.text_area(
        "Optional source leads",
        placeholder="Paste regional association, NOAA, USCG, state agency, port, academic, or economic baseline links here.",
        height=150,
    )
    prompt = regional_research_prompt(target, research_focus, source_leads, int(rows_requested))
    st.text_area("Copy-ready regional prompt", value=prompt, height=760)
    st.download_button(
        "Download regional prompt",
        prompt.encode("utf-8"),
        file_name=f"ioos_{normalize_text(target.get('region_id')) or 'regional'}_research_prompt.txt",
        mime="text/plain",
    )

    st.download_button(
        "Download regional target table",
        regional_targets_df.to_csv(index=False).encode("utf-8"),
        file_name="regional_research_targets.csv",
        mime="text/csv",
    )


def page_evidence_intake(regional_targets_df: pd.DataFrame) -> None:
    st.title("Evidence Intake")
    st.caption("Generate copy-ready prompts, then stage AI candidate rows before they become official evidence.")
    with st.expander("Claim-use classification guide", expanded=False):
        st.write("Use these fields to separate hard-dollar evidence from context, operations, and backend data-source attribution.")
        st.markdown(
            "\n".join(
                [
                    f"- **Economic number type:** {allowed_economic_number_types_text()}",
                    f"- **IOOS role type:** {allowed_ioos_role_types_text()}",
                    "- **Allowed use:** the strongest claim the row can safely support.",
                    "- **Not allowed use:** the overclaim the row should prevent.",
                ]
            )
        )

    research_tab, regional_tab, source_tab, claude_tab, import_tab = st.tabs(
        ["Research Topic", "Regional Build Prompt", "Add Source", "Claude Batch Prompt", "Import CSV"]
    )

    with research_tab:
        topic = st.text_area("Research question or topic", placeholder="Find 5 new evidence rows on HF radar and search and rescue.")
        prompt = research_prompt(topic)
        st.text_area("Copy-ready research prompt", value=prompt, height=420)
        st.download_button(
            "Download prompt",
            prompt.encode("utf-8"),
            file_name="ioos_research_to_row_prompt.txt",
            mime="text/plain",
        )

    with regional_tab:
        if regional_targets_df.empty:
            st.warning(f"No regional research targets found at {REGIONAL_TARGETS_PATH}")
        else:
            target = selected_regional_target(regional_targets_df, "intake_regional_target")
            if target is not None:
                rows_requested = st.number_input(
                    "Candidate rows to request",
                    min_value=3,
                    max_value=20,
                    value=8,
                    step=1,
                    key="intake_regional_rows",
                )
                research_focus = st.text_area(
                    "Research focus",
                    value=normalize_text(target.get("starter_research_question")),
                    height=110,
                    key="intake_regional_focus",
                )
                source_leads = st.text_area(
                    "Optional source leads",
                    placeholder="Paste regional association, NOAA, USCG, state agency, port, academic, or economic baseline links here.",
                    height=140,
                    key="intake_regional_sources",
                )
                prompt = regional_research_prompt(target, research_focus, source_leads, int(rows_requested))
                st.text_area("Copy-ready regional prompt", value=prompt, height=620)
                st.download_button(
                    "Download regional prompt",
                    prompt.encode("utf-8"),
                    file_name=f"ioos_{normalize_text(target.get('region_id')) or 'regional'}_research_prompt.txt",
                    mime="text/plain",
                )

    with source_tab:
        source_text = st.text_area(
            "Source URL, title, report text, abstract, or excerpt",
            placeholder="Paste a NOAA report URL, title, abstract, or excerpt.",
            height=180,
        )
        prompt = source_prompt(source_text)
        st.text_area("Copy-ready source extraction prompt", value=prompt, height=420)
        st.download_button(
            "Download prompt",
            prompt.encode("utf-8"),
            file_name="ioos_source_to_row_prompt.txt",
            mime="text/plain",
        )

    with claude_tab:
        source_links = st.text_area(
            "Paper or report links",
            placeholder=(
                "https://tidesandcurrents.noaa.gov/publications/...\n"
                "https://example.org/paper.pdf"
            ),
            height=180,
        )
        research_focus = st.text_area(
            "Optional research focus",
            placeholder="Focus on PORTS benefits, avoided costs, maritime safety, and emergency response evidence.",
            height=110,
        )
        prompt = claude_batch_prompt(source_links, research_focus)
        st.text_area("Copy-ready Claude batch prompt", value=prompt, height=520)
        st.download_button(
            "Download Claude prompt",
            prompt.encode("utf-8"),
            file_name="ioos_claude_batch_prompt.txt",
            mime="text/plain",
        )

    with import_tab:
        st.code(intake_schema_csv_header(), language="text")
        render_intake_upload()


def page_staged_evidence(staged_df: pd.DataFrame, evidence_df: pd.DataFrame, source_df: pd.DataFrame) -> None:
    st.title("Staged Evidence")
    if not STAGED_EVIDENCE_PATH.exists():
        st.info("No staged evidence file exists yet. Use Evidence Intake to stage candidate rows.")
        return
    if staged_df.empty:
        st.success("No staged rows - add evidence or run an extraction to populate source review.")
        return

    staged_df = normalize_intake_df(staged_df)
    staged_df["review_status"] = staged_df["Source verification needed"].map(
        lambda value: "Verified / ready to accept" if value == "No" else "Needs verification"
    )

    edited = st.data_editor(
        staged_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "review_status": st.column_config.TextColumn(disabled=True),
        },
        disabled=["review_status"],
        key="staged_evidence_editor",
    )

    staged_to_save = edited.drop(columns=["review_status"], errors="ignore")
    save_errors = validate_intake_df(staged_to_save)
    left, right = st.columns([1, 1])

    with left:
        if st.button("Save staged edits"):
            if save_errors:
                st.error("Staged edits were not saved.")
                for error in save_errors:
                    st.write(f"- {error}")
            else:
                normalized = normalize_intake_df(staged_to_save)
                write_csv(STAGED_EVIDENCE_PATH, normalized.to_dict("records"), INTAKE_SCHEMA)
                clear_data_cache()
                st.success("Staged evidence saved.")
                st.rerun()

    with right:
        verified_mask = staged_to_save["Source verification needed"].map(normalize_text) == "No"
        verified_count = int(verified_mask.sum())
        if st.button(f"Promote {verified_count} verified rows to database", type="primary", disabled=verified_count == 0):
            if save_errors:
                st.error("Fix staged validation errors before accepting rows.")
                for error in save_errors:
                    st.write(f"- {error}")
                return

            normalized = normalize_intake_df(staged_to_save)
            verified_rows = normalized[verified_mask].to_dict("records")
            official_rows, updated_sources = accepted_rows_to_official(verified_rows, evidence_df, source_df)

            if official_rows:
                write_csv(SOURCE_PATH, updated_sources.to_dict("records"), list(updated_sources.columns))
                append_rows(EVIDENCE_PATH, official_rows, list(evidence_df.columns))

            remaining = normalized[~verified_mask]
            write_csv(STAGED_EVIDENCE_PATH, remaining.to_dict("records"), INTAKE_SCHEMA)
            clear_data_cache()
            st.success(f"Accepted {len(official_rows):,} rows into the official matrix.")
            st.rerun()

    st.download_button(
        "Download staged CSV",
        staged_to_save.to_csv(index=False).encode("utf-8"),
        file_name="staged_evidence.csv",
        mime="text/csv",
    )


def page_add_evidence_row(evidence_df: pd.DataFrame) -> None:
    st.title("Add Evidence Row")
    if evidence_df.empty:
        st.warning(f"No evidence matrix found at {EVIDENCE_PATH}")
        return

    st.caption("This form appends one new row and does not alter existing rows.")
    with st.form("add_evidence_row"):
        new_row: dict[str, str] = {}
        for column in evidence_df.columns:
            default_value = next_row_id(evidence_df) if column == "row_id" else ""
            if column in {"evidence_strength", "ioos_attribution_strength"}:
                new_row[column] = st.selectbox(column, ALLOWED_RATING_VALUES, index=1)
            elif column == "economic_number_type":
                new_row[column] = st.selectbox(column, ECONOMIC_NUMBER_TYPE_VALUES, index=3)
            elif column == "ioos_role_type":
                new_row[column] = st.selectbox(column, IOOS_ROLE_TYPE_VALUES, index=1)
            elif column in {
                "limitations",
                "claim_allowed",
                "ai_extraction_notes",
                "metric",
                "decision_supported",
                "economic_pathway",
                "allowed_use",
                "not_allowed_use",
            }:
                new_row[column] = st.text_area(column, value=default_value)
            else:
                new_row[column] = st.text_input(column, value=default_value)

        submitted = st.form_submit_button("Save row")

    if submitted:
        missing = [field for field in REQUIRED_ADD_FIELDS if not new_row.get(field, "").strip()]
        if missing:
            st.error("Please complete required fields: " + ", ".join(missing))
            return

        append_evidence_row(new_row, list(evidence_df.columns))
        clear_data_cache()
        st.success("Evidence row saved.")
        st.rerun()


def page_run_validation() -> None:
    st.title("Run Validation")
    st.write(f"Validator: `{VALIDATOR_PATH}`")
    if st.button("Run validation", type="primary"):
        result = run_validation()
        clear_data_cache()

        if result.returncode == 0:
            st.success("Validation completed successfully.")
        else:
            st.error("Validation completed with errors.")

        if result.stdout:
            st.code(result.stdout, language="text")
        if result.stderr:
            st.code(result.stderr, language="text")

        if REVIEW_PATH.exists():
            st.info(f"Refreshed `{REVIEW_PATH}`.")


def page_review_admin(
    regional_targets_df: pd.DataFrame,
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    review_df: pd.DataFrame,
    staged_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> None:
    st.markdown(
        """
        <div class="hub-page-title">
            <div class="hub-kicker">Maintainer workspace</div>
            <h1>Review / Admin</h1>
            <p>Review each generated staged claim against its source, then send verified source records to the best_sources table.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_claim_source_review(staged_df, best_sources_df)

    with st.expander("Advanced admin tools", expanded=False):
        render_ai_staging_comparison(staged_df, review_df)
        st.divider()

        current_section = st.session_state.get("review_admin_navigation", REVIEW_ADMIN_NAVIGATION[0])
        if current_section not in REVIEW_ADMIN_NAVIGATION:
            current_section = REVIEW_ADMIN_NAVIGATION[0]
            st.session_state["review_admin_navigation"] = current_section

        section = st.radio(
            "Review/Admin section",
            REVIEW_ADMIN_NAVIGATION,
            index=REVIEW_ADMIN_NAVIGATION.index(current_section),
            horizontal=True,
            label_visibility="collapsed",
            key="review_admin_navigation",
        )

        if section == "Evidence Intake":
            page_evidence_intake(regional_targets_df)
        elif section == "Review Evidence":
            page_staged_evidence(staged_df, evidence_df, source_df)
        elif section == "Validation Queue":
            page_review_needed(review_df)
        elif section == "Add Evidence Row":
            page_add_evidence_row(evidence_df)
        elif section == "Run Validation":
            page_run_validation()
        elif section == "Regional Builds":
            page_regional_builds(regional_targets_df, evidence_df)
        elif section == "Project Roadmap":
            page_project_roadmap(evidence_df, source_df, review_df, staged_df, best_sources_df)


def main() -> None:
    apply_hub_styles()

    evidence_df = load_csv(EVIDENCE_PATH)
    source_df = load_csv(SOURCE_PATH)
    review_df = load_csv(REVIEW_PATH)
    staged_df = load_csv(STAGED_EVIDENCE_PATH)
    best_sources_df = load_csv(BEST_SOURCES_PATH)
    regional_targets_df = load_csv(REGIONAL_TARGETS_PATH)
    (
        public_evidence_df,
        public_source_df,
        public_review_df,
        public_staged_df,
        public_best_sources_df,
    ) = public_two_table_views(evidence_df, source_df, review_df, staged_df, best_sources_df)

    render_app_hero()
    page = render_top_navigation()

    if page == "Overview":
        page_about_data(public_evidence_df, public_source_df, public_review_df, public_staged_df, public_best_sources_df)
    elif page == "Dashboard":
        page_dashboard_summary(public_evidence_df, public_source_df, public_review_df, public_staged_df, public_best_sources_df)
    elif page == "Regions":
        page_regions(regional_targets_df, public_evidence_df, public_source_df, public_best_sources_df)
    elif page == "Financial Evidence":
        page_evidence_atlas(public_evidence_df, public_source_df, public_review_df, public_best_sources_df)
    elif page == "Evidence Database":
        page_evidence_matrix(public_evidence_df, public_source_df, public_review_df)
    elif page == "Briefs & Outputs":
        page_congressional_briefing(public_evidence_df, public_source_df, public_staged_df, public_best_sources_df)
    elif page == "Best Sources":
        page_best_sources(public_best_sources_df)
    elif page == "Review / Admin":
        page_review_admin(regional_targets_df, evidence_df, source_df, review_df, staged_df, best_sources_df)


if __name__ == "__main__":
    main()
