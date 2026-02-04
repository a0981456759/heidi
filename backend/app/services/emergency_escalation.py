"""
Heidi Calls: Emergency Escalation Module
Handles critical Level 5 voicemails with automated alerts and escalation

Features:
- Automatic escalation for critical cases
- SMS notification to managers (simulated)
- Voice alert script for patients
- Intervention status tracking
"""

from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class EscalationResult:
    """Result of emergency escalation process"""
    escalation_triggered: bool
    intervention_status: str
    timestamp_escalated: Optional[str]
    emergency_script: Optional[str]
    sms_sent_to: Optional[str]
    actions_taken: list


# Emergency script in Traditional Chinese (for Australian medical context)
EMERGENCY_SCRIPT_ZH = """我們偵測到您的症狀可能需要緊急醫療協助。
請立即掛斷電話並撥打 000，或前往最近的急診中心。
診所人員已收到您的通知。"""

EMERGENCY_SCRIPT_EN = """We have detected that your symptoms may require emergency medical attention.
Please hang up immediately and call 000, or proceed to your nearest emergency department.
Clinic staff have been notified of your situation."""

# Emergency script with bilingual content
EMERGENCY_SCRIPT_BILINGUAL = f"""[ENGLISH]
{EMERGENCY_SCRIPT_EN}

[中文]
{EMERGENCY_SCRIPT_ZH}"""


class EmergencyEscalation:
    """
    Emergency Escalation Handler

    Responsible for:
    1. Detecting critical (level 5) voicemails
    2. Triggering automated patient voice alerts
    3. Sending SMS notifications to managers
    4. Tracking intervention status
    """

    def __init__(self):
        self.manager_phone = "+61400000001"  # Simulated manager number
        self.emergency_script = EMERGENCY_SCRIPT_BILINGUAL
        self.escalation_log = []

    def should_escalate(self, urgency_level: int, intent: str = None) -> bool:
        """
        Determine if escalation is required

        Criteria:
        - Level 5 urgency (Critical/Emergency)
        - Or Level 4 with Emergency intent
        """
        if urgency_level >= 5:
            return True
        if urgency_level >= 4 and intent == "Emergency":
            return True
        return False

    def send_sms_to_manager(
        self,
        voicemail_id: str,
        patient_phone: str,
        summary: str,
        urgency_level: int
    ) -> bool:
        """
        Send SMS notification to clinic manager (SIMULATED)

        In production, this would integrate with Twilio, AWS SNS, or similar
        """
        timestamp = datetime.utcnow().isoformat()

        sms_content = f"""
╔══════════════════════════════════════════════╗
║  🚨 HEIDI CALLS - EMERGENCY ALERT 🚨          ║
╠══════════════════════════════════════════════╣
║  Time: {timestamp[:19]}
║  Voicemail ID: {voicemail_id}
║  Patient Phone: {patient_phone}
║  Urgency: LEVEL {urgency_level} - CRITICAL
║
║  Summary:
║  {summary[:60]}...
║
║  ⚡ Automated voice alert sent to patient
║  ⚡ Advising patient to call 000 / go to ED
║
║  ACTION REQUIRED: Verify patient status
╚══════════════════════════════════════════════╝
"""

        # SIMULATED: Print to console (in production, send actual SMS)
        print("\n" + "=" * 50)
        print("📱 SIMULATED SMS TO MANAGER:", self.manager_phone)
        print("=" * 50)
        print(sms_content)
        print("=" * 50 + "\n")

        # Log the escalation
        self.escalation_log.append({
            "type": "sms",
            "recipient": self.manager_phone,
            "voicemail_id": voicemail_id,
            "timestamp": timestamp,
            "status": "sent_simulated"
        })

        return True

    def trigger_voice_alert(self, voicemail_id: str, patient_phone: str) -> bool:
        """
        Trigger automated voice callback to patient (SIMULATED)

        In production, this would use Twilio Voice API or similar
        """
        timestamp = datetime.utcnow().isoformat()

        print("\n" + "=" * 50)
        print("📞 SIMULATED VOICE ALERT TO PATIENT:", patient_phone)
        print("=" * 50)
        print("Script being played:")
        print("-" * 50)
        print(self.emergency_script)
        print("-" * 50)
        print("=" * 50 + "\n")

        # Log the voice alert
        self.escalation_log.append({
            "type": "voice_alert",
            "recipient": patient_phone,
            "voicemail_id": voicemail_id,
            "timestamp": timestamp,
            "status": "sent_simulated"
        })

        return True

    def process_escalation(
        self,
        voicemail_id: str,
        urgency_level: int,
        intent: str,
        summary: str,
        patient_phone: Optional[str] = None
    ) -> EscalationResult:
        """
        Main escalation processing pipeline

        Returns:
            EscalationResult with all escalation details
        """
        actions_taken = []

        # Check if escalation is needed
        if not self.should_escalate(urgency_level, intent):
            return EscalationResult(
                escalation_triggered=False,
                intervention_status="None",
                timestamp_escalated=None,
                emergency_script=None,
                sms_sent_to=None,
                actions_taken=[]
            )

        timestamp = datetime.utcnow().isoformat()

        # Step 1: Send SMS to manager
        sms_sent = self.send_sms_to_manager(
            voicemail_id=voicemail_id,
            patient_phone=patient_phone or "Unknown",
            summary=summary,
            urgency_level=urgency_level
        )
        if sms_sent:
            actions_taken.append("SMS_Alert_Sent_To_Manager")

        # Step 2: Trigger voice alert to patient (if phone available)
        voice_sent = False
        if patient_phone:
            voice_sent = self.trigger_voice_alert(
                voicemail_id=voicemail_id,
                patient_phone=patient_phone
            )
            if voice_sent:
                actions_taken.append("Voice_Alert_Sent_To_Patient")

        # Determine intervention status
        if voice_sent and sms_sent:
            intervention_status = "Voice_Alert_Sent"
        elif sms_sent:
            intervention_status = "SMS_Alert_Only"
        else:
            intervention_status = "Escalation_Failed"

        return EscalationResult(
            escalation_triggered=True,
            intervention_status=intervention_status,
            timestamp_escalated=timestamp,
            emergency_script=self.emergency_script,
            sms_sent_to=self.manager_phone,
            actions_taken=actions_taken
        )

    def get_escalation_log(self) -> list:
        """Get the log of all escalations"""
        return self.escalation_log.copy()


# Singleton instance
emergency_escalation = EmergencyEscalation()
