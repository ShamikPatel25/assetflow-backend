import os
import json
import urllib.request
import urllib.error
from django.conf import settings
from rest_framework.exceptions import APIException

from apps.requests.models import AssetRequest
from apps.employees.models import Employee
from apps.assets.models import Asset
from apps.allocations.models import AssetAllocation
from apps.incidents.models import Incident
import random


class RiskAssessmentService:
    """Service to gather context and call the LLM for risk assessment."""

    @classmethod
    def assess_request(cls, request_id):
        try:
            asset_request = AssetRequest.objects.select_related(
                "requested_by", "requested_by__department", "category"
            ).get(id=request_id)
        except AssetRequest.DoesNotExist:
            raise APIException("Asset Request not found.")

        employee = asset_request.requested_by
        
        # Gather Employee Context
        active_allocations = AssetAllocation.objects.filter(
            employee=employee, status="ACTIVE", is_deleted=False
        ).select_related("asset")
        
        past_incidents = Incident.objects.filter(
            reported_by=employee, is_deleted=False
        )

        # Build Context String
        context = f"Action: Approve Asset Request\n"
        context += f"Employee: {employee.get_full_name()} (Designation: {employee.designation}, Dept: {employee.department.name if employee.department else 'N/A'})\n"
        context += f"Requested Category: {asset_request.category.name if asset_request.category else 'General'}\n"
        context += f"Reason Given: {asset_request.reason}\n\n"
        
        context += f"Employee's Currently Active Assets ({active_allocations.count()}):\n"
        for alloc in active_allocations:
            context += f"- {alloc.asset.name} (Value: {alloc.asset.purchase_cost})\n"
            
        context += f"\nEmployee's Incident History ({past_incidents.count()} total incidents):\n"
        for inc in past_incidents:
            context += f"- {inc.title} (Status: {inc.status}, Priority: {inc.priority})\n"

        return cls._call_llm(context)

    @classmethod
    def assess_allocation(cls, employee_id, asset_id):
        try:
            employee = Employee.objects.select_related("department").get(id=employee_id)
            asset = Asset.objects.get(id=asset_id)
        except (Employee.DoesNotExist, Asset.DoesNotExist):
            raise APIException("Employee or Asset not found.")

        # Gather Context
        active_allocations = AssetAllocation.objects.filter(
            employee=employee, status="ACTIVE", is_deleted=False
        ).select_related("asset")
        
        past_incidents = Incident.objects.filter(
            reported_by=employee, is_deleted=False
        )
        
        asset_past_incidents = Incident.objects.filter(
            asset=asset, is_deleted=False
        )

        context = f"Action: Manually Allocate Asset to Employee\n"
        context += f"Target Employee: {employee.get_full_name()} (Designation: {employee.designation})\n"
        context += f"Target Asset: {asset.name} (Value: {asset.purchase_cost}, Condition: {asset.condition})\n\n"
        
        context += f"Employee's Currently Active Assets ({active_allocations.count()}):\n"
        for alloc in active_allocations:
            context += f"- {alloc.asset.name}\n"
            
        context += f"\nEmployee's Incident History ({past_incidents.count()}):\n"
        context += f"Asset's Repair/Incident History ({asset_past_incidents.count()}):\n"

        return cls._call_llm(context)

    @classmethod
    def _call_llm(cls, context_string):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            # Fallback to mock for testing if no key is provided
            return cls._mock_llm(context_string)
            
        api_key = api_key.strip().strip("'").strip('"')

        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"

        headers = {
            "Content-Type": "application/json"
        }

        system_prompt = (
            "You are an AI Risk Assessment engine for an Enterprise Asset Management System. "
            "You will be given the context of an action that an HR Manager is about to take. "
            "Analyze the employee's history, their current assets, and what they are requesting, "
            "and determine the financial/operational risk of approving this action.\n\n"
            "You MUST output raw JSON exactly in this format:\n"
            "{\n"
            '  "risk_score": <int 0-100 (0 is safe, 100 is highly dangerous)>,\n'
            '  "risk_level": <string "LOW", "MEDIUM", or "HIGH">,\n'
            '  "recommendation": <string "APPROVE", "REVIEW", or "DENY">,\n'
            '  "reasoning": <string explaining the logic concisely in 2-3 sentences>\n'
            "}"
        )

        payload = {
            "contents": [{
                "parts": [{"text": system_prompt + "\n\n" + context_string}]
            }]
        }

        try:
            req = urllib.request.Request(
                gemini_url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                response_data = json.loads(response.read().decode("utf-8"))
                # Gemini returns the text deep in candidates -> content -> parts
                content = response_data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(content)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            return {
                "risk_score": 50,
                "risk_level": "MEDIUM",
                "recommendation": "REVIEW",
                "reasoning": f"AI API call failed (HTTP {e.code}). Details: {error_body[:200]}"
            }
        except urllib.error.URLError as e:
            # Fallback on network/API failure
            return {
                "risk_score": 50,
                "risk_level": "MEDIUM",
                "recommendation": "REVIEW",
                "reasoning": f"AI API network failure: {str(e)}."
            }

    @classmethod
    def _mock_llm(cls, context_string):
        """Mock response if API key is missing."""
        score = random.randint(10, 90)
        level = "LOW" if score < 40 else "MEDIUM" if score < 75 else "HIGH"
        rec = "APPROVE" if score < 40 else "REVIEW" if score < 75 else "DENY"
        
        return {
            "risk_score": score,
            "risk_level": level,
            "recommendation": rec,
            "reasoning": "This is a mock AI response. Please add GEMINI_API_KEY to your .env file to activate real AI analysis. Context received: " + context_string[:100] + "..."
        }
