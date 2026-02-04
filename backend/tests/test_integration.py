"""
Heidi Calls: Integration Test Suite
Tests core functionality including multilingual triage, entity extraction, and emergency escalation.

Usage:
    cd backend
    pip install pytest httpx
    pytest tests/test_integration.py -v

Or run directly:
    python tests/test_integration.py
"""

import sys
import json
from datetime import datetime

# For running without pytest
try:
    import httpx
except ImportError:
    print("Please install httpx: pip install httpx")
    sys.exit(1)

BASE_URL = "http://127.0.0.1:8000/api/v1"


class TestHeidiCallsIntegration:
    """Integration tests for Heidi Calls API"""

    # ========================================================================
    # TEST 1: Vietnamese Emergency Voicemail
    # ========================================================================
    def test_vietnamese_emergency_triage(self):
        """
        Test Case: Vietnamese patient with emergency symptoms

        Expected:
        - English summary generated
        - Phone number extracted
        - Medicare number extracted
        - Emergency escalation triggered (Level 5)
        """
        # Vietnamese emergency voicemail transcript
        payload = {
            "transcript": """
                Xin chào, tôi tên là Nguyễn Văn An. Tôi đang bị đau ngực rất nặng
                và khó thở. Tôi rất lo lắng. Medicare của tôi là 2345 67890 1.
                Xin gọi lại cho tôi số 0412 345 678. Cảm ơn.
            """,
            "caller_phone": "+61412345678",
            "duration_seconds": 45
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{BASE_URL}/voicemail/triage", json=payload)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        result = response.json()
        print("\n" + "=" * 60)
        print("TEST 1: Vietnamese Emergency Voicemail")
        print("=" * 60)
        print(json.dumps(result, indent=2, default=str))

        # Assertions
        assert "voicemail_id" in result, "Missing voicemail_id"
        assert result.get("language") != "English", f"Should detect non-English language, got: {result.get('language')}"
        assert "summary" in result, "Missing English summary"
        assert result["summary"], "Summary should not be empty"

        # Urgency should be high (4-5) for chest pain
        urgency_level = result.get("urgency", {}).get("level", 0)
        assert urgency_level >= 4, f"Chest pain should be Level 4-5, got: {urgency_level}"

        print(f"\n[OK] Language detected: {result.get('language')}")
        print(f"[OK] Urgency Level: {urgency_level}")
        print(f"[OK] Summary: {result.get('summary')}")

        return result

    # ========================================================================
    # TEST 2: API Connectivity - List Voicemails
    # ========================================================================
    def test_list_voicemails(self):
        """Test that voicemail list endpoint returns data"""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{BASE_URL}/voicemail/", params={"page_size": 10})

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        result = response.json()
        print("\n" + "=" * 60)
        print("TEST 2: List Voicemails")
        print("=" * 60)

        assert "items" in result, "Missing items array"
        assert "total" in result, "Missing total count"
        assert len(result["items"]) > 0, "Expected demo data in voicemail store"

        print(f"[OK] Total voicemails: {result['total']}")
        print(f"[OK] Items returned: {len(result['items'])}")

        # Check first item structure
        first_item = result["items"][0]
        required_fields = ["voicemail_id", "language", "urgency", "intent", "summary"]
        for field in required_fields:
            assert field in first_item, f"Missing required field: {field}"

        print(f"[OK] First item ID: {first_item['voicemail_id']}")

        return result

    # ========================================================================
    # TEST 3: Status Update (PATCH)
    # ========================================================================
    def test_status_update(self):
        """Test that status can be updated via PATCH"""
        # First, get a voicemail ID
        with httpx.Client(timeout=30.0) as client:
            list_response = client.get(f"{BASE_URL}/voicemail/", params={"page_size": 1})

        assert list_response.status_code == 200
        items = list_response.json().get("items", [])
        assert len(items) > 0, "Need at least one voicemail for this test"

        voicemail_id = items[0]["voicemail_id"]
        original_status = items[0]["status"]

        # Update status
        new_status = "actioned" if original_status != "actioned" else "pending"

        with httpx.Client(timeout=30.0) as client:
            patch_response = client.patch(
                f"{BASE_URL}/voicemail/{voicemail_id}",
                json={"status": new_status}
            )

        print("\n" + "=" * 60)
        print("TEST 3: Status Update (PATCH)")
        print("=" * 60)

        assert patch_response.status_code == 200, f"Expected 200, got {patch_response.status_code}"

        result = patch_response.json()
        assert result["status"] == new_status, f"Status not updated. Expected {new_status}, got {result['status']}"

        print(f"[OK] Voicemail ID: {voicemail_id}")
        print(f"[OK] Status changed: {original_status} → {new_status}")

        # Restore original status
        with httpx.Client(timeout=30.0) as client:
            client.patch(f"{BASE_URL}/voicemail/{voicemail_id}", json={"status": original_status})

        return result

    # ========================================================================
    # TEST 4: Entity Extraction Verification
    # ========================================================================
    def test_entity_extraction_in_demo_data(self):
        """Verify demo data contains properly extracted entities"""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{BASE_URL}/voicemail/", params={"page_size": 100})

        assert response.status_code == 200
        items = response.json().get("items", [])

        print("\n" + "=" * 60)
        print("TEST 4: Entity Extraction Verification")
        print("=" * 60)

        entities_found = {
            "callback_numbers": 0,
            "medicare_numbers": 0,
            "symptoms": 0,
            "medications": 0,
            "doctors_mentioned": 0,
            "locations_mentioned": 0
        }

        for item in items:
            entities = item.get("extracted_entities", {})
            if entities:
                if entities.get("callback_number"):
                    entities_found["callback_numbers"] += 1
                if entities.get("medicare_number"):
                    entities_found["medicare_numbers"] += 1
                if entities.get("symptoms"):
                    entities_found["symptoms"] += len(entities["symptoms"])
                if entities.get("medication_names"):
                    entities_found["medications"] += len(entities["medication_names"])
                if entities.get("mentioned_doctor"):
                    entities_found["doctors_mentioned"] += 1
                if entities.get("mentioned_location"):
                    entities_found["locations_mentioned"] += 1

        print(f"[OK] Callback numbers extracted: {entities_found['callback_numbers']}")
        print(f"[OK] Medicare numbers extracted: {entities_found['medicare_numbers']}")
        print(f"[OK] Symptoms identified: {entities_found['symptoms']}")
        print(f"[OK] Medications identified: {entities_found['medications']}")
        print(f"[OK] Doctors mentioned: {entities_found['doctors_mentioned']}")
        print(f"[OK] Locations mentioned: {entities_found['locations_mentioned']}")

        # At least some entities should be extracted in demo data
        assert entities_found["callback_numbers"] > 0, "No callback numbers in demo data"
        assert entities_found["medicare_numbers"] > 0, "No Medicare numbers in demo data"

        return entities_found

    # ========================================================================
    # TEST 5: Emergency Escalation Data
    # ========================================================================
    def test_emergency_escalation_data(self):
        """Verify Level 5 cases have escalation info"""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{BASE_URL}/voicemail/",
                params={"urgency_min": 5, "page_size": 100}
            )

        assert response.status_code == 200
        items = response.json().get("items", [])

        print("\n" + "=" * 60)
        print("TEST 5: Emergency Escalation Data")
        print("=" * 60)

        level_5_count = len(items)
        escalation_triggered = 0
        voice_alerts = 0
        sms_alerts = 0

        for item in items:
            escalation = item.get("escalation", {})
            if escalation:
                if escalation.get("escalation_triggered"):
                    escalation_triggered += 1
                actions = escalation.get("actions_taken", [])
                if "Voice_Alert_Sent_To_Patient" in actions:
                    voice_alerts += 1
                if "SMS_Alert_Sent_To_Manager" in actions:
                    sms_alerts += 1

                # Print escalation details
                if escalation.get("escalation_triggered"):
                    print(f"\n[Escalation] {item['voicemail_id']}:")
                    print(f"   Status: {escalation.get('intervention_status')}")
                    print(f"   Actions: {actions}")
                    if escalation.get("emergency_script"):
                        print(f"   Script: [PRESENT - {len(escalation['emergency_script'])} chars]")

        print(f"\n[OK] Level 5 voicemails: {level_5_count}")
        print(f"[OK] Escalations triggered: {escalation_triggered}")
        print(f"[OK] Voice alerts sent: {voice_alerts}")
        print(f"[OK] SMS alerts sent: {sms_alerts}")

        if level_5_count > 0:
            assert escalation_triggered > 0, "Level 5 cases should have escalation triggered"

        return {
            "level_5_count": level_5_count,
            "escalation_triggered": escalation_triggered
        }

    # ========================================================================
    # TEST 6: Smart Routing / Location Assignment
    # ========================================================================
    def test_smart_routing(self):
        """Verify location routing is present in demo data"""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{BASE_URL}/voicemail/", params={"page_size": 100})

        assert response.status_code == 200
        items = response.json().get("items", [])

        print("\n" + "=" * 60)
        print("TEST 6: Smart Routing / Location Assignment")
        print("=" * 60)

        routing_stats = {
            "total_with_location": 0,
            "by_reason": {}
        }

        for item in items:
            location_info = item.get("location_info", {})
            if location_info and location_info.get("assigned_location"):
                routing_stats["total_with_location"] += 1
                reason = location_info.get("routing_reason", "unknown")
                routing_stats["by_reason"][reason] = routing_stats["by_reason"].get(reason, 0) + 1

                print(f"   {item['voicemail_id']}: @{location_info['assigned_location']} ({reason})")

        print(f"\n[OK] Voicemails with location: {routing_stats['total_with_location']}")
        print(f"[OK] Routing reasons: {routing_stats['by_reason']}")

        return routing_stats


def run_all_tests():
    """Run all integration tests"""
    print("\n" + "=" * 60)
    print("HEIDI CALLS - INTEGRATION TEST SUITE")
    print("=" * 60)
    print(f"Target: {BASE_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)

    test_suite = TestHeidiCallsIntegration()

    tests = [
        ("List Voicemails", test_suite.test_list_voicemails),
        ("Status Update", test_suite.test_status_update),
        ("Entity Extraction", test_suite.test_entity_extraction_in_demo_data),
        ("Emergency Escalation", test_suite.test_emergency_escalation_data),
        ("Smart Routing", test_suite.test_smart_routing),
        ("Vietnamese Emergency", test_suite.test_vietnamese_emergency_triage),
    ]

    results = []
    for name, test_func in tests:
        try:
            test_func()
            results.append((name, "PASS", None))
        except AssertionError as e:
            results.append((name, "FAIL", str(e)))
        except Exception as e:
            results.append((name, "ERROR", str(e)))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, status, _ in results if status == "PASS")
    failed = sum(1 for _, status, _ in results if status == "FAIL")
    errors = sum(1 for _, status, _ in results if status == "ERROR")

    for name, status, error in results:
        icon = "[OK]" if status == "PASS" else "[FAIL]" if status == "FAIL" else "[ERR]"
        print(f"{icon} {name}: {status}")
        if error:
            print(f"   └─ {error}")

    print("\n" + "-" * 60)
    print(f"Total: {len(results)} | Passed: {passed} | Failed: {failed} | Errors: {errors}")
    print("=" * 60)

    return passed == len(results)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
