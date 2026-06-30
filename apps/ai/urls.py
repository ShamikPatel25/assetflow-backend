from django.urls import path
from .views import AIRiskAssessmentView

urlpatterns = [
    path("risk-assessment/", AIRiskAssessmentView.as_view(), name="ai_risk_assessment"),
]
