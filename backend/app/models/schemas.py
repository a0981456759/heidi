"""
Heidi Calls: Data Models & Schemas
Pydantic models for request/response validation
Enhanced with confidence scoring and multilingual entity extraction
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum


class UrgencyLevel(int, Enum):
    """Urgency levels from 1 (lowest) to 5 (highest/emergency)"""
    LOW = 1
    MODERATE = 2
    STANDARD = 3
    HIGH = 4
    CRITICAL = 5


class IntentType(str, Enum):
    """Classification of voicemail intent"""
    BOOKING = "Booking"
    PRESCRIPTION = "Prescription"
    RESULTS = "Results"
    EMERGENCY = "Emergency"
    BILLING = "Billing"
    REFERRAL = "Referral"
    AMBIGUOUS = "Ambiguous"  # New: for unclear/unintelligible content
    OTHER = "Other"


class LanguageInfo(BaseModel):
    """Language detection with interpreter requirements"""
    detected: str = Field(..., description="Detected language name")
    code: Optional[str] = Field(None, description="ISO 639-1 language code")
    requires_interpreter: bool = Field(False, description="Whether interpreter is recommended")


class UrgencyInfo(BaseModel):
    """Urgency classification with reasoning and confidence"""
    level: int = Field(..., ge=1, le=5, description="Urgency level 1-5")
    reasoning: str = Field(..., description="Explanation for urgency classification")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="AI confidence score 0-1")

    @validator('level')
    def validate_level(cls, v):
        if not 1 <= v <= 5:
            raise ValueError('Urgency level must be between 1 and 5')
        return v


class ExtractedEntities(BaseModel):
    """Entities extracted from voicemail across any language"""
    callback_number: Optional[str] = Field(None, description="Extracted callback phone number")
    callback_number_raw: Optional[str] = Field(None, description="Raw phone as spoken/written")
    urgency_keywords: List[str] = Field(default_factory=list, description="Keywords indicating urgency")
    medication_names: List[str] = Field(default_factory=list, description="Any mentioned medications")
    symptoms: List[str] = Field(default_factory=list, description="Reported symptoms")
    # Multi-location clinic support
    medicare_number: Optional[str] = Field(None, description="Extracted Medicare number (11 digits)")
    medicare_number_masked: Optional[str] = Field(None, description="Masked Medicare: XXXX XXXX X##")
    mentioned_doctor: Optional[str] = Field(None, description="Doctor name mentioned by patient")
    mentioned_location: Optional[str] = Field(None, description="Clinic location mentioned")


class LocationInfo(BaseModel):
    """Clinic location routing information"""
    assigned_location: Optional[str] = Field(None, description="Assigned clinic branch")
    location_confidence: float = Field(0.0, description="Confidence in location assignment")
    routing_reason: str = Field("default", description="Why this location was assigned")
    available_locations: List[str] = Field(default_factory=list, description="All clinic locations")


class PatientMatchInfo(BaseModel):
    """Patient identification matching status"""
    medicare_matched: bool = Field(False, description="Whether Medicare was matched to records")
    patient_id: Optional[str] = Field(None, description="Matched patient ID if found")
    match_confidence: float = Field(0.0, description="Confidence in patient match")
    previous_location: Optional[str] = Field(None, description="Patient's usual clinic location")


class UIState(BaseModel):
    """UI display hints for frontend rendering"""
    is_ambiguous: bool = Field(False, description="Content is unclear/unintelligible")
    needs_manual_listening: bool = Field(False, description="Staff should listen to audio")
    highlight_urgent: bool = Field(False, description="Should be visually highlighted")
    time_since_call: Optional[str] = Field(None, description="Human-readable time elapsed")


class EscalationInfo(BaseModel):
    """Emergency escalation status for Level 5 cases"""
    escalation_triggered: bool = Field(False, description="Whether emergency escalation was triggered")
    emergency_alert_sent: bool = Field(False, description="Whether TTS emergency alert was sent to patient")
    intervention_status: Optional[str] = Field(None, description="Status of intervention (e.g., Voice_Alert_Sent)")
    timestamp_escalated: Optional[str] = Field(None, description="ISO timestamp when escalation occurred")
    emergency_script: Optional[str] = Field(None, description="Script played to patient")
    sms_sent_to: Optional[str] = Field(None, description="Manager phone that received SMS")
    actions_taken: List[str] = Field(default_factory=list, description="List of actions taken")


class VoicemailInput(BaseModel):
    """Input schema for new voicemail submission"""
    transcript: str = Field(..., min_length=1, description="Raw voicemail transcript")
    caller_phone: Optional[str] = Field(None, description="Caller phone number")
    call_timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)
    duration_seconds: Optional[int] = Field(None, ge=0)
    audio_file_url: Optional[str] = Field(None, description="URL to audio file")
    audio_quality_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Audio clarity score")

    class Config:
        json_schema_extra = {
            "example": {
                "transcript": "Hi, this is John Smith calling about my blood pressure medication...",
                "caller_phone": "+61412345678",
                "duration_seconds": 45
            }
        }


class TriagedVoicemail(BaseModel):
    """
    Core output schema for triaged voicemail
    Enhanced with confidence scoring and entity extraction
    """
    voicemail_id: str = Field(..., description="Unique identifier")

    # Language info (now structured)
    language: str = Field(..., description="Detected language (backwards compat)")
    language_info: Optional[LanguageInfo] = Field(None, description="Detailed language info")

    # Triage results
    urgency: UrgencyInfo = Field(..., description="Urgency classification with confidence")
    intent: IntentType = Field(..., description="Primary intent classification")
    summary: str = Field(..., description="English summary of the voicemail")
    action_item: str = Field(..., description="Suggested next step for staff")

    # Entity extraction
    extracted_entities: Optional[ExtractedEntities] = Field(None, description="Extracted entities")

    # Multi-location clinic support
    location_info: Optional[LocationInfo] = Field(None, description="Clinic location routing")
    patient_match: Optional[PatientMatchInfo] = Field(None, description="Patient identification status")

    # UI state hints
    ui_state: Optional[UIState] = Field(None, description="UI rendering hints")

    # Emergency escalation (Level 5)
    escalation: Optional[EscalationInfo] = Field(None, description="Emergency escalation info for Level 5")

    # Audio file
    audio_file_url: Optional[str] = Field(None, description="URL to original voicemail audio file")

    # PII handling
    is_pii_safe: bool = Field(..., description="Whether PII has been redacted")
    original_transcript: Optional[str] = Field(None, description="Original transcript (redacted)")
    redacted_transcript: Optional[str] = Field(None, description="PII-redacted transcript")
    caller_phone_redacted: Optional[str] = Field(None, description="Partially masked phone")

    # Timestamps and status
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    status: Literal["pending", "processed", "actioned", "archived"] = "processed"
    assigned_to: Optional[str] = None
    notes: Optional[str] = None

    # Callback Tracking
    callback_status: Optional[Literal["pending", "attempted", "successful", "no_answer", "left_message", "wrong_number"]] = "pending"
    callback_attempted_at: Optional[datetime] = None
    callback_completed_at: Optional[datetime] = None
    callback_by: Optional[str] = None
    callback_notes: Optional[str] = None

    # Duplicate Detection
    caller_phone_hash: Optional[str] = Field(None, description="Hash of caller phone for grouping")
    related_voicemail_ids: List[str] = Field(default_factory=list, description="IDs of related voicemails from same caller")
    call_count_today: int = Field(1, description="Number of calls from this number today")
    is_repeat_caller: bool = Field(False, description="Whether this caller has called before")

    # Escalation Timeout Tracking
    escalation_acknowledged: bool = Field(False, description="Whether staff acknowledged the escalation")
    escalation_acknowledged_at: Optional[datetime] = None
    escalation_acknowledged_by: Optional[str] = None
    escalation_reminder_count: int = Field(0, description="Number of reminder alerts sent")
    escalation_last_reminder_at: Optional[datetime] = None

    # PMS Integration
    pms_patient_id: Optional[str] = Field(None, description="Patient ID in Practice Management System")
    pms_linked: bool = Field(False, description="Whether linked to PMS patient record")
    pms_system: Optional[str] = Field(None, description="PMS system name: best_practice, medical_director, cliniko")
    pms_appointment_id: Optional[str] = Field(None, description="Created appointment ID if any")
    pms_last_sync: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "voicemail_id": "vm_20240115_001",
                "language": "Vietnamese",
                "language_info": {
                    "detected": "Vietnamese",
                    "code": "vi",
                    "requires_interpreter": True
                },
                "urgency": {
                    "level": 4,
                    "reasoning": "Post-operative infection risk",
                    "confidence": 0.85
                },
                "intent": "Prescription",
                "summary": "Post-surgery patient reporting wound concerns",
                "action_item": "Arrange same-day review for potential infection",
                "extracted_entities": {
                    "callback_number": "0422555890",
                    "urgency_keywords": ["redness", "discharge"],
                    "symptoms": ["wound redness", "discharge"]
                },
                "ui_state": {
                    "is_ambiguous": False,
                    "needs_manual_listening": False,
                    "highlight_urgent": True
                },
                "is_pii_safe": True
            }
        }


class BatchTriageRequest(BaseModel):
    """Request schema for batch voicemail processing"""
    voicemails: List[VoicemailInput] = Field(..., min_length=1, max_length=50)


class BatchTriageResponse(BaseModel):
    """Response schema for batch processing"""
    processed_count: int
    failed_count: int
    results: List[TriagedVoicemail]
    errors: List[Dict[str, Any]] = []


class VoicemailListResponse(BaseModel):
    """Paginated list of voicemails"""
    total: int
    page: int
    page_size: int
    items: List[TriagedVoicemail]


class AnalyticsSummary(BaseModel):
    """Analytics dashboard data"""
    total_voicemails: int
    pending_count: int
    processed_today: int
    urgency_distribution: Dict[str, int]
    intent_distribution: Dict[str, int]
    avg_processing_time_ms: float
    language_distribution: Dict[str, int]
    ambiguous_count: int = 0
    low_confidence_count: int = 0


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    timestamp: str
    version: str
    components: Optional[Dict[str, str]] = None


class UpdateVoicemailRequest(BaseModel):
    """Request to update voicemail status"""
    status: Optional[Literal["pending", "processed", "actioned", "archived"]] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None

    # Callback tracking updates
    callback_status: Optional[Literal["pending", "attempted", "successful", "no_answer", "left_message", "wrong_number"]] = None
    callback_by: Optional[str] = None
    callback_notes: Optional[str] = None

    # Escalation acknowledgment
    acknowledge_escalation: Optional[bool] = None
    acknowledged_by: Optional[str] = None

    # PMS linking
    pms_patient_id: Optional[str] = None
    pms_system: Optional[str] = None


class CallbackUpdateRequest(BaseModel):
    """Request to update callback status"""
    callback_status: Literal["attempted", "successful", "no_answer", "left_message", "wrong_number"]
    callback_by: str
    callback_notes: Optional[str] = None


class PMSLinkRequest(BaseModel):
    """Request to link voicemail to PMS patient"""
    pms_system: Literal["best_practice", "medical_director", "cliniko", "other"]
    pms_patient_id: str
    create_appointment: bool = False
    appointment_type: Optional[str] = None
    appointment_notes: Optional[str] = None
