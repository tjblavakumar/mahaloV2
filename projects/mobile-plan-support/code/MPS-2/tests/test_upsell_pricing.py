# tests/test_upsell_pricing.py

import datetime
import unittest

from upsell_pricing import Plan, PromoCode, UpsellEngine, CYCLE_DAYS

def build_sample_catalog():
    plans = {
        "basic-plan": Plan(plan_id="basic-plan", name="Basic Plan", monthly_price=25.0),
        "premium-plan": Plan(plan_id="premium-plan", name="Premium Plan", monthly_price=45.0),
    }
    promos = {
        "NEWUSER10": PromoCode(
            code="NEWUSER10",
            discount_type="percent",
            value=10.0,
            expires_at=None,
            applies_to_plan_ids=None,
            stacking_allowed=True
        ),
        "UPSELL5": PromoCode(
            code="UPSELL5",
            discount_type="flat",
            value=5.0,
            expires_at=None,
            applies_to_plan_ids=None,
            stacking_allowed=True
        ),
        "SPECIAL15": PromoCode(
            code="SPECIAL15",
            discount_type="percent",
            value=15.0,
            expires_at=None,
            applies_to_plan_ids=["premium-plan"],
            stacking_allowed=False
        ),
    }
    return plans, promos


class TestUpsellPricing(unittest.TestCase):
    def test_basic_upsell_proration_with_promos(self):
        plans, promos = build_sample_catalog()
        engine = UpsellEngine(plans, promos)

        order = engine.generate_upsell_order(
            user_id="u-1",
            old_plan_id="basic-plan",
            new_plan_id="premium-plan",
            days_remaining=15,
            promo_codes=["NEWUSER10", "UPSELL5"],
            as_of=datetime.date.today()
        )

        # Expected calculation:
        # Prorated new: 45 * (15/30) = 22.5
        # Credit old: 25 * (15/30) = 12.5
        # Subtotal: 22.5 - 12.5 = 10.0
        # Apply NEWUSER10 (10% of 10) = 1.0
        # Then UPSELL5 ($5) = 4.0
        self.assertAlmostEqual(order.prorated_charge, 22.5, places=2)
        self.assertAlmostEqual(order.old_plan_credit, 12.5, places=2)
        self.assertEqual(order.total_due, round(4.0, 2))
        self.assertEqual(set(order.promo_codes_applied), {"NEWUSER10", "UPSELL5"})

    def test_non_stacking_promo(self):
        plans, promos = build_sample_catalog()
        engine = UpsellEngine(plans, promos)

        # Use a non-stacking promo (SPECIAL15) that targets premium-plan
        order = engine.generate_upsell_order(
            user_id="u-2",
            old_plan_id="basic-plan",
            new_plan_id="premium-plan",
            days_remaining=10,
            promo_codes=["SPECIAL15", "NEWUSER10"],
            as_of=datetime.date.today()
        )

        # Since SPECIAL15 is non-stacking, it should override the other promos
        # Proration: new = 45*(10/30)=15.0; credit_old = 25*(10/30)=8.333...
        # Subtotal = 6.6667
        # SPECIAL15 discount = 15% => 1.0
        # Total due ≈ 5.6667
        self.assertAlmostEqual(order.prorated_charge, 15.0, places=2)
        self.assertAlmostEqual(order.old_plan_credit, 8.333333, places=3)
        self.assertAlmostEqual(order.total_due, round(5.6667, 4), places=4)
        self.assertIn("SPECIAL15", order.promo_codes_applied)


if __name__ == '__main__':
    unittest.main()
