"""Reset demo data — seeds MahaloPay sample data into a project or legacy DB."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from backend.database import SessionLocal, get_project_db, init_db, init_project_db
from backend.models.jira_models import JiraBug, JiraSprint, JiraStory, JiraUser
from backend.models.servicenow_models import ServiceNowDeployment, ServiceNowIncident
from backend.models.splunk_models import SplunkLog


def reset_demo_data(project_id: Optional[str] = None) -> None:
    """Seed MahaloPay demo data.

    Args:
        project_id: If provided, seeds into that project's database.
                    If None, falls back to the legacy root database (backward compat).
    """
    if project_id:
        init_project_db(project_id)
        gen = get_project_db(project_id)
        db = next(gen)
    else:
        init_db()
        db = SessionLocal()

    try:
        # Clear existing data
        db.query(JiraBug).delete()
        db.query(JiraStory).delete()
        db.query(JiraSprint).delete()
        db.query(JiraUser).delete()
        db.query(ServiceNowIncident).delete()
        db.query(ServiceNowDeployment).delete()
        db.query(SplunkLog).delete()

        users = [
            JiraUser(username="alice_dev", full_name="Alice Developer", email="alice@mahalopay.com", role="developer"),
            JiraUser(username="bob_pm", full_name="Bob Product Manager", email="bob@mahalopay.com", role="product_manager"),
            JiraUser(username="charlie_qa", full_name="Charlie QA", email="charlie@mahalopay.com", role="qa"),
            JiraUser(username="diana_dev", full_name="Diana Developer", email="diana@mahalopay.com", role="developer"),
            JiraUser(username="eve_exec", full_name="Eve Executive", email="eve@mahalopay.com", role="executive"),
        ]
        db.add_all(users)
        db.commit()

        user_map = {u.username: u for u in users}

        story_1 = JiraStory(
            story_key="MPAY-1",
            title="Implement Stripe payment gateway integration",
            description="Add Stripe-powered payment processing to the checkout flow.",
            assignee_id=user_map["alice_dev"].id,
            reporter_id=user_map["bob_pm"].id,
            story_points=8,
            priority="High",
            sprint="Sprint 23",
            status="Done",
        )
        story_2 = JiraStory(
            story_key="MPAY-2",
            title="Add fraud detection for high-value transactions",
            description="Flag risky payments for secondary review.",
            assignee_id=user_map["diana_dev"].id,
            reporter_id=user_map["bob_pm"].id,
            story_points=13,
            priority="Critical",
            sprint="Sprint 23",
            status="In Progress",
        )
        story_3 = JiraStory(
            story_key="MPAY-3",
            title="Build account reconciliation automation",
            description="Automate nightly settlement reconciliation and balances.",
            assignee_id=user_map["alice_dev"].id,
            reporter_id=user_map["bob_pm"].id,
            story_points=5,
            priority="Medium",
            sprint="Sprint 23",
            status="Backlog",
        )
        db.add_all([story_1, story_2, story_3])
        db.commit()

        db.add(JiraSprint(
            sprint_name="Sprint 23",
            goal="Stabilize payment processing and improve reconciliation reliability.",
            velocity=8,
            completed_stories=1,
            total_stories=3,
            status="Active",
        ))
        db.commit()

        bug_1 = JiraBug(
            bug_key="MPAY-BUG-1",
            title="Payment timeout on high-value transactions",
            description="Transactions above $10,000 time out while waiting for gateway confirmation.",
            assignee_id=user_map["alice_dev"].id,
            reporter_id=user_map["charlie_qa"].id,
            severity="Critical",
            status="Open",
            related_story_id=story_1.id,
            servicenow_incident_id="MPAY-INC-001",
        )
        bug_2 = JiraBug(
            bug_key="MPAY-BUG-2",
            title="Balance calculation rounding error",
            description="Ledger balance rounding produces small mismatches in reconciliation.",
            assignee_id=user_map["diana_dev"].id,
            reporter_id=user_map["charlie_qa"].id,
            severity="Medium",
            status="In Progress",
            related_story_id=story_3.id,
        )
        db.add_all([bug_1, bug_2])

        db.add(ServiceNowIncident(
            incident_id="MPAY-INC-001",
            title="Payment service returning 500 errors during peak load",
            description="Payment API returns internal server errors during peak hours.",
            severity="Critical",
            status="Active",
            assigned_group="Platform Reliability",
            created_at=datetime.utcnow(),
        ))

        db.add_all([
            ServiceNowDeployment(
                deployment_id="MPAY-DEP-001",
                feature_name="Stripe payment gateway integration",
                version="v2.4.0",
                environment="production",
                status="Deployed",
                deployed_by="release-engineering",
            ),
            ServiceNowDeployment(
                deployment_id="MPAY-DEP-002",
                feature_name="Fraud detection rules engine",
                version="v1.8.2",
                environment="production",
                status="Deployed",
                deployed_by="platform-release",
            ),
            ServiceNowDeployment(
                deployment_id="MPAY-DEP-003",
                feature_name="Account reconciliation automation",
                version="v3.1.0",
                environment="production",
                status="Deployed",
                deployed_by="finance-platform",
            ),
        ])
        db.add(ServiceNowIncident(
            incident_id="MPAY-INC-002",
            title="Nightly account reconciliation job failed",
            description="Settlement job fails due to missing ledger records.",
            severity="High",
            status="Monitoring",
            assigned_group="Finance Ops",
            created_at=datetime.utcnow(),
        ))

        db.add_all([
            SplunkLog(source="payment-service", level="ERROR", message="Database connection pool exhausted during payment authorization.", service="payment-service"),
            SplunkLog(source="payment-service", level="ERROR", message="Payment gateway timeout after 30 seconds for high-value transaction.", service="payment-service"),
            SplunkLog(source="payment-service", level="WARN", message="Retry queue reached 85 percent capacity after gateway failures.", service="payment-service"),
            SplunkLog(source="fraud-detection", level="WARN", message="High-risk transaction flagged for manual review.", service="fraud-detection"),
            SplunkLog(source="fraud-detection", level="ERROR", message="Fraud scoring service latency exceeded 2 seconds.", service="fraud-detection"),
            SplunkLog(source="account-service", level="ERROR", message="Balance mismatch detected in nightly reconciliation.", service="account-service"),
            SplunkLog(source="transaction-api", level="INFO", message="Transaction processing latency above expected threshold.", service="transaction-api"),
            SplunkLog(source="transaction-api", level="ERROR", message="Downstream payment provider returned intermittent 502 responses.", service="transaction-api"),
        ])

        db.commit()
        print("Demo data reset complete.")
    finally:
        if project_id:
            try:
                next(gen)
            except StopIteration:
                pass
        else:
            db.close()


if __name__ == "__main__":
    reset_demo_data()
