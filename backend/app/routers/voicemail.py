"""
Heidi Calls: Voicemail API Router
RESTful endpoints for voicemail management
Enhanced with confidence scoring and entity extraction
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import List, Optional
from datetime import datetime, timedelta
import uuid

from app.models.schemas import (
    VoicemailInput,
    TriagedVoicemail,
    BatchTriageRequest,
    BatchTriageResponse,
    VoicemailListResponse,
    UpdateVoicemailRequest,
    UrgencyInfo,
    IntentType,
    LanguageInfo,
    ExtractedEntities,
    UIState,
    EscalationInfo,
    LocationInfo,
    PatientMatchInfo
)
from app.services.triage_service import triage_service
from app.services.emergency_escalation import emergency_escalation, EMERGENCY_SCRIPT_BILINGUAL
from app.services.smart_routing import smart_routing

router = APIRouter()

# In-memory storage for demo (replace with database in production)
voicemail_store: dict[str, TriagedVoicemail] = {}

# Auto-hide actioned items after this many hours (archived items are kept)
ACTIONED_HIDE_HOURS = 48


def _get_recent_time(hours_ago: float = 0, minutes_ago: float = 0) -> datetime:
    """Generate a recent timestamp relative to now"""
    return datetime.utcnow() - timedelta(hours=hours_ago, minutes=minutes_ago)


def _seed_demo_data():
    """Seed demo data with enhanced entity extraction and confidence scores"""
    demo_voicemails = [
        {
            "voicemail_id": "vm_20240115_demo001",
            "language": "English",
            "language_info": LanguageInfo(detected="English", code="en", requires_interpreter=False),
            "urgency": UrgencyInfo(level=5, reasoning="Patient reporting severe chest pain and shortness of breath", confidence=0.95),
            "intent": IntentType.EMERGENCY,
            "summary": "Patient experiencing chest pain and difficulty breathing for the past hour",
            "action_item": "IMMEDIATE: Contact patient and advise to call 000 or present to ED immediately",
            "extracted_entities": ExtractedEntities(
                callback_number="0412345789",
                callback_number_raw="●●●●●●●789",
                urgency_keywords=["chest pain", "trouble breathing", "urgently"],
                symptoms=["chest pain", "shortness of breath"],
                medicare_number="2345678901",
                medicare_number_masked="XXXX XXXX X01",
                mentioned_doctor=None,
                mentioned_location=None
            ),
            "location_info": LocationInfo(
                assigned_location="harbour",
                location_confidence=0.75,
                routing_reason="patient_history",
                available_locations=["harbour", "sunset", "central", "northside"]
            ),
            "patient_match": PatientMatchInfo(
                medicare_matched=True,
                patient_id="PAT-678901",
                match_confidence=0.95,
                previous_location="harbour"
            ),
            "ui_state": UIState(is_ambiguous=False, needs_manual_listening=False, highlight_urgent=True),
            "escalation": EscalationInfo(
                escalation_triggered=True,
                emergency_alert_sent=True,
                intervention_status="Voice_Alert_Sent",
                timestamp_escalated=_get_recent_time(minutes_ago=25).isoformat() + "Z",
                emergency_script=EMERGENCY_SCRIPT_BILINGUAL,
                sms_sent_to="+61400000001",
                actions_taken=["SMS_Alert_Sent_To_Manager", "Voice_Alert_Sent_To_Patient"]
            ),
                        "is_pii_safe": True,
            "redacted_transcript": "Hi, this is [NAME REDACTED] calling. I've been having really bad chest pain for the past hour and I'm having trouble breathing. My Medicare is [MEDICARE REDACTED]. Please call me back urgently at ●●●●●●●789.",
            "caller_phone_redacted": "●●●●●●●789",
            "caller_phone_hash": "hash_0412345789",
            "call_count_today": 2,
            "is_repeat_caller": True,
            "related_voicemail_ids": ["vm_20240115_demo001b"],
            "callback_status": "pending",
            "pms_linked": True,
            "pms_system": "best_practice",
            "pms_patient_id": "BP-001",
            "created_at": _get_recent_time(minutes_ago=25),
            "processed_at": _get_recent_time(minutes_ago=24),
            "status": "processed"
        },
        # Duplicate call from same patient (earlier call)
        {
            "voicemail_id": "vm_20240115_demo001b",
            "language": "English",
            "language_info": LanguageInfo(detected="English", code="en", requires_interpreter=False),
            "urgency": UrgencyInfo(level=3, reasoning="Patient reporting mild chest discomfort", confidence=0.75),
            "intent": IntentType.BOOKING,
            "summary": "Patient requesting appointment for chest discomfort - earlier call before symptoms worsened",
            "action_item": "Schedule appointment with GP",
            "extracted_entities": ExtractedEntities(
                callback_number="0412345789",
                callback_number_raw="●●●●●●●789",
                urgency_keywords=["chest", "discomfort"],
                symptoms=["mild chest discomfort"],
                medicare_number="2345678901",
                medicare_number_masked="XXXX XXXX X01",
            ),
            "ui_state": UIState(is_ambiguous=False, needs_manual_listening=False, highlight_urgent=False),
            "is_pii_safe": True,
            "redacted_transcript": "Hi, this is [NAME REDACTED]. I've been having some mild chest discomfort. Could I book an appointment to see the doctor? My number is ●●●●●●●789.",
            "caller_phone_redacted": "●●●●●●●789",
            "caller_phone_hash": "hash_0412345789",
            "call_count_today": 2,
            "is_repeat_caller": True,
            "related_voicemail_ids": ["vm_20240115_demo001"],
            "callback_status": "pending",
            "created_at": _get_recent_time(hours_ago=1, minutes_ago=30),
            "processed_at": _get_recent_time(hours_ago=1, minutes_ago=29),
            "status": "processed"
        },
        {
            "voicemail_id": "vm_20240115_demo002",
            "language": "English",
            "language_info": LanguageInfo(detected="English", code="en", requires_interpreter=False),
            "urgency": UrgencyInfo(level=4, reasoning="Patient without critical cardiac medication for 2 days", confidence=0.88),
            "intent": IntentType.PRESCRIPTION,
            "summary": "Patient needs urgent refill of blood pressure medication - has been without for 2 days",
            "action_item": "Flag for Dr. Wong at Sunset clinic for prescriber review TODAY - arrange e-script for antihypertensive",
            "extracted_entities": ExtractedEntities(
                callback_number="0412345456",
                callback_number_raw="●●●●●●●456",
                urgency_keywords=["run out", "two days", "blood pressure"],
                medication_names=["blood pressure tablets", "antihypertensive"],
                symptoms=[],
                medicare_number="3456789012",
                medicare_number_masked="XXXX XXXX X12",
                mentioned_doctor="Dr. Michael Wong",
                mentioned_location=None
            ),
            "location_info": LocationInfo(
                assigned_location="sunset",
                location_confidence=0.85,
                routing_reason="doctor_association",
                available_locations=["harbour", "sunset", "central", "northside"]
            ),
            "patient_match": PatientMatchInfo(
                medicare_matched=True,
                patient_id="PAT-789012",
                match_confidence=0.95,
                previous_location="sunset"
            ),
            "ui_state": UIState(is_ambiguous=False, needs_manual_listening=False, highlight_urgent=True),
                        "is_pii_safe": True,
            "redacted_transcript": "Hello, this is [NAME REDACTED]. I need to speak to Dr Wong about my blood pressure tablets. I've completely run out and my chemist says they need a new script. I normally take them twice a day and haven't had any for two days now. My Medicare is [MEDICARE REDACTED]. Please call me back at ●●●●●●●456.",
            "caller_phone_redacted": "●●●●●●●456",
            "created_at": _get_recent_time(hours_ago=2),
            "processed_at": _get_recent_time(hours_ago=1, minutes_ago=59),
            "status": "processed"
        },
        {
            "voicemail_id": "vm_20240115_demo003",
            "language": "Mandarin Chinese",
            "language_info": LanguageInfo(detected="Mandarin Chinese", code="zh", requires_interpreter=True),
            "urgency": UrgencyInfo(level=2, reasoning="Routine appointment booking with no clinical urgency", confidence=0.92),
            "intent": IntentType.BOOKING,
            "summary": "Patient requesting to schedule a routine health check-up for next week at Central clinic",
            "action_item": "Call back to schedule appointment at Central City Clinic - Mandarin interpreter required",
            "extracted_entities": ExtractedEntities(
                callback_number="0412345123",
                callback_number_raw="●●●●●●●123",
                urgency_keywords=[],
                symptoms=[],
                medicare_number="4567890123",
                medicare_number_masked="XXXX XXXX X23",
                mentioned_doctor=None,
                mentioned_location="Central City Clinic"
            ),
            "location_info": LocationInfo(
                assigned_location="central",
                location_confidence=0.95,
                routing_reason="location_mentioned",
                available_locations=["harbour", "sunset", "central", "northside"]
            ),
            "patient_match": PatientMatchInfo(
                medicare_matched=True,
                patient_id="PAT-890123",
                match_confidence=0.95,
                previous_location="central"
            ),
            "ui_state": UIState(is_ambiguous=False, needs_manual_listening=False, highlight_urgent=False),
            "is_pii_safe": True,
            "redacted_transcript": "你好，我叫[NAME REDACTED]，我想在Central诊所预约下周的体检。我的Medicare号码是[MEDICARE REDACTED]。请回电话，谢谢。电话是●●●●●●●123。",
            "caller_phone_redacted": "●●●●●●●123",
            "created_at": _get_recent_time(hours_ago=5),
            "processed_at": _get_recent_time(hours_ago=4, minutes_ago=45),
            "status": "actioned"
        },
        {
            "voicemail_id": "vm_20240115_demo004",
            "language": "English",
            "language_info": LanguageInfo(detected="English", code="en", requires_interpreter=False),
            "urgency": UrgencyInfo(level=3, reasoning="Patient inquiring about non-urgent test results", confidence=0.85),
            "intent": IntentType.RESULTS,
            "summary": "Patient calling to follow up on blood test results from last week",
            "action_item": "Retrieve pathology results and arrange callback or appointment to discuss",
            "extracted_entities": ExtractedEntities(
                callback_number="0412345567",
                callback_number_raw="●●●●●●●567",
                urgency_keywords=["blood test results"],
                symptoms=[]
            ),
            "ui_state": UIState(is_ambiguous=False, needs_manual_listening=False, highlight_urgent=False),
            "is_pii_safe": True,
            "redacted_transcript": "Hi there, it's [NAME REDACTED] calling about my blood test results from last week. The doctor said to call after a few days but I haven't heard anything. Can someone please let me know? My number is ●●●●●●●567.",
            "caller_phone_redacted": "●●●●●●●567",
            "created_at": _get_recent_time(hours_ago=3),
            "processed_at": _get_recent_time(hours_ago=2, minutes_ago=59),
            "status": "pending"
        },
        {
            "voicemail_id": "vm_20240115_demo005",
            "language": "Vietnamese",
            "language_info": LanguageInfo(detected="Vietnamese", code="vi", requires_interpreter=True),
            "urgency": UrgencyInfo(level=4, reasoning="Post-operative patient with concerning wound symptoms; patient sounds distressed", confidence=0.78),
            "intent": IntentType.PRESCRIPTION,
            "summary": "Post-surgery patient reporting redness and discharge from wound site",
            "action_item": "URGENT: Arrange same-day review at Harbour Medical Centre for potential surgical site infection - Vietnamese interpreter required",
            "extracted_entities": ExtractedEntities(
                callback_number="0422555890",
                callback_number_raw="●●●●●●●890",
                urgency_keywords=["redness", "discharge", "surgery", "worried"],
                symptoms=["wound redness", "wound discharge", "post-operative concern"],
                medicare_number="5678901234",
                medicare_number_masked="XXXX XXXX X34",
                mentioned_doctor="Dr. Lisa Patel",
                mentioned_location=None
            ),
            "location_info": LocationInfo(
                assigned_location="harbour",
                location_confidence=0.85,
                routing_reason="doctor_association",
                available_locations=["harbour", "sunset", "central", "northside"]
            ),
            "patient_match": PatientMatchInfo(
                medicare_matched=True,
                patient_id="PAT-901234",
                match_confidence=0.95,
                previous_location="harbour"
            ),
            "ui_state": UIState(is_ambiguous=False, needs_manual_listening=False, highlight_urgent=True),
            "is_pii_safe": True,
            "redacted_transcript": "Xin chào, tôi là [NAME REDACTED]. Tôi vừa mổ với Dr Patel tuần trước và vết thương bắt đầu đỏ và có mủ. Medicare của tôi là [MEDICARE REDACTED]. Tôi lo lắng lắm. Xin gọi lại cho tôi ●●●●●●●890.",
            "caller_phone_redacted": "●●●●●●●890",
            "created_at": _get_recent_time(hours_ago=1),
            "processed_at": _get_recent_time(minutes_ago=59),
            "status": "processed"
        },
        {
            "voicemail_id": "vm_20240115_demo006",
            "language": "English",
            "language_info": LanguageInfo(detected="English", code="en", requires_interpreter=False),
            "urgency": UrgencyInfo(level=1, reasoning="General feedback with no clinical content", confidence=0.98),
            "intent": IntentType.OTHER,
            "summary": "Patient calling to thank staff for excellent care during recent visit",
            "action_item": "No action required - positive feedback for records",
            "extracted_entities": ExtractedEntities(
                callback_number=None,
                urgency_keywords=[],
                symptoms=[]
            ),
            "ui_state": UIState(is_ambiguous=False, needs_manual_listening=False, highlight_urgent=False),
            "is_pii_safe": True,
            "redacted_transcript": "Hello, I just wanted to call and say thank you to everyone at the clinic. The service was wonderful during my last visit. Keep up the great work!",
            "caller_phone_redacted": "●●●●●●●234",
            "created_at": _get_recent_time(hours_ago=24),
            "processed_at": _get_recent_time(hours_ago=23, minutes_ago=55),
            "status": "archived"
        },
        {
            "voicemail_id": "vm_20240115_demo007",
            "language": "Greek",
            "language_info": LanguageInfo(detected="Greek", code="el", requires_interpreter=True),
            "urgency": UrgencyInfo(level=3, reasoning="Standard prescription renewal request", confidence=0.82),
            "intent": IntentType.PRESCRIPTION,
            "summary": "Patient requesting refill of diabetes medication - routine renewal",
            "action_item": "Process standard script renewal for metformin - Greek interpreter may be needed for callback",
            "extracted_entities": ExtractedEntities(
                callback_number="0412345345",
                callback_number_raw="●●●●●●●345",
                urgency_keywords=["prescription renewal"],
                medication_names=["diabetes medication", "metformin"],
                symptoms=[]
            ),
            "ui_state": UIState(is_ambiguous=False, needs_manual_listening=False, highlight_urgent=False),
            "is_pii_safe": True,
            "redacted_transcript": "Γεια σας, είμαι ο/η [NAME REDACTED]. Χρειάζομαι ανανέωση της συνταγής για τα χάπια του διαβήτη μου. Παρακαλώ καλέστε με στο ●●●●●●●345.",
            "caller_phone_redacted": "●●●●●●●345",
            "created_at": _get_recent_time(hours_ago=4),
            "processed_at": _get_recent_time(hours_ago=3, minutes_ago=55),
            "status": "processed"
        },
        # New: Ambiguous/low confidence example - Heavy accent case
        {
            "voicemail_id": "vm_20240115_demo008",
            "language": "English",
            "language_info": LanguageInfo(detected="English", code="en", requires_interpreter=False),
            "urgency": UrgencyInfo(level=3, reasoning="Heavy accent detected - transcription may be inaccurate. Unable to confidently assess urgency.", confidence=0.35),
            "intent": IntentType.AMBIGUOUS,
            "summary": "Possible medication or pain complaint. Heavy accent - manual review recommended.",
            "action_item": "MANUAL REVIEW: Listen to original recording - speaker has strong accent, AI transcription may be inaccurate",
            "extracted_entities": ExtractedEntities(
                callback_number="0412345999",
                callback_number_raw="●●●●●●●999",
                urgency_keywords=["pain", "medication", "doctor"],
                symptoms=["possible chest/back pain"]
            ),
            "ui_state": UIState(is_ambiguous=True, needs_manual_listening=True, highlight_urgent=False),
            "is_pii_safe": True,
            "redacted_transcript": "Hallo, dis is [NAME REDACTED] calling. I am {{heving??having}} some problem wit my {{chest area??chest/test area}}, da pain is {{coming and going??coming in/going}} since yesterday. I {{tink??think/drink}} I need to see da doctor for dis. Also my {{madication??medication}}, da one for da blood pressure, I am running out. Please call me back on ●●●●●●●999. {{Tank??Thank}} you very much.",
            "caller_phone_redacted": "●●●●●●●999",
            "created_at": _get_recent_time(hours_ago=6),
            "processed_at": _get_recent_time(hours_ago=5, minutes_ago=59),
            "status": "pending"
        },
        # Another accent example - Strong Australian accent
        {
            "voicemail_id": "vm_20240115_demo009",
            "language": "English",
            "language_info": LanguageInfo(detected="English", code="en-AU", requires_interpreter=False),
            "urgency": UrgencyInfo(level=3, reasoning="Strong regional accent affecting transcription accuracy. Content appears non-urgent but verification recommended.", confidence=0.42),
            "intent": IntentType.AMBIGUOUS,
            "summary": "Appointment or test results inquiry. Strong Australian accent - please verify by listening.",
            "action_item": "MANUAL REVIEW: Listen to recording to confirm intent - heavy Australian slang/accent detected",
            "extracted_entities": ExtractedEntities(
                callback_number="0412345888",
                callback_number_raw="●●●●●●●888",
                urgency_keywords=[],
                symptoms=[]
            ),
            "ui_state": UIState(is_ambiguous=True, needs_manual_listening=True, highlight_urgent=False),
            "is_pii_safe": True,
            "redacted_transcript": "G'day mate, it's [NAME REDACTED] here. Just wanna {{suss out??check/assess}} me blood test results from {{last arvo??last afternoon}}. The doc {{reckons??recommends/records}} I might need a {{squiz??look/check}} at 'em before me next appointment. {{Give us a bell??Give me a call}} when ya can, yeah? Cheers, ●●●●●●●888.",
            "caller_phone_redacted": "●●●●●●●888",
            "created_at": _get_recent_time(hours_ago=8),
            "processed_at": _get_recent_time(hours_ago=7, minutes_ago=59),
            "status": "pending"
        },
    ]

    for vm_data in demo_voicemails:
        vm = TriagedVoicemail(**vm_data)
        voicemail_store[vm.voicemail_id] = vm


# Seed demo data on module load
_seed_demo_data()


@router.post("/triage", response_model=TriagedVoicemail)
async def triage_voicemail(voicemail: VoicemailInput):
    """
    Process and triage a new voicemail

    - Applies PII redaction
    - Detects language
    - Classifies urgency (1-5) with confidence score
    - Identifies intent (including Ambiguous for unclear content)
    - Extracts entities (phone numbers, symptoms, medications)
    - Generates actionable summary
    """
    try:
        result = await triage_service.triage(voicemail)
        voicemail_store[result.voicemail_id] = result
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Triage processing failed: {str(e)}")


@router.post("/triage/batch", response_model=BatchTriageResponse)
async def batch_triage_voicemails(request: BatchTriageRequest, background_tasks: BackgroundTasks):
    """
    Process multiple voicemails in batch

    For large batches (>10), processing continues in background.
    """
    results = []
    errors = []

    for idx, voicemail in enumerate(request.voicemails):
        try:
            result = await triage_service.triage(voicemail)
            voicemail_store[result.voicemail_id] = result
            results.append(result)
        except Exception as e:
            errors.append({"index": idx, "error": str(e)})

    return BatchTriageResponse(
        processed_count=len(results),
        failed_count=len(errors),
        results=results,
        errors=errors
    )


@router.get("/", response_model=VoicemailListResponse)
async def list_voicemails(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    urgency_min: Optional[int] = Query(None, ge=1, le=5),
    urgency_max: Optional[int] = Query(None, ge=1, le=5),
    intent: Optional[str] = Query(None),
    ambiguous_only: bool = Query(False),
    sort_by: str = Query("created_at", pattern="^(created_at|urgency|status|confidence)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    # Advanced filters
    phone: Optional[str] = Query(None, description="Filter by phone number (partial match)"),
    symptom: Optional[str] = Query(None, description="Filter by symptom keyword"),
    medication: Optional[str] = Query(None, description="Filter by medication name"),
    doctor: Optional[str] = Query(None, description="Filter by doctor name"),
    hide_old_actioned: bool = Query(True, description="Hide actioned items older than 48 hours")
):
    """
    List all voicemails with filtering and pagination

    Advanced filters:
    - phone: Filter by caller phone number (partial match)
    - symptom: Filter by symptom keywords
    - medication: Filter by medication names
    - doctor: Filter by mentioned doctor
    - hide_old_actioned: Auto-hide actioned items older than 48 hours (default: True)
    """
    items = list(voicemail_store.values())
    now = datetime.utcnow()

    # Auto-hide old actioned items (but keep archived)
    if hide_old_actioned:
        cutoff = now - timedelta(hours=ACTIONED_HIDE_HOURS)
        items = [v for v in items if not (
            v.status == "actioned" and v.created_at < cutoff
        )]

    # Apply filters
    if status:
        items = [v for v in items if v.status == status]
    if urgency_min:
        items = [v for v in items if v.urgency.level >= urgency_min]
    if urgency_max:
        items = [v for v in items if v.urgency.level <= urgency_max]
    if intent:
        items = [v for v in items if v.intent.value == intent]
    if ambiguous_only:
        items = [v for v in items if v.intent == IntentType.AMBIGUOUS or
                 (v.ui_state and v.ui_state.is_ambiguous)]

    # Advanced filters - phone number
    if phone:
        phone_lower = phone.lower().replace(" ", "")
        items = [v for v in items if (
            (v.caller_phone_redacted and phone_lower in v.caller_phone_redacted.lower().replace(" ", "")) or
            (v.extracted_entities and v.extracted_entities.callback_number and
             phone_lower in v.extracted_entities.callback_number.lower().replace(" ", ""))
        )]

    # Advanced filters - symptoms
    if symptom:
        symptom_lower = symptom.lower()
        items = [v for v in items if (
            v.extracted_entities and v.extracted_entities.symptoms and
            any(symptom_lower in s.lower() for s in v.extracted_entities.symptoms)
        ) or (
            # Also search in transcript
            v.redacted_transcript and symptom_lower in v.redacted_transcript.lower()
        )]

    # Advanced filters - medication
    if medication:
        med_lower = medication.lower()
        items = [v for v in items if (
            v.extracted_entities and v.extracted_entities.medication_names and
            any(med_lower in m.lower() for m in v.extracted_entities.medication_names)
        ) or (
            v.redacted_transcript and med_lower in v.redacted_transcript.lower()
        )]

    # Advanced filters - doctor
    if doctor:
        doctor_lower = doctor.lower()
        items = [v for v in items if (
            v.extracted_entities and v.extracted_entities.mentioned_doctor and
            doctor_lower in v.extracted_entities.mentioned_doctor.lower()
        )]

    # Sort
    reverse = sort_order == "desc"
    if sort_by == "urgency":
        items.sort(key=lambda x: x.urgency.level, reverse=reverse)
    elif sort_by == "status":
        items.sort(key=lambda x: x.status, reverse=reverse)
    elif sort_by == "confidence":
        items.sort(key=lambda x: x.urgency.confidence, reverse=reverse)
    else:
        items.sort(key=lambda x: x.created_at, reverse=reverse)

    # Paginate
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    items = items[start:end]

    return VoicemailListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items
    )


@router.get("/{voicemail_id}", response_model=TriagedVoicemail)
async def get_voicemail(voicemail_id: str):
    """Get a specific voicemail by ID"""
    if voicemail_id not in voicemail_store:
        raise HTTPException(status_code=404, detail="Voicemail not found")
    return voicemail_store[voicemail_id]


@router.patch("/{voicemail_id}", response_model=TriagedVoicemail)
async def update_voicemail(voicemail_id: str, update: UpdateVoicemailRequest):
    """Update voicemail status, assignment, callback tracking, or notes"""
    if voicemail_id not in voicemail_store:
        raise HTTPException(status_code=404, detail="Voicemail not found")

    voicemail = voicemail_store[voicemail_id]

    # Basic updates
    if update.status:
        voicemail.status = update.status
    if update.assigned_to is not None:
        voicemail.assigned_to = update.assigned_to
    if update.notes is not None:
        voicemail.notes = update.notes

    # Callback tracking updates
    if update.callback_status:
        voicemail.callback_status = update.callback_status
        if update.callback_status == "attempted":
            voicemail.callback_attempted_at = datetime.utcnow()
        elif update.callback_status in ["successful", "no_answer", "left_message", "wrong_number"]:
            voicemail.callback_completed_at = datetime.utcnow()
    if update.callback_by:
        voicemail.callback_by = update.callback_by
    if update.callback_notes:
        voicemail.callback_notes = update.callback_notes

    # Escalation acknowledgment
    if update.acknowledge_escalation:
        voicemail.escalation_acknowledged = True
        voicemail.escalation_acknowledged_at = datetime.utcnow()
        voicemail.escalation_acknowledged_by = update.acknowledged_by

    # PMS linking
    if update.pms_patient_id:
        voicemail.pms_patient_id = update.pms_patient_id
        voicemail.pms_linked = True
        voicemail.pms_last_sync = datetime.utcnow()
    if update.pms_system:
        voicemail.pms_system = update.pms_system

    voicemail_store[voicemail_id] = voicemail
    return voicemail


@router.delete("/{voicemail_id}")
async def delete_voicemail(voicemail_id: str):
    """Archive/delete a voicemail"""
    if voicemail_id not in voicemail_store:
        raise HTTPException(status_code=404, detail="Voicemail not found")

    del voicemail_store[voicemail_id]
    return {"status": "deleted", "voicemail_id": voicemail_id}


# ============================================================================
# DUPLICATE DETECTION
# ============================================================================

@router.get("/duplicates/by-phone/{phone_hash}")
async def get_duplicates_by_phone(phone_hash: str):
    """Get all voicemails from the same phone number"""
    duplicates = [v for v in voicemail_store.values() if v.caller_phone_hash == phone_hash]
    return {
        "phone_hash": phone_hash,
        "count": len(duplicates),
        "voicemails": sorted(duplicates, key=lambda x: x.created_at, reverse=True)
    }


@router.get("/duplicates/summary")
async def get_duplicate_summary():
    """Get summary of repeat callers"""
    phone_counts = {}
    for v in voicemail_store.values():
        if v.caller_phone_hash:
            if v.caller_phone_hash not in phone_counts:
                phone_counts[v.caller_phone_hash] = {
                    "count": 0,
                    "voicemail_ids": [],
                    "phone_redacted": v.caller_phone_redacted,
                    "latest_urgency": 0
                }
            phone_counts[v.caller_phone_hash]["count"] += 1
            phone_counts[v.caller_phone_hash]["voicemail_ids"].append(v.voicemail_id)
            if v.urgency.level > phone_counts[v.caller_phone_hash]["latest_urgency"]:
                phone_counts[v.caller_phone_hash]["latest_urgency"] = v.urgency.level

    # Filter to only repeat callers (2+ calls)
    repeat_callers = {k: v for k, v in phone_counts.items() if v["count"] >= 2}

    return {
        "total_repeat_callers": len(repeat_callers),
        "repeat_callers": repeat_callers
    }


# ============================================================================
# CALLBACK TRACKING
# ============================================================================

@router.post("/{voicemail_id}/callback")
async def record_callback(voicemail_id: str, callback_status: str, callback_by: str, notes: Optional[str] = None):
    """Record a callback attempt"""
    if voicemail_id not in voicemail_store:
        raise HTTPException(status_code=404, detail="Voicemail not found")

    voicemail = voicemail_store[voicemail_id]

    voicemail.callback_status = callback_status
    voicemail.callback_by = callback_by
    voicemail.callback_notes = notes

    if callback_status == "attempted":
        voicemail.callback_attempted_at = datetime.utcnow()
    else:
        voicemail.callback_completed_at = datetime.utcnow()

    # Auto-mark as actioned if callback was successful
    if callback_status == "successful":
        voicemail.status = "actioned"

    voicemail_store[voicemail_id] = voicemail
    return voicemail


@router.get("/callbacks/pending")
async def get_pending_callbacks():
    """Get all voicemails needing callback"""
    pending = [v for v in voicemail_store.values()
               if v.callback_status in ["pending", "attempted", "no_answer"]
               and v.status not in ["archived"]]
    return {
        "count": len(pending),
        "voicemails": sorted(pending, key=lambda x: (x.urgency.level * -1, x.created_at))
    }


# ============================================================================
# ESCALATION TIMEOUT
# ============================================================================

@router.get("/escalations/active")
async def get_active_escalations():
    """Get all active escalations that need attention"""
    active = []
    now = datetime.utcnow()

    for v in voicemail_store.values():
        if v.escalation and v.escalation.escalation_triggered and not v.escalation_acknowledged:
            # Calculate time since escalation
            escalated_at = datetime.fromisoformat(v.escalation.timestamp_escalated.replace('Z', '+00:00'))
            minutes_since = (now - escalated_at.replace(tzinfo=None)).total_seconds() / 60

            active.append({
                "voicemail_id": v.voicemail_id,
                "summary": v.summary,
                "urgency_level": v.urgency.level,
                "escalated_at": v.escalation.timestamp_escalated,
                "minutes_since_escalation": round(minutes_since, 1),
                "needs_re_alert": minutes_since > 15,  # Re-alert after 15 min
                "reminder_count": v.escalation_reminder_count,
                "callback_number": v.extracted_entities.callback_number if v.extracted_entities else None
            })

    return {
        "count": len(active),
        "escalations": sorted(active, key=lambda x: x["minutes_since_escalation"], reverse=True)
    }


@router.post("/{voicemail_id}/acknowledge-escalation")
async def acknowledge_escalation(voicemail_id: str, acknowledged_by: str):
    """Acknowledge an escalation to stop re-alerts"""
    if voicemail_id not in voicemail_store:
        raise HTTPException(status_code=404, detail="Voicemail not found")

    voicemail = voicemail_store[voicemail_id]

    voicemail.escalation_acknowledged = True
    voicemail.escalation_acknowledged_at = datetime.utcnow()
    voicemail.escalation_acknowledged_by = acknowledged_by

    voicemail_store[voicemail_id] = voicemail
    return {"status": "acknowledged", "voicemail_id": voicemail_id}


@router.post("/{voicemail_id}/send-reminder")
async def send_escalation_reminder(voicemail_id: str):
    """Send another reminder for unacknowledged escalation"""
    if voicemail_id not in voicemail_store:
        raise HTTPException(status_code=404, detail="Voicemail not found")

    voicemail = voicemail_store[voicemail_id]

    voicemail.escalation_reminder_count += 1
    voicemail.escalation_last_reminder_at = datetime.utcnow()

    # In production, this would trigger actual SMS/notification
    print(f"🚨 REMINDER #{voicemail.escalation_reminder_count}: Unacknowledged Level 5 escalation for {voicemail_id}")

    voicemail_store[voicemail_id] = voicemail
    return {
        "status": "reminder_sent",
        "reminder_count": voicemail.escalation_reminder_count
    }


# ============================================================================
# PMS INTEGRATION
# ============================================================================

# Simulated PMS patient database
PMS_PATIENTS = {
    "best_practice": {
        "BP-001": {"name": "John Smith", "dob": "1965-03-15", "phone": "0412345678"},
        "BP-002": {"name": "Mary Johnson", "dob": "1978-07-22", "phone": "0412345789"},
    },
    "medical_director": {
        "MD-001": {"name": "Sarah Chen", "dob": "1982-11-08", "phone": "0412345456"},
    },
    "cliniko": {
        "CL-001": {"name": "David Wong", "dob": "1990-01-30", "phone": "0412345123"},
    }
}


@router.get("/pms/search")
async def search_pms_patient(
    pms_system: str,
    phone: Optional[str] = None,
    name: Optional[str] = None
):
    """Search for patient in PMS by phone or name"""
    if pms_system not in PMS_PATIENTS:
        return {"error": f"Unknown PMS system: {pms_system}", "patients": []}

    patients = PMS_PATIENTS[pms_system]
    results = []

    for pid, pdata in patients.items():
        if phone and phone in pdata.get("phone", ""):
            results.append({"patient_id": pid, **pdata, "match_type": "phone"})
        elif name and name.lower() in pdata.get("name", "").lower():
            results.append({"patient_id": pid, **pdata, "match_type": "name"})

    return {
        "pms_system": pms_system,
        "query": {"phone": phone, "name": name},
        "count": len(results),
        "patients": results
    }


@router.post("/{voicemail_id}/link-pms")
async def link_to_pms(voicemail_id: str, pms_system: str, pms_patient_id: str):
    """Link voicemail to a PMS patient record"""
    if voicemail_id not in voicemail_store:
        raise HTTPException(status_code=404, detail="Voicemail not found")

    voicemail = voicemail_store[voicemail_id]

    voicemail.pms_system = pms_system
    voicemail.pms_patient_id = pms_patient_id
    voicemail.pms_linked = True
    voicemail.pms_last_sync = datetime.utcnow()

    voicemail_store[voicemail_id] = voicemail

    return {
        "status": "linked",
        "voicemail_id": voicemail_id,
        "pms_system": pms_system,
        "pms_patient_id": pms_patient_id
    }


@router.post("/{voicemail_id}/create-appointment")
async def create_pms_appointment(
    voicemail_id: str,
    appointment_type: str = "General Consultation",
    preferred_date: Optional[str] = None,
    notes: Optional[str] = None
):
    """Create appointment in PMS from voicemail"""
    if voicemail_id not in voicemail_store:
        raise HTTPException(status_code=404, detail="Voicemail not found")

    voicemail = voicemail_store[voicemail_id]

    if not voicemail.pms_linked:
        raise HTTPException(status_code=400, detail="Voicemail not linked to PMS patient")

    # Simulated appointment creation
    appointment_id = f"APT-{voicemail_id[-8:]}"
    voicemail.pms_appointment_id = appointment_id

    voicemail_store[voicemail_id] = voicemail

    return {
        "status": "appointment_created",
        "appointment_id": appointment_id,
        "pms_system": voicemail.pms_system,
        "patient_id": voicemail.pms_patient_id,
        "type": appointment_type,
        "notes": notes or voicemail.summary
    }
