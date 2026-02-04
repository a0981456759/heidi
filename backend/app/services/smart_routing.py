"""
Heidi Calls: Smart Routing Service
Multi-location clinic support with intelligent patient routing

Features:
- Location extraction from voicemail content
- Medicare number extraction and masking
- Doctor name recognition
- Patient history-based routing suggestions
"""

import re
from typing import Optional, Tuple, List
from dataclasses import dataclass


# ============================================================================
# CLINIC CONFIGURATION
# ============================================================================

# Available clinic locations
CLINIC_LOCATIONS = [
    {"id": "harbour", "name": "Harbour Medical Centre", "keywords": ["harbour", "harbor", "waterfront", "bay"]},
    {"id": "sunset", "name": "Sunset Family Practice", "keywords": ["sunset", "west", "evening"]},
    {"id": "central", "name": "Central City Clinic", "keywords": ["central", "city", "downtown", "cbd"]},
    {"id": "northside", "name": "Northside Health Hub", "keywords": ["north", "northside", "upper"]},
]

# Known doctors across locations
KNOWN_DOCTORS = [
    {"name": "Dr. Sarah Chen", "location": "harbour", "aliases": ["dr chen", "sarah chen", "chen"]},
    {"name": "Dr. Michael Wong", "location": "sunset", "aliases": ["dr wong", "michael wong", "wong"]},
    {"name": "Dr. Emma Thompson", "location": "central", "aliases": ["dr thompson", "emma thompson", "thompson"]},
    {"name": "Dr. James Nguyen", "location": "northside", "aliases": ["dr nguyen", "james nguyen", "nguyen"]},
    {"name": "Dr. Lisa Patel", "location": "harbour", "aliases": ["dr patel", "lisa patel", "patel"]},
]

# Simulated patient database (Medicare -> Location mapping)
PATIENT_LOCATION_HISTORY = {
    "2345678901": "harbour",
    "3456789012": "sunset",
    "4567890123": "central",
    "5678901234": "northside",
    "6789012345": "harbour",
}


@dataclass
class RoutingResult:
    """Result of smart routing analysis"""
    assigned_location: Optional[str]
    location_name: Optional[str]
    confidence: float
    routing_reason: str
    mentioned_doctor: Optional[str]
    mentioned_location: Optional[str]


@dataclass
class MedicareResult:
    """Result of Medicare extraction"""
    medicare_number: Optional[str]
    medicare_masked: Optional[str]
    is_valid: bool


@dataclass
class PatientMatchResult:
    """Result of patient matching"""
    matched: bool
    patient_id: Optional[str]
    confidence: float
    previous_location: Optional[str]


class SmartRoutingService:
    """
    Intelligent routing service for multi-location clinics

    Responsibilities:
    1. Extract and validate Medicare numbers
    2. Identify mentioned doctors and locations
    3. Route to appropriate clinic based on context
    4. Match patients to historical records
    """

    def __init__(self):
        self.locations = CLINIC_LOCATIONS
        self.doctors = KNOWN_DOCTORS
        self.patient_history = PATIENT_LOCATION_HISTORY

    # ========================================================================
    # MEDICARE EXTRACTION
    # ========================================================================

    def extract_medicare(self, text: str) -> MedicareResult:
        """
        Extract Medicare number from text (any language)

        Australian Medicare format: XXXX XXXXX X (10 digits + 1 check digit)
        May appear as: 2345 67890 1, 2345678901, 2345-67890-1
        """
        # Remove common separators and normalize
        normalized = re.sub(r'[^\d]', '', text)

        # Look for 10-11 digit sequences
        # Medicare is 10 digits + optional Individual Reference Number (IRN)
        patterns = [
            r'\b(\d{4})\s*(\d{5})\s*(\d{1,2})\b',  # Spaced format
            r'\b(\d{10,11})\b',  # Continuous digits
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    digits = ''.join(match)
                else:
                    digits = match

                # Validate length (10 or 11 digits)
                if 10 <= len(digits) <= 11:
                    # Basic validation: first digit should be 2-6
                    if digits[0] in '23456':
                        masked = self._mask_medicare(digits)
                        return MedicareResult(
                            medicare_number=digits,
                            medicare_masked=masked,
                            is_valid=True
                        )

        return MedicareResult(
            medicare_number=None,
            medicare_masked=None,
            is_valid=False
        )

    def _mask_medicare(self, medicare: str) -> str:
        """
        Mask Medicare number for privacy display
        Format: XXXX XXXX X## (show only last 2 digits)
        """
        if len(medicare) >= 10:
            return f"XXXX XXXX X{medicare[-2:]}"
        return "XXXX XXXX XXX"

    # ========================================================================
    # LOCATION EXTRACTION
    # ========================================================================

    def extract_location(self, text: str) -> Optional[str]:
        """Extract mentioned clinic location from text"""
        text_lower = text.lower()

        for location in self.locations:
            for keyword in location["keywords"]:
                if keyword in text_lower:
                    return location["id"]

        return None

    def get_location_name(self, location_id: str) -> Optional[str]:
        """Get full location name from ID"""
        for location in self.locations:
            if location["id"] == location_id:
                return location["name"]
        return None

    # ========================================================================
    # DOCTOR EXTRACTION
    # ========================================================================

    def extract_doctor(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract mentioned doctor from text

        Returns:
            Tuple of (doctor_name, associated_location)
        """
        text_lower = text.lower()

        for doctor in self.doctors:
            for alias in doctor["aliases"]:
                if alias in text_lower:
                    return doctor["name"], doctor["location"]

        return None, None

    # ========================================================================
    # SMART ROUTING
    # ========================================================================

    def route_voicemail(
        self,
        transcript: str,
        medicare_number: Optional[str] = None
    ) -> RoutingResult:
        """
        Determine the best clinic location for this voicemail

        Priority:
        1. Explicitly mentioned location
        2. Doctor's associated location
        3. Patient's historical location (via Medicare)
        4. Default to None (requires manual assignment)
        """
        # Step 1: Check for explicit location mention
        mentioned_location = self.extract_location(transcript)
        if mentioned_location:
            return RoutingResult(
                assigned_location=mentioned_location,
                location_name=self.get_location_name(mentioned_location),
                confidence=0.95,
                routing_reason="location_mentioned",
                mentioned_doctor=None,
                mentioned_location=self.get_location_name(mentioned_location)
            )

        # Step 2: Check for doctor mention
        doctor_name, doctor_location = self.extract_doctor(transcript)
        if doctor_location:
            return RoutingResult(
                assigned_location=doctor_location,
                location_name=self.get_location_name(doctor_location),
                confidence=0.85,
                routing_reason="doctor_association",
                mentioned_doctor=doctor_name,
                mentioned_location=None
            )

        # Step 3: Check patient history via Medicare
        if medicare_number and medicare_number in self.patient_history:
            historical_location = self.patient_history[medicare_number]
            return RoutingResult(
                assigned_location=historical_location,
                location_name=self.get_location_name(historical_location),
                confidence=0.75,
                routing_reason="patient_history",
                mentioned_doctor=None,
                mentioned_location=None
            )

        # Step 4: No routing information available
        return RoutingResult(
            assigned_location=None,
            location_name=None,
            confidence=0.0,
            routing_reason="unassigned",
            mentioned_doctor=doctor_name,
            mentioned_location=None
        )

    # ========================================================================
    # PATIENT MATCHING
    # ========================================================================

    def match_patient(self, medicare_number: Optional[str]) -> PatientMatchResult:
        """
        Attempt to match patient via Medicare number

        In production, this would query the patient database
        """
        if not medicare_number:
            return PatientMatchResult(
                matched=False,
                patient_id=None,
                confidence=0.0,
                previous_location=None
            )

        # Simulated patient lookup
        if medicare_number in self.patient_history:
            # Generate simulated patient ID
            patient_id = f"PAT-{medicare_number[-6:]}"
            return PatientMatchResult(
                matched=True,
                patient_id=patient_id,
                confidence=0.95,
                previous_location=self.patient_history[medicare_number]
            )

        return PatientMatchResult(
            matched=False,
            patient_id=None,
            confidence=0.0,
            previous_location=None
        )

    def get_all_locations(self) -> List[str]:
        """Get list of all available location IDs"""
        return [loc["id"] for loc in self.locations]


# Singleton instance
smart_routing = SmartRoutingService()
