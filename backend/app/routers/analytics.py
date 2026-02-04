"""
Heidi Calls: Analytics API Router
Dashboard metrics and reporting endpoints
"""

from fastapi import APIRouter
from collections import Counter
from datetime import datetime, timedelta

from app.models.schemas import AnalyticsSummary
from app.routers.voicemail import voicemail_store

router = APIRouter()


@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary():
    """
    Get dashboard analytics summary
    
    Returns aggregate metrics for the voicemail dashboard.
    """
    voicemails = list(voicemail_store.values())
    
    if not voicemails:
        return AnalyticsSummary(
            total_voicemails=0,
            pending_count=0,
            processed_today=0,
            urgency_distribution={},
            intent_distribution={},
            avg_processing_time_ms=0.0,
            language_distribution={}
        )
    
    # Count pending
    pending_count = sum(1 for v in voicemails if v.status == "pending")
    
    # Processed today
    today = datetime.utcnow().date()
    processed_today = sum(
        1 for v in voicemails 
        if v.processed_at and v.processed_at.date() == today
    )
    
    # Urgency distribution
    urgency_counts = Counter(v.urgency.level for v in voicemails)
    urgency_distribution = {
        "critical": urgency_counts.get(5, 0),
        "high": urgency_counts.get(4, 0),
        "standard": urgency_counts.get(3, 0),
        "moderate": urgency_counts.get(2, 0),
        "low": urgency_counts.get(1, 0)
    }
    
    # Intent distribution
    intent_counts = Counter(v.intent.value for v in voicemails)
    intent_distribution = dict(intent_counts)
    
    # Language distribution
    language_counts = Counter(v.language for v in voicemails)
    language_distribution = dict(language_counts)
    
    # Average processing time (mock for demo)
    avg_processing_time_ms = 450.0  # Simulated average
    
    return AnalyticsSummary(
        total_voicemails=len(voicemails),
        pending_count=pending_count,
        processed_today=processed_today,
        urgency_distribution=urgency_distribution,
        intent_distribution=intent_distribution,
        avg_processing_time_ms=avg_processing_time_ms,
        language_distribution=language_distribution
    )


@router.get("/urgency-timeline")
async def get_urgency_timeline():
    """
    Get urgency trend data for charting
    
    Returns hourly breakdown of voicemail urgency levels.
    """
    voicemails = list(voicemail_store.values())
    
    # Group by hour for the last 24 hours
    now = datetime.utcnow()
    timeline = []
    
    for hours_ago in range(24, -1, -1):
        hour_start = now - timedelta(hours=hours_ago)
        hour_end = hour_start + timedelta(hours=1)
        
        hour_voicemails = [
            v for v in voicemails
            if v.created_at and hour_start <= v.created_at < hour_end
        ]
        
        timeline.append({
            "hour": hour_start.strftime("%H:%M"),
            "critical": sum(1 for v in hour_voicemails if v.urgency.level == 5),
            "high": sum(1 for v in hour_voicemails if v.urgency.level == 4),
            "standard": sum(1 for v in hour_voicemails if v.urgency.level == 3),
            "moderate": sum(1 for v in hour_voicemails if v.urgency.level == 2),
            "low": sum(1 for v in hour_voicemails if v.urgency.level == 1),
            "total": len(hour_voicemails)
        })
    
    return {"timeline": timeline}


@router.get("/staff-metrics")
async def get_staff_metrics():
    """
    Get staff workload and performance metrics
    """
    voicemails = list(voicemail_store.values())
    
    # Group by assigned staff
    staff_metrics = {}
    unassigned_count = 0
    
    for vm in voicemails:
        if vm.assigned_to:
            if vm.assigned_to not in staff_metrics:
                staff_metrics[vm.assigned_to] = {
                    "total": 0,
                    "actioned": 0,
                    "pending": 0
                }
            staff_metrics[vm.assigned_to]["total"] += 1
            if vm.status == "actioned":
                staff_metrics[vm.assigned_to]["actioned"] += 1
            elif vm.status in ["pending", "processed"]:
                staff_metrics[vm.assigned_to]["pending"] += 1
        else:
            unassigned_count += 1
    
    return {
        "staff_metrics": staff_metrics,
        "unassigned_count": unassigned_count
    }
