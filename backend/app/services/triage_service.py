"""
Heidi Calls: AI Triage Service
Agentic workflow for medical voicemail classification and prioritization

Features:
- Multi-language detection and translation
- Medical urgency classification (1-5 scale)
- Intent recognition
- Actionable summary generation
"""

import json
import re
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
import uuid
import httpx
from dataclasses import dataclass

from app.models.schemas import (
    VoicemailInput,
    TriagedVoicemail,
    UrgencyInfo,
    IntentType,
    LanguageInfo,
    ExtractedEntities,
    UIState,
    LocationInfo,
    PatientMatchInfo,
    EscalationInfo
)
from app.utils.pii_filter import pii_filter
from app.services.smart_routing import smart_routing
from app.services.emergency_escalation import emergency_escalation


# ============================================================================
# MEDICAL TRIAGE SYSTEM PROMPT
# ============================================================================

MEDICAL_TRIAGE_SYSTEM_PROMPT = """You are Heidi, an expert medical voicemail triage AI assistant for clinic administrative staff. Your role is to analyze voicemail transcripts and provide structured, actionable intelligence.

## CORE PRINCIPLES

1. **Patient Safety First**: When in doubt, escalate urgency. A false positive (higher urgency) is safer than a false negative.
2. **Clinical Accuracy**: Use appropriate medical terminology while keeping summaries accessible to administrative staff.
3. **Actionable Output**: Every triage must include a clear, specific next step.
4. **Privacy Awareness**: Never include or reference any PII in your output - assume all PII has been redacted.

## URGENCY CLASSIFICATION SCALE

**Level 5 - CRITICAL/EMERGENCY** (Immediate callback required)
- Chest pain, difficulty breathing, signs of stroke
- Severe bleeding, loss of consciousness
- Suicidal ideation or psychiatric emergency
- Allergic reactions (anaphylaxis symptoms)
- Post-operative complications (fever, wound issues)
- Keywords: "emergency", "can't breathe", "chest pain", "severe pain", "bleeding heavily"

**Level 4 - HIGH PRIORITY** (Same-day response required)
- Medication ran out (chronic conditions: diabetes, hypertension, cardiac)
- Worsening symptoms of ongoing condition
- Post-procedure concerns
- Abnormal test results inquiry (patient indicates urgency)
- Fever with other symptoms
- Keywords: "ran out of medication", "getting worse", "urgent refill", "results were abnormal"

**Level 3 - STANDARD** (Response within 24-48 hours)
- Routine prescription refills
- Non-urgent test results inquiry
- Follow-up appointment requests
- General medical questions
- Referral requests

**Level 2 - MODERATE** (Response within 2-3 business days)
- Administrative inquiries
- Insurance/billing questions
- Medical records requests
- Non-urgent appointment changes

**Level 1 - LOW** (Response when convenient)
- General feedback
- Marketing/promotional calls
- Wrong numbers
- Incomplete/unintelligible messages

## INTENT CATEGORIES

- **Emergency**: Life-threatening situations requiring immediate medical attention
- **Prescription**: Medication refills, dosage questions, new prescriptions
- **Results**: Lab results, imaging results, test results inquiries
- **Booking**: Appointment scheduling, rescheduling, cancellations
- **Billing**: Payment inquiries, insurance questions, billing disputes
- **Referral**: Specialist referral requests, second opinions
- **Other**: Administrative, records requests, general inquiries

## LANGUAGE HANDLING

1. Detect the primary language of the voicemail
2. If non-English, translate key clinical content
3. Always provide English summary regardless of source language
4. Note language in output for staff awareness

## OUTPUT FORMAT

You must respond with ONLY a valid JSON object in this exact format:
{
    "language": "<detected language>",
    "urgency": {
        "level": <1-5>,
        "reasoning": "<brief clinical reasoning for urgency level>"
    },
    "intent": "<Booking|Prescription|Results|Emergency|Billing|Referral|Other>",
    "summary": "<clear English summary of the voicemail in 1-2 sentences>",
    "action_item": "<specific actionable next step for clinic staff>"
}

## EXAMPLES

Input: "Hi this is [NAME REDACTED] calling. I've completely run out of my blood pressure tablets and my chemist says they need a new script. I normally take them twice a day and I haven't had any for two days now."

Output:
{
    "language": "English",
    "urgency": {
        "level": 4,
        "reasoning": "Patient without antihypertensive medication for 2 days - risk of rebound hypertension and cardiovascular events"
    },
    "intent": "Prescription",
    "summary": "Patient requires urgent refill of blood pressure medication; has been without medication for 2 days",
    "action_item": "Flag for prescriber review TODAY - arrange e-script for regular antihypertensive medication"
}

Input: "你好，我想预约下周的体检，请回电话。谢谢。"

Output:
{
    "language": "Mandarin Chinese",
    "urgency": {
        "level": 2,
        "reasoning": "Routine appointment booking request with no clinical urgency"
    },
    "intent": "Booking",
    "summary": "Patient requesting to book a general check-up appointment for next week",
    "action_item": "Call back to schedule routine health check appointment - Mandarin interpreter may be needed"
}

Remember: Your output must be ONLY the JSON object, no additional text or explanation."""


# ============================================================================
# LANGUAGE DETECTION PROMPT
# ============================================================================

LANGUAGE_DETECTION_PROMPT = """Identify the primary language of the following text. 
Respond with ONLY the language name in English (e.g., "English", "Mandarin Chinese", "Spanish", "Vietnamese", "Arabic", "Greek", "Italian").

Text: {text}

Language:"""


@dataclass
class TriageConfig:
    """Configuration for the triage service"""
    api_key: Optional[str] = None
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 1024
    temperature: float = 0.1  # Low temperature for consistent clinical output
    api_base_url: str = "https://api.anthropic.com/v1"


class TriageService:
    """
    Agentic Medical Voicemail Triage Service
    
    Pipeline:
    1. PII Redaction
    2. Language Detection
    3. Medical Triage Classification
    4. Response Validation
    """
    
    def __init__(self, config: Optional[TriageConfig] = None):
        self.config = config or TriageConfig()
        self._client = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy initialization of HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                }
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def generate_voicemail_id(self) -> str:
        """Generate a unique voicemail ID"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        short_uuid = str(uuid.uuid4())[:8]
        return f"vm_{timestamp}_{short_uuid}"
    
    async def _call_llm(
        self, 
        system_prompt: str, 
        user_message: str,
        temperature: Optional[float] = None
    ) -> str:
        """Make an API call to the LLM"""
        
        # For demo/prototype: Return mock response if no API key
        if not self.config.api_key:
            return self._mock_triage_response(user_message)
        
        payload = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": temperature or self.config.temperature,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_message}
            ]
        }
        
        headers = {
            "x-api-key": self.config.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        response = await self.client.post(
            f"{self.config.api_base_url}/messages",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        
        result = response.json()
        return result["content"][0]["text"]
    
    def _mock_triage_response(self, transcript: str) -> str:
        """Generate mock triage response for demo purposes with multilingual support"""

        transcript_lower = transcript.lower()

        # ================================================================
        # MULTILINGUAL EMERGENCY KEYWORDS
        # ================================================================
        emergency_keywords = {
            "en": ["emergency", "chest pain", "can't breathe", "bleeding", "unconscious", "heart attack", "stroke"],
            "vi": ["đau ngực", "khó thở", "chảy máu", "bất tỉnh", "cấp cứu", "đau tim"],  # Vietnamese
            "zh": ["胸痛", "呼吸困难", "出血", "昏迷", "急诊", "心脏病"],  # Chinese
            "el": ["πόνος στο στήθος", "δυσκολία αναπνοής", "αιμορραγία"],  # Greek
        }

        high_priority_keywords = {
            "en": ["urgent", "ran out", "medication", "worse", "pain", "worried", "lo lắng"],
            "vi": ["cấp bách", "hết thuốc", "tệ hơn", "đau", "lo lắng"],
            "zh": ["紧急", "没药了", "更糟", "疼痛"],
        }

        prescription_keywords = ["prescription", "refill", "medication", "pills", "tablets", "script", "thuốc", "药"]
        booking_keywords = ["appointment", "book", "schedule", "reschedule", "预约", "đặt lịch"]
        results_keywords = ["results", "test", "blood work", "scan", "report", "kết quả", "结果"]

        # ================================================================
        # LANGUAGE DETECTION (Enhanced)
        # ================================================================
        language = "English"
        language_code = "en"
        requires_interpreter = False

        # Vietnamese detection (Latin script with diacritics)
        vietnamese_chars = re.search(r'[àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]', transcript, re.IGNORECASE)
        vietnamese_words = any(w in transcript_lower for w in ["xin", "chào", "tôi", "của", "gọi", "lại", "cảm ơn"])

        # Chinese detection
        chinese_chars = re.search(r'[\u4e00-\u9fff]', transcript)

        # Greek detection
        greek_chars = re.search(r'[\u0370-\u03ff]', transcript)

        if vietnamese_chars or vietnamese_words:
            language = "Vietnamese"
            language_code = "vi"
            requires_interpreter = True
        elif chinese_chars:
            language = "Mandarin Chinese"
            language_code = "zh"
            requires_interpreter = True
        elif greek_chars:
            language = "Greek"
            language_code = "el"
            requires_interpreter = True

        # ================================================================
        # URGENCY DETECTION (Multilingual)
        # ================================================================
        urgency_level = 3
        urgency_reasoning = "Standard medical inquiry requiring routine follow-up"
        confidence = 0.85

        # Check emergency keywords across all languages
        is_emergency = False
        for lang, keywords in emergency_keywords.items():
            if any(kw in transcript_lower for kw in keywords):
                is_emergency = True
                break

        is_high_priority = False
        for lang, keywords in high_priority_keywords.items():
            if any(kw in transcript_lower for kw in keywords):
                is_high_priority = True
                break

        if is_emergency:
            urgency_level = 5
            urgency_reasoning = "Emergency symptoms detected (multilingual) - potential life-threatening situation"
            confidence = 0.92
        elif is_high_priority:
            urgency_level = 4
            urgency_reasoning = "High priority indicators - patient may need urgent attention"
            confidence = 0.88

        # ================================================================
        # INTENT CLASSIFICATION
        # ================================================================
        intent = "Other"
        if is_emergency:
            intent = "Emergency"
        elif any(kw in transcript_lower for kw in prescription_keywords):
            intent = "Prescription"
        elif any(kw in transcript_lower for kw in results_keywords):
            intent = "Results"
        elif any(kw in transcript_lower for kw in booking_keywords):
            intent = "Booking"

        # ================================================================
        # ACTION ITEM
        # ================================================================
        action_map = {
            "Emergency": "IMMEDIATE: Contact patient and advise to call 000 or present to ED immediately",
            "Prescription": "Review with prescriber and arrange e-script if appropriate",
            "Results": "Retrieve results and arrange callback or appointment to discuss",
            "Booking": "Check availability and call back to confirm appointment",
            "Other": "Review message and respond within standard timeframe"
        }

        # Add interpreter note for non-English
        action = action_map.get(intent, action_map["Other"])
        if requires_interpreter:
            action += f" - {language} interpreter required"

        # ================================================================
        # BUILD RESPONSE
        # ================================================================
        attention_levels = ['routine', 'moderate', 'standard', 'urgent', 'immediate']

        mock_response = {
            "language": language,
            "language_code": language_code,
            "requires_interpreter": requires_interpreter,
            "urgency": {
                "level": urgency_level,
                "reasoning": urgency_reasoning,
                "confidence": confidence
            },
            "intent": intent,
            "summary": f"Patient message regarding {intent.lower()} matter - requires {attention_levels[urgency_level-1]} attention",
            "action_item": action
        }

        return json.dumps(mock_response)
    
    def _parse_triage_response(self, response: str) -> Dict[str, Any]:
        """Parse and validate the LLM response"""
        
        # Try to extract JSON from response
        try:
            # Handle potential markdown code blocks
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            
            return json.loads(response.strip())
        
        except json.JSONDecodeError:
            # Fallback: try to find JSON object in response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
            
            # If all fails, return default
            return {
                "language": "Unknown",
                "urgency": {"level": 3, "reasoning": "Unable to parse AI response"},
                "intent": "Other",
                "summary": "Message requires manual review",
                "action_item": "Manual review required - AI processing error"
            }
    
    def _validate_triage_output(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize the triage output"""
        
        # Ensure urgency level is in range
        if "urgency" in data:
            data["urgency"]["level"] = max(1, min(5, data["urgency"].get("level", 3)))
        
        # Normalize intent
        valid_intents = ["Booking", "Prescription", "Results", "Emergency", "Billing", "Referral", "Other"]
        if data.get("intent") not in valid_intents:
            data["intent"] = "Other"
        
        return data
    
    def _extract_phone_from_text(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract phone number from transcript"""
        # Australian phone patterns
        patterns = [
            r'0\d{3}\s?\d{3}\s?\d{3}',  # 0412 345 678
            r'\+61\d{9}',               # +61412345678
            r'04\d{8}',                 # 0412345678
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                raw = match.group()
                normalized = re.sub(r'\s', '', raw)
                return normalized, self._redact_phone_display(normalized)
        return None, None

    async def triage(self, voicemail: VoicemailInput) -> TriagedVoicemail:
        """
        Main triage pipeline with full entity extraction and escalation

        Steps:
        1. Generate unique ID
        2. Apply PII redaction
        3. Call AI for triage
        4. Extract entities (phone, Medicare, symptoms)
        5. Smart routing
        6. Emergency escalation (if Level 5)
        7. Construct response
        """

        # Step 1: Generate ID
        voicemail_id = self.generate_voicemail_id()

        # Step 2: PII Redaction
        redacted_transcript, pii_matches, is_pii_safe = pii_filter.redact(
            voicemail.transcript
        )

        # Step 3: AI Triage
        ai_response = await self._call_llm(
            MEDICAL_TRIAGE_SYSTEM_PROMPT,
            f"Analyze this voicemail transcript:\n\n{redacted_transcript}"
        )

        # Step 4: Parse and validate
        triage_data = self._parse_triage_response(ai_response)
        triage_data = self._validate_triage_output(triage_data)

        urgency_level = triage_data["urgency"]["level"]
        intent = triage_data.get("intent", "Other")
        confidence = triage_data["urgency"].get("confidence", 0.85)

        # Step 5: Entity Extraction
        # Extract phone from original transcript
        callback_number, callback_masked = self._extract_phone_from_text(voicemail.transcript)
        if not callback_number and voicemail.caller_phone:
            callback_number = voicemail.caller_phone
            callback_masked = self._redact_phone_display(voicemail.caller_phone)

        # Extract Medicare from original transcript
        medicare_result = smart_routing.extract_medicare(voicemail.transcript)

        # Build extracted entities
        extracted_entities = ExtractedEntities(
            callback_number=callback_number,
            callback_number_raw=callback_masked,
            urgency_keywords=[],
            symptoms=[],
            medication_names=[],
            medicare_number=medicare_result.medicare_number,
            medicare_number_masked=medicare_result.medicare_masked,
            mentioned_doctor=None,
            mentioned_location=None
        )

        # Extract doctor and location mentions
        doctor_name, doctor_location = smart_routing.extract_doctor(voicemail.transcript)
        if doctor_name:
            extracted_entities.mentioned_doctor = doctor_name

        mentioned_loc = smart_routing.extract_location(voicemail.transcript)
        if mentioned_loc:
            extracted_entities.mentioned_location = smart_routing.get_location_name(mentioned_loc)

        # Step 6: Smart Routing
        routing_result = smart_routing.route_voicemail(
            voicemail.transcript,
            medicare_result.medicare_number
        )

        location_info = LocationInfo(
            assigned_location=routing_result.assigned_location,
            location_confidence=routing_result.confidence,
            routing_reason=routing_result.routing_reason,
            available_locations=smart_routing.get_all_locations()
        ) if routing_result.assigned_location else None

        # Patient matching
        patient_match_result = smart_routing.match_patient(medicare_result.medicare_number)
        patient_match = PatientMatchInfo(
            medicare_matched=patient_match_result.matched,
            patient_id=patient_match_result.patient_id,
            match_confidence=patient_match_result.confidence,
            previous_location=patient_match_result.previous_location
        ) if patient_match_result.matched else None

        # Step 7: Emergency Escalation (Level 5)
        escalation_info = None
        if urgency_level >= 5:
            escalation_result = emergency_escalation.process_escalation(
                voicemail_id=voicemail_id,
                urgency_level=urgency_level,
                intent=intent,
                summary=triage_data.get("summary", ""),
                patient_phone=callback_number
            )
            if escalation_result.escalation_triggered:
                escalation_info = EscalationInfo(
                    escalation_triggered=True,
                    emergency_alert_sent=True,
                    intervention_status=escalation_result.intervention_status,
                    timestamp_escalated=escalation_result.timestamp_escalated,
                    emergency_script=escalation_result.emergency_script,
                    sms_sent_to=escalation_result.sms_sent_to,
                    actions_taken=escalation_result.actions_taken
                )

        # Step 8: Build Language Info
        language_info = LanguageInfo(
            detected=triage_data.get("language", "Unknown"),
            code=triage_data.get("language_code", "en"),
            requires_interpreter=triage_data.get("requires_interpreter", False)
        )

        # Step 9: UI State
        is_ambiguous = intent == "Ambiguous" or confidence < 0.5
        ui_state = UIState(
            is_ambiguous=is_ambiguous,
            needs_manual_listening=is_ambiguous,
            highlight_urgent=urgency_level >= 4
        )

        # Step 10: Construct response
        return TriagedVoicemail(
            voicemail_id=voicemail_id,
            language=triage_data.get("language", "Unknown"),
            language_info=language_info,
            urgency=UrgencyInfo(
                level=urgency_level,
                reasoning=triage_data["urgency"]["reasoning"],
                confidence=confidence
            ),
            intent=IntentType(intent),
            summary=triage_data.get("summary", ""),
            action_item=triage_data.get("action_item", ""),
            extracted_entities=extracted_entities,
            location_info=location_info,
            patient_match=patient_match,
            ui_state=ui_state,
            escalation=escalation_info,
            is_pii_safe=is_pii_safe,
            original_transcript=voicemail.transcript,
            redacted_transcript=redacted_transcript,
            caller_phone_redacted=self._redact_phone_display(voicemail.caller_phone),
            created_at=voicemail.call_timestamp or datetime.utcnow(),
            processed_at=datetime.utcnow(),
            status="processed"
        )
    
    def _redact_phone_display(self, phone: Optional[str]) -> Optional[str]:
        """Partially mask phone number for display"""
        if not phone:
            return None
        # Keep last 4 digits
        digits = re.sub(r'\D', '', phone)
        if len(digits) >= 4:
            return "●" * (len(digits) - 4) + digits[-4:]
        return "●" * len(digits)


# Singleton instance
triage_service = TriageService()


async def triage_voicemail(voicemail: VoicemailInput) -> TriagedVoicemail:
    """Convenience function for voicemail triage"""
    return await triage_service.triage(voicemail)
