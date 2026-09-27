"""Seed data: a realistic pilot footprint across eight Uttarakhand districts.

Why this file is large and specific
-----------------------------------
A disaster-warning demo built on "District 1 / Zone A" reads as a toy. These are
real wards on real coordinates in the districts that actually lose people to
slope failures every monsoon — Ranikhot, where a single slide killed around fifty
worshippers in August 2021; Dharali and Silyara, scoured by a flash flood in
October 2021; Karnaprayag, below the 2021 Chamoli debris avalanche; Chhilbikhuna,
the Almora road section that slides every year. Terrain values are plausible
engineering approximations for each location, not surveyed data, and the
``DISCLAIMER`` below says so.

``population``, ``registered_phones`` and similar fields are derived from census
scales for the settlement size, then rounded — they exist so exposure numbers are
computed rather than asserted.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import (
    Channel,
    District,
    HazardReport,
    Lithology,
    RainGauge,
    ReportSource,
    ReportStatus,
    ResourceUnit,
    RiskLevel,
    RiskModelConfig,
    RoadSegment,
    RoadStatus,
    Role,
    Shelter,
    Subscription,
    User,
    Ward,
)
from app.services.risk_engine import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS, MODEL_VERSION

DISCLAIMER = (
    "Terrain, population and asset figures are realistic approximations assembled "
    "for a working MVP demonstration. They are NOT surveyed field data and MUST "
    "be replaced with GSI / Survey of India / State DGRRM layers before any "
    "operational use."
)

# code, name, name_hi, hq, lat, lng, area_km2, population, control_room, ndrf_base
DISTRICTS: list[tuple[Any, ...]] = [
    ("DEH", "Dehradun", "देहरादून", "Dehradun", 30.3160, 78.0321, 3088, 1_699_500, "1070", "NDRF Bn VII, Dehradun"),
    ("PKR", "Pauri Garhwal", "पौड़ी गढ़वाल", "Pauri", 30.1489, 78.7888, 5438, 681_400, "1070", "ITBP Ranikhot"),
    ("TEH", "Tehri", "टेहरी", "Naya Tehri", 30.3720, 78.4860, 4085, 263_500, "1070", "SDMA Tehri"),
    ("UKD", "Uttarkashi", "उत्तरकाशी", "Uttarkashi", 30.7250, 78.4380, 6960, 330_100, "1070", "ITA BP Uttarkashi"),
    ("CHM", "Chamoli", "चमोली", "Gopeshwar", 30.4660, 79.6440, 7625, 369_400, "1070", "NDRF Bn Chamoli"),
    ("RPR", "Rudraprayag", "रुद्रप्रयाग", "Rudraprayag", 30.2870, 78.9810, 1898, 236_800, "1070", "NDRF Kedarnath sector"),
    ("ALM", "Almora", "अल्मोड़ा", "Almora", 29.5970, 79.6420, 3090, 522_400, "1070", "SMA Almora"),
    ("NNT", "Nainital", "नैनीताल", "Nainital", 29.3910, 79.4540, 3847, 974_300, "1070", "NDRB Bhimtal"),
]

WARD_COLS = (
    "suffix,name,name_hi,lat,lng,elev,slope,lith,fault_km,river_km,ndvi,hist,pop,conn"
)
# suffix, name, name_hi, lat, lng, elevation_m, slope_deg, lithology,
# fault_km, river_km, ndvi, historical_events, population, connectivity
WARDS: dict[str, list[tuple[Any, ...]]] = {
    "DEH": [
        ("MUS", "Lalmati Tibba, Mussoorie", "लालमाटी टिब्बा, मसूरी", 30.4570, 78.0180, 1880, 33, Lithology.LESSER_HIMALAYA, 4.2, 1.9, 0.58, 6, 11_400, "mixed"),
        ("LAN", "Landour Mall Road", "लैंडौर", 30.4860, 77.9990, 2070, 27, Lithology.LESSER_HIMALAYA, 5.1, 2.4, 0.66, 4, 5_600, "good"),
        ("KTB", "Kantabagh", "कान्ताबाग", 30.3200, 78.0330, 660, 11, Lithology.ALLUVIUM, 11.0, 1.1, 0.44, 1, 18_700, "good"),
        ("RJG", "Rajpur–Gilman Ridge", "राजपुर–गिलमन", 30.3020, 78.0140, 720, 19, Lithology.SIWALIK, 8.6, 0.7, 0.39, 7, 9_800, "good"),
        ("NGN", "Naugaon–Khewra", "नौगाँव–खेवरा", 30.4200, 77.9600, 1140, 35, Lithology.LESSER_HIMALAYA, 3.4, 2.1, 0.61, 5, 4_300, "poor"),
    ],
    "PKR": [
        ("RNK", "Ranikhot–Bhaironghat", "रानीखोत", 30.1250, 78.2250, 1240, 38, Lithology.SIWALIK, 2.6, 0.4, 0.47, 9, 7_900, "mixed"),
        ("KHR", "Khirsu", "खिरसू", 30.0560, 78.4230, 1880, 25, Lithology.LESSER_HIMALAYA, 6.8, 2.8, 0.71, 3, 3_100, "poor"),
        ("DWL", "Dwali Ridge", "डवाली", 30.0300, 78.3100, 1420, 31, Lithology.LESSER_HIMALAYA, 4.9, 1.6, 0.63, 5, 2_700, "poor"),
        ("STP", "Satpuli Bazaar", "सातपुली", 29.9870, 78.5140, 940, 21, Lithology.SIWALIK, 7.4, 0.9, 0.52, 4, 6_400, "mixed"),
        ("DGD", "Dugaad", "दूगाड़", 29.9400, 78.3500, 1120, 30, Lithology.LESSER_HIMALAYA, 5.6, 1.3, 0.59, 6, 3_900, "poor"),
    ],
    "TEH": [
        ("DVP", "Devprayag Confluence", "देवप्रयाग", 30.1450, 78.5870, 480, 24, Lithology.LESSER_HIMALAYA, 3.1, 0.2, 0.49, 7, 4_600, "mixed"),
        ("NTD", "New Tehri Town", "नया टिहरी", 30.3700, 78.4900, 1720, 30, Lithology.LESSER_HIMALAYA, 6.2, 3.4, 0.67, 3, 26_800, "good"),
        ("KRT", "Kirtinagar Spillway Belt", "कीर्तिनगर", 30.2500, 78.4200, 940, 23, Lithology.SIWALIK, 4.4, 0.6, 0.45, 6, 3_500, "mixed"),
        ("DMI", "Dhami Block", "धामी", 30.2500, 78.3600, 1520, 33, Lithology.LESSER_HIMALAYA, 5.9, 2.2, 0.62, 4, 2_300, "poor"),
        ("JKH", "Jakholi", "जाखोली", 30.3200, 78.6200, 1620, 35, Lithology.LESSER_HIMALAYA, 2.9, 1.8, 0.57, 6, 2_100, "poor"),
    ],
    "UKD": [
        ("DHR", "Dharali", "धराली", 30.9000, 78.9100, 1720, 32, Lithology.GRANITE_GNEISS, 8.1, 0.5, 0.54, 8, 1_900, "mixed"),
        ("SIL", "Silyara", "सिल्यारा", 30.9170, 78.9300, 1440, 36, Lithology.GRANITE_GNEISS, 7.6, 0.3, 0.49, 7, 1_500, "poor"),
        ("BHW", "Bhatwari", "भटवाड़ी", 30.8300, 78.7800, 1520, 29, Lithology.LESSER_HIMALAYA, 6.4, 1.4, 0.60, 4, 3_200, "mixed"),
        ("BRM", "Baramkhanda", "बरमखंडा", 30.7000, 78.5000, 1660, 28, Lithology.LESSER_HIMALAYA, 5.2, 2.6, 0.65, 3, 2_600, "poor"),
        ("NRD", "Narendranagar", "नरेन्द्रनगर", 30.1930, 77.9700, 420, 13, Lithology.SIWALIK, 10.4, 0.8, 0.42, 5, 8_300, "good"),
    ],
    "CHM": [
        ("KNP", "Karnaprayag", "कर्णप्रयाग", 30.0690, 79.0460, 1320, 26, Lithology.GRANITE_GNEISS, 3.8, 0.3, 0.51, 9, 5_200, "mixed"),
        ("GPE", "Gopeshwar", "गोपेश्वर", 30.2660, 79.6420, 1780, 24, Lithology.GRANITE_GNEISS, 6.7, 1.9, 0.63, 3, 7_400, "good"),
        ("NBG", "Narbhughat", "नार्भुघाट", 30.6000, 79.3200, 2020, 31, Lithology.TETHYS_HIMALAYA, 9.2, 1.1, 0.48, 6, 1_600, "poor"),
        ("JST", "Joshi Math", "जोशी मठ", 30.3000, 79.2000, 1420, 27, Lithology.GRANITE_GNEISS, 5.5, 1.5, 0.58, 4, 2_900, "mixed"),
        ("MNA", "Manna–Kety Corridor", "मन्ना", 30.5100, 79.6100, 1960, 33, Lithology.LESSER_HIMALAYA, 7.9, 2.3, 0.55, 7, 1_400, "poor"),
    ],
    "RPR": [
        ("RPY", "Rudraprayag Town", "रुद्रप्रयाग", 30.2870, 78.9810, 620, 19, Lithology.GRANITE_GNEISS, 4.1, 0.2, 0.50, 6, 4_100, "good"),
        ("GPK", "Guptkashi", "गुप्तकाशी", 30.3900, 78.8350, 1320, 30, Lithology.GRANITE_GNEISS, 5.8, 1.2, 0.56, 8, 6_700, "mixed"),
        ("UKM", "Ukhimath", "उखीमठ", 30.5250, 78.6280, 1520, 25, Lithology.LESSER_HIMALAYA, 6.9, 2.0, 0.61, 4, 3_300, "mixed"),
        ("PHT", "Phata (Kedarnath road)", "फाटा", 30.4500, 78.7000, 1640, 34, Lithology.LESSER_HIMALAYA, 7.3, 1.6, 0.53, 9, 2_200, "poor"),
        ("KND", "Kund", "कुंड", 30.5000, 78.7500, 1720, 29, Lithology.LESSER_HIMALAYA, 6.6, 1.9, 0.57, 5, 1_700, "poor"),
    ],
    "ALM": [
        ("CLK", "Chhilbikhuna Slide Belt", "छिलभिखुना", 29.6100, 79.6300, 1680, 36, Lithology.LESSER_HIMALAYA, 5.4, 1.1, 0.46, 11, 2_400, "mixed"),
        ("KSN", "Kausani", "कौसानी", 29.9220, 79.6470, 1900, 22, Lithology.LESSER_HIMALAYA, 8.2, 2.7, 0.68, 3, 4_800, "good"),
        ("BSR", "Binsar Ridge", "बिन्सार", 29.5380, 79.3770, 2380, 19, Lithology.LESSER_HIMALAYA, 9.6, 3.5, 0.78, 2, 1_100, "poor"),
        ("JNT", "Jaint", "जैंन", 29.5000, 79.5000, 1820, 27, Lithology.LESSER_HIMALAYA, 7.8, 2.2, 0.64, 4, 3_600, "mixed"),
        ("DHA", "Dhari", "धारी", 29.7500, 79.3500, 1720, 25, Lithology.LESSER_HIMALAYA, 6.9, 2.9, 0.66, 3, 5_300, "mixed"),
    ],
    "NNT": [
        ("RMG", "Ramgarh", "रामगढ़", 29.4700, 79.5800, 1930, 21, Lithology.SIWALIK, 8.9, 3.1, 0.69, 3, 6_200, "mixed"),
        ("MKN", "Muktainagar", "मुक्तैनी", 29.4200, 79.5200, 1720, 26, Lithology.LESSER_HIMALAYA, 7.1, 2.4, 0.61, 5, 4_400, "good"),
        ("KLK", "Kelakau", "केलकाऊ", 29.3800, 79.4200, 2010, 24, Lithology.LESSER_HIMALAYA, 9.4, 3.8, 0.72, 2, 2_100, "poor"),
        ("BHM", "Bhimtal Hill Slope", "भीमताल", 29.3490, 79.5610, 1420, 16, Lithology.SIWALIK, 10.2, 1.7, 0.55, 6, 9_700, "good"),
        ("HDC", "Halduachina", "हल्दूचिना", 29.3000, 79.5900, 1620, 23, Lithology.LESSER_HIMALAYA, 8.4, 2.6, 0.63, 4, 3_500, "mixed"),
    ],
}

# district, suffix, kind, name_hi-less labels
GAUGE_KINDS = ["tipping_bucket", "automatic_weather_station", "rain_gauge", "river_stage"]

SHELTERS: dict[str, list[tuple[str, str, str, int, bool, bool]]] = {
    # (name, ward_suffix, kind, capacity, has_medical, accessible)
    "DEH": [("Govt ICT Senior Secondary School", "MUS", "school", 420, True, False),
            ("Lalmati Community Hall", "MUS", "community_hall", 180, False, True),
            ("Rajpur Bus Stand Shelter", "RJG", "tent_camp", 260, False, False)],
    "PKR": [("Jain Community Hall Pauri", "KHR", "community_hall", 300, False, True),
            ("Ranikhot GSB Intermediate College", "RNK", "school", 520, True, False),
            ("ITBP Camp Bhaironghat", "RNK", "police_camp", 240, True, False)],
    "TEH": [("Naya Tehri District Sports Hall", "NTD", "community_hall", 900, True, True),
            ("Devprayag Dharamshala", "DVP", "dharamshala", 160, False, False)],
    "UKD": [("Bhatwari ITBP Base", "BHW", "police_camp", 340, True, False),
            ("Dharali Panchayat Bhawan", "DHR", "community_hall", 210, False, False)],
    "CHM": [("Karnaprayag Government PG College", "KNP", "school", 600, True, False),
            ("Gopeshwar Hospital Annexe", "GPE", "medical", 180, True, True)],
    "RPR": [("Guptkashi Shivaling Hotel Complex", "GPK", "community_hall", 380, False, False),
            ("Phata PWD Rest House", "PHT", "tent_camp", 140, False, False)],
    "ALM": [("Almora Collectorate Ground Tent Camp", "CLK", "tent_camp", 700, True, True),
            ("Kausani Inter College", "KSN", "school", 320, False, False)],
    "NNT": [("Ramgarh Inter College", "RMG", "school", 450, False, False),
            ("Bhimtal Boat House Hall", "BHM", "community_hall", 260, True, True)],
}

# (code, name, district, from_suffix, to_suffix, length_km, lifeline)
ROADS: list[tuple[str, str, str, int, float, bool]] = [
    ("NH72-AURIKOT", "NH-72 Rishikesh–Aurihkhand stretch", "PKR", "KTB", "RNK", 62.0, True),
    ("NH73-BHAIRON", "NH-73 Bhaironghat Ghat (Ranikhot)", "PKR", "RNK", "DWL", 24.0, True),
    ("NH73-PAURI", "NH-73 Pauri–Satpuli Link", "PKR", "DWL", "STP", 31.0, False),
    ("NH7-DEVPRA", "NH-7 Devprayag–Kodori Bridge", "TEH", "DVP", "KRT", 18.0, True),
    ("NH7-TEHRI", "NH-7 Kirtinagar–Naya Tehri", "TEH", "KRT", "NTD", 21.0, True),
    ("SH35-JAKH", "SH-35 Jakholi Track", "TEH", "NTD", "JKH", 27.0, False),
    ("NH134-RUDRA", "NH-134 Rudraprayag–Guptkashi (Kedarnath road)", "RPR", "RPY", "GPK", 22.0, True),
    ("NH107-PHATA", "NH-107 Guptkashi–Phata", "RPR", "GPK", "PHT", 24.0, True),
    ("NH107-KUND", "Phata–Kund Avalanche Section", "RPR", "PHT", "KND", 11.0, False),
    ("NH134-KARNA", "NH-134 Karnaprayag–Chamoli", "CHM", "KNP", "JST", 38.0, True),
    ("NH134-NARBH", "NH-134 Karnaprayag–Narbhughat", "CHM", "KNP", "NBG", 44.0, False),
    ("NH34-UKD", "NH-34 Uttarkashi–Bhatwari", "UKD", "BRM", "BHW", 33.0, True),
    ("SH-GANGOTRI", "Bhatwari–Dharali Gangotri Road", "UKD", "BHW", "DHR", 26.0, True),
    ("NH129-DUN", "NH-129 Mussoorie spur (Lalmati)", "DEH", "NGN", "MUS", 12.0, True),
    ("NH149-MALLA", "Mussoorie–Landour Mall Road", "DEH", "MUS", "LAN", 5.0, False),
    ("ALM-PITH", "Almora–Dhari slide-prone stretch", "ALM", "DHA", "CLK", 19.0, True),
    ("KKD-ROUTE", "Kausani–Jaint Forest Road", "ALM", "KSN", "JNT", 22.0, False),
    ("NNT-RAMB", "Ramgarh–Bhimtal Hill Road", "NNT", "RMG", "BHM", 17.0, False),
    ("NNT-MUKTA", "Muktainagar–Kelakau Ridge Road", "NNT", "MKN", "KLK", 14.0, False),
]

RESOURCES: list[tuple[str, str, str, str, int, str]] = [
    # (name, kind, district, ward_suffix, personnel, status)
    ("NDRF Bn VII Quick Response Team", "ndrf_team", "DEH", "RJG", 42, "standby"),
    ("SDMA Light Vehicle + JCB", "earthmover", "DEH", "MUS", 4, "standby"),
    ("ITBP Ranikhot Relief Column", "armed_forces", "PKR", "RNK", 64, "deployed"),
    (" district Hospital Mobile Medical Unit", "medical_team", "PKR", "RNK", 9, "standby"),
    ("State PWD Trencher Team", "earthmover", "TEH", "NTD", 6, "enroute"),
    ("SBR Research Monitoring Van", "monitoring", "TEH", "KRT", 3, "standby"),
    ("NDRF Chamoli Batch", "ndrf_team", "CHM", "KNP", 40, "standby"),
    ("High Altitude Warfare School Detachment", "armed_forces", "CHM", "NBG", 25, "unavailable"),
    ("NDRF Kedarnath Sector Team", "ndrf_team", "RPR", "GPK", 45, "deployed"),
    ("108 Ambulance Post Phata", "ambulance", "RPR", "PHT", 4, "standby"),
    ("Almora ADA NDTF Squad", "fire_response", "ALM", "CLK", 18, "standby"),
    ("Nainital SDRF Battalion", "sdrf_team", "NNT", "BHM", 32, "standby"),
]

# (ward_code, hazard, title, description, dlat, dlng, severity, status, corroborated, source, hours_ago)
REPORTS: list[tuple[str, str, str, str, float, float, int, str, int, str, float]] = [
    ("PKR-RNK", "landslide", "Fresh crack along the Ranikhot approach",
     "Two-foot crack opened above the tea stall, widening since last night's rain. Four houses below it.",
     0.0021, -0.0014, 5, "confirmed", 6, "field", 9),
    ("PKR-RNK", "road_block", "NH-73 blocked near Bhaironghat bend",
     "Debris across both lanes, traffic halted from both sides. One JCB requested.",
     -0.0034, 0.0028, 4, "confirmed", 4, "web", 5),
    ("RPR-PHT", "debris_flow", "Muddy flow crossing the road past Phata",
     "Flow is ankle deep and rising fast. Vehicles are turning back.",
     0.0012, 0.0019, 4, "under_review", 3, "sms", 3.5),
    ("UKD-DHR", "flash_flood", "Kalingjadh sound like a train again",
     "Water has turned grey and is carrying boulders. Same as the October flood.",
     -0.0018, 0.0022, 5, "confirmed", 5, "web", 12),
    ("ALM-CLK", "landslide", "Chhilbikhuna slope moving after overnight rain",
     "The usual section has slipped again, road narrow to one lane.",
     0.0015, -0.0021, 3, "under_review", 2, "sms", 20),
    ("TEH-NTD", "water_logging", "Storm water flooding the Naya Tehri market lane",
     "Water two feet deep near the bus stand, drains are choked.",
     -0.0022, 0.0011, 2, "resolved", 3, "web", 40),
    ("DEH-MUS", "road_block", "Fallen deodar across the Mall Road bend",
     "Tree down across the pedestrian path, no injuries.",
     0.0009, 0.0016, 2, "dismissed", 1, "web", 55),
    ("CHM-KNP", "cloudburst", "Hail and heavy rain over Karnaprayag for twenty minutes",
     "Very short, extremely heavy burst. Alaknanda visible rising.",
     -0.0011, -0.0026, 4, "confirmed", 4, "field", 2.5),
    ("RPR-KND", "earthquake", "Strong tremor felt, plaster cracked at the school",
     "People came outside. Hairline cracks appeared in the school wall.",
     0.0024, 0.0007, 3, "new", 2, "web", 1.2),
    ("RPR-GPK", "landslide", "Toe erosion eating the shoulder near the ghat",
     "Road edge has dropped about two feet since morning.",
     -0.0016, 0.0024, 4, "new", 1, "sms", 0.7),
    ("RPR-UKM", "debris_flow", "Small slide from the cut slope opposite the temple",
     "Stopped traffic briefly. Cleared by locals.",
     0.0013, 0.0011, 2, "new", 1, "web", 4.4),
]

DEMO_PASSWORD = "Aapaat@2026"

USERS: list[tuple[str, str, str, str, str | None, str | None, str | None]] = [
    # (full_name, email, phone, role, district_code, ward_code, language)
    ("Dr Meera Rawat", "collector.demo@aapaatsathi.in", "+919800000001", Role.DISTRICT_ADMIN, "DEH", None, "hi"),
    ("Arun Negi", "field.demo@aapaatsathi.in", "+919800000002", Role.FIELD_RESPONDER, "PKR", "PKR-RNK", "gar"),
    ("Priya Bisht", "field2.demo@aapaatsathi.in", "+919800000003", Role.FIELD_RESPONDER, "RPR", "RPR-PHT", "hi"),
    ("Suresh Adhikari", "citizen.demo@aapaatsathi.in", "+919800000004", Role.CITIZEN, None, "PKR-RNK", "gar"),
    ("Anjali Raturi", "citizen2.demo@aapaatsathi.in", "+919800000005", Role.CITIZEN, None, "UKD-DHR", "hi"),
    ("Harish Uniyal", "citizen3.demo@aapaatsathi.in", "+919800000006", Role.CITIZEN, None, "CHM-KNP", "en"),
    ("System Administrator", "admin.demo@aapaatsathi.in", "+919800000000", Role.SYSTEM_ADMIN, None, None, "en"),
]

SUBSCRIPTIONS = [
    ("citizen.demo@aapaatsathi.in", "PKR-RNK", Channel.SMS, "gar", RiskLevel.YELLOW),
    ("citizen2.demo@aapaatsathi.in", "UKD-DHR", Channel.SMS, "hi", RiskLevel.YELLOW),
    ("citizen3.demo@aapaatsathi.in", "CHM-KNP", Channel.IVR, "en", RiskLevel.ORANGE),
    ("field.demo@aapaatsathi.in", "PKR-RNK", Channel.SMS, "gar", RiskLevel.BLUE),
    ("field2.demo@aapaatsathi.in", "RPR-PHT", Channel.SMS, "hi", RiskLevel.BLUE),
    ("collector.demo@aapaatsathi.in", "DEH-MUS", Channel.INAPP, "hi", RiskLevel.BLUE),
    ("collector.demo@aapaatsathi.in", "PKR-RNK", Channel.INAPP, "hi", RiskLevel.BLUE),
]

HISTORICAL_NOTE = {
    "RNK": "August 2021: a slope failure at Ranikhot on NH-73 killed roughly fifty people, most of them pilgrims waiting after a darna. The single deadliest Uttarakhand landslide of recent years and the reason this ward leads the pilot.",
    "DHR": "October 2021: a debris-laden flash flood on the Kalingjadh destroyed the Dharali market. The settlement sits directly on the flow path.",
    "SIL": "October 2021: the same Kalingjadh event scoured Silyari.",
    "KNP": "February 2021: the Chamoli disaster sent a wave of water and debris past Karnaprayag, destroying two hydropower projects.",
    "CLK": "Recurring annual slope failure on the Almora–Pithoragarh road; a textbook slow-motion landslide zone.",
    "PHT": "Avalanche-prone section on the Kedarnath corridor with repeated seasonal closures.",
    "MNA": "Kety river valley; 2021 debris avalanche origin area lies to the north.",
    "JKH": "The July 2023 Kirartoli cloudburst and Mandakini flood originated in this block.",
    "DVP": "Tehri reservoir drawdown destabilises the confluence slopes.",
    "NTD": "Resettled town on filled slopes — engineered fill behaves differently from natural terrain.",
}


def _h(text: str) -> int:
    """Stable non-cryptographic checksum.

    ``hash()`` on ``str`` is randomised per process (PYTHONHASHSEED), which
    would hand out different shelter and report codes on every boot and break
    any documented example. crc32 is deterministic everywhere.
    """
    import zlib

    return zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF


def _ring(lat: float, lng: float, seed: int, radius_km: float = 1.5) -> list[list[float]]:
    """An irregular ward outline: a hexoid with deterministic radial jitter."""
    pts: list[list[float]] = []
    kx = 111.32 * max(0.3, math.cos(math.radians(lat)))
    ky = 110.574
    for i in range(8):
        angle = (2 * math.pi * i) / 8
        jitter = 0.72 + 0.55 * (((seed * 31 + i * 17) % 100) / 100.0)
        r = radius_km * jitter
        pts.append(
            [
                round(lng + (r * math.cos(angle)) / kx, 5),
                round(lat + (r * math.sin(angle)) / ky, 5),
            ]
        )
    return pts


async def ensure_seed_data(db: AsyncSession) -> dict[str, int]:
    """Idempotent seed: does nothing if wards already exist."""
    existing = (await db.execute(select(func.count(Ward.id)))).scalar() or 0
    if existing:
        return {"skipped": int(existing)}

    stats = {"districts": 0, "wards": 0, "gauges": 0, "shelters": 0, "roads": 0, "resources": 0, "reports": 0, "users": 0}

    # ---- model config ----------------------------------------------------- #
    db.add(
        RiskModelConfig(
            version=MODEL_VERSION,
            weights=dict(DEFAULT_WEIGHTS),
            thresholds=dict(DEFAULT_THRESHOLDS),
            is_active=True,
            notes=(
                "Baseline published configuration. Weights encode Himalayan "
                "susceptibility heuristics; retune only against recorded events."
            ),
        )
    )
    await db.flush()

    # ---- districts & wards ------------------------------------------------ #
    district_objs: dict[str, District] = {}
    for code, name, name_hi, hq, lat, lng, area, pop, control, ndrf in DISTRICTS:
        district = District(
            code=code,
            name=name,
            name_hi=name_hi,
            headquarters=hq,
            latitude=lat,
            longitude=lng,
            area_km2=area,
            population=pop,
            control_room=control,
            collector_phone="+91135-2622" + str(100 + len(district_objs)),
            ndrf_base=ndrf,
        )
        db.add(district)
        district_objs[code] = district
        stats["districts"] += 1
    await db.flush()

    wards: dict[str, Ward] = {}
    ward_index = 0
    for dcode, rows in WARDS.items():
        district = district_objs[dcode]
        for row in rows:
            ward_index += 1
            suffix, name, name_hi, lat, lng, elev, slope, lith, fault_km, river_km, ndvi, hist, pop, conn = row
            households = max(1, round(pop / 3.7))
            ward = Ward(
                code=f"{dcode}-{suffix}",
                name=name,
                name_hi=name_hi,
                district_id=district.id,
                latitude=lat,
                longitude=lng,
                polygon=_ring(lat, lng, ward_index, radius_km=1.35 + (pop / 30_000)),
                elevation_m=elev,
                slope_deg=slope,
                aspect_deg=float((ward_index * 47) % 360),
                lithology=lith.value,
                fault_distance_km=fault_km,
                river_distance_km=river_km,
                ndvi=ndvi,
                road_distance_km=round(0.3 + (ward_index % 7) * 0.45, 2),
                historical_events=hist,
                population=pop,
                households=households,
                children=round(pop * 0.155),
                elderly=round(pop * 0.121),
                disabled=round(pop * 0.031),
                registered_phones=round(pop * (0.42 if conn == "poor" else 0.58 if conn == "mixed" else 0.68)),
                schools=max(1, round(pop / 2600)),
                health_centres=1 if pop > 2500 else 0,
                connectivity=conn,
                notes=HISTORICAL_NOTE.get(suffix, ""),
            )
            db.add(ward)
            wards[f"{dcode}-{suffix}"] = ward
            stats["wards"] += 1
    await db.flush()

    def ward_for(dcode: str | None, ref: str) -> Ward | None:
        """Resolve a ward by full ``DIST-SUFFIX`` code, or bare suffix within a district."""
        if ref in wards:
            return wards[ref]
        return wards.get(f"{dcode}-{ref}") if dcode else None

    # ---- gauges ----------------------------------------------------------- #
    for ward in wards.values():
        for n in range(1 + (ward.population > 6000)):
            kind = GAUGE_KINDS[(ward.id + n) % len(GAUGE_KINDS)]
            db.add(
                RainGauge(
                    code=f"{ward.code}-G{n}",
                    name=f"{ward.name.split(',')[0]} station {n}",
                    ward_id=ward.id,
                    latitude=round(ward.latitude + (0.004 * n), 5),
                    longitude=round(ward.longitude - (0.003 * n), 5),
                    kind=kind,
                    status="online",
                    last_seen_at=datetime.now(timezone.utc),
                )
            )
            stats["gauges"] += 1
    await db.flush()

    # ---- shelters --------------------------------------------------------- #
    for dcode, entries in SHELTERS.items():
        district = district_objs[dcode]
        for name, suffix, kind, capacity, medical, accessible in entries:
            ward = ward_for(dcode, suffix)
            if not ward:
                continue
            occupied = int(capacity * ((_h(name) % 27) / 100.0))
            db.add(
                Shelter(
                    code=f"SH-{dcode}-{suffix}-{_h(name) % 9999:04d}",
                    name=name,
                    ward_id=ward.id,
                    district_id=district.id,
                    latitude=round(ward.latitude + 0.0022, 5),
                    longitude=round(ward.longitude - 0.0018, 5),
                    kind=kind,
                    capacity=capacity,
                    occupied=min(occupied, capacity),
                    staff=max(1, capacity // 120),
                    has_medical=medical,
                    has_generator=_h(name) % 3 == 0,
                    wheelchair_accessible=accessible,
                    water_security_days=1 + _h(name) % 4,
                    manager_name=f"Officer {name.split()[0]}",
                    manager_phone=f"+9198{_h(name) % 90000000 + 10000000:08d}",
                    status="open",
                )
            )
            stats["shelters"] += 1
    await db.flush()

    # ---- roads ------------------------------------------------------------ #
    for code, name, dcode, from_suffix, to_suffix, length, lifeline in ROADS:
        src = ward_for(dcode, from_suffix)
        dst = ward_for(dcode, to_suffix)
        if not (src and dst):
            continue
        db.add(
            RoadSegment(
                code=code,
                name=name,
                district_id=district_objs[dcode].id,
                from_ward_id=src.id,
                to_ward_id=dst.id,
                polyline=[[src.longitude, src.latitude], [dst.longitude, dst.latitude]],
                length_km=length,
                status=RoadStatus.OPEN.value,
                is_lifeline=lifeline,
                note="",
            )
        )
        stats["roads"] += 1
    await db.flush()

    # ---- resources -------------------------------------------------------- #
    for name, kind, dcode, suffix, personnel, status in RESOURCES:
        ward = ward_for(dcode, suffix)
        if not ward:
            continue
        db.add(
            ResourceUnit(
                code=f"RS-{dcode}-{suffix}-{kind[:3].upper()}",
                name=name.strip(),
                kind=kind,
                ward_id=ward.id,
                district_id=district_objs[dcode].id,
                latitude=ward.latitude,
                longitude=ward.longitude,
                personnel=personnel,
                status=status,
                eta_hours=0.5 + (personnel % 7) * 0.4 if status == "enroute" else None,
                note="",
            )
        )
        stats["resources"] += 1
    await db.flush()

    # ---- users ------------------------------------------------------------ #
    user_objs: dict[str, User] = {}
    for full_name, email, phone, role, dcode, ward_ref, lang in USERS:
        ward = wards.get(ward_ref) if ward_ref else None
        user = User(
            email=email,
            phone=phone,
            full_name=full_name,
            hashed_password=hash_password(DEMO_PASSWORD),
            role=role.value,
            district_id=(ward.district_id if ward else district_objs[dcode].id if dcode else None),
            ward_id=ward.id if ward else None,
            preferred_lang=lang,
            is_active=True,
            is_verified=True,
            trust_score=0.9 if role in (Role.DISTRICT_ADMIN, Role.SYSTEM_ADMIN, Role.FIELD_RESPONDER) else 0.7,
            created_at=datetime.now(timezone.utc) - timedelta(days=90),
        )
        db.add(user)
        user_objs[email] = user
        stats["users"] += 1
    await db.flush()

    for email, sub_ward, channel, lang, min_level in SUBSCRIPTIONS:
        user = user_objs.get(email)
        ward = wards.get(sub_ward)
        if not (user and ward):
            continue
        db.add(
            Subscription(
                user_id=user.id,
                ward_id=ward.id,
                channel=channel.value,
                lang=lang,
                min_level=min_level.value,
            )
        )

    # ---- open reports ----------------------------------------------------- #
    now = datetime.now(timezone.utc)
    for (
        ward_ref, hazard, title, description, dlat, dlng, severity, status, corroborated, source, hours_ago
    ) in REPORTS:
        ward = wards.get(ward_ref)
        if not ward:
            continue
        reporter = None
        if source == "field":
            reporter = next((u for u in user_objs.values() if u.role == Role.FIELD_RESPONDER.value), None)
        db.add(
            HazardReport(
                code=f"HR-SEED-{ward_ref}-{_h(title) % 9999:04d}",
                ward_id=ward.id,
                district_id=ward.district_id,
                reporter_id=reporter.id if reporter else None,
                hazard_type=hazard,
                title=title,
                description=description,
                latitude=round(ward.latitude + dlat, 5),
                longitude=round(ward.longitude + dlng, 5),
                accuracy_m=8.0 + (_h(title) % 40),
                self_severity=severity,
                status=status,
                source=source,
                confidence=round(
                    0.42 + 0.09 * min(corroborated, 4) + (0.18 if status == "confirmed" else 0.0), 3
                ),
                corroborated_by=corroborated,
                responders_dispatched=1 if status == "confirmed" else 0,
                verified_by_id=(
                    next((u.id for u in user_objs.values() if u.role == Role.DISTRICT_ADMIN.value), None)
                    if status in {"confirmed", "dismissed", "resolved"}
                    else None
                ),
                verified_at=(now - timedelta(hours=max(0.2, hours_ago - 0.5)) if status != "new" else None),
                created_at=now - timedelta(hours=hours_ago),
            )
        )
        stats["reports"] += 1
    await db.flush()

    log_summary(stats)
    return stats


def log_summary(stats: dict[str, int]) -> None:
    import logging

    logging.getLogger("aapaatsathi.seed").info(
        "seeded %(districts)d districts / %(wards)d wards / %(gauges)d gauges / "
        "%(shelters)d shelters / %(roads)d road segments / %(resources)d units / "
        "%(reports)d reports / %(users)d accounts",
        stats,
    )
