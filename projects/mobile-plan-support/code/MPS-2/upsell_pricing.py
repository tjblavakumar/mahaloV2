# upsell_pricing.py

import datetime
import uuid
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple

# Configure a basic logger for traceability
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("upsell_pricing")

CYCLE_DAYS = 30  # standard billing cycle in days


@dataclass
class Plan:
    plan_id: str
    name: str
    monthly_price: float  # price per calendar month


@dataclass
class PromoCode:
    code: str
    discount_type: str  # 'percent' or 'flat'
    value: float  # percent as 0-100, or flat amount
    expires_at: Optional[datetime.date]  # None means no expiry
    applies_to_plan_ids: Optional[List[str]] = None  # None means all plans
    stacking_allowed: bool = True  # can this promo stack with others
    # For simplicity, we ignore usage limits in this prototype


@dataclass
class Order:
    order_id: str
    user_id: str
    old_plan: Plan
    new_plan: Plan
    days_remaining: int
    prorated_charge: float
    old_plan_credit: float
    promo_codes_applied: List[str]
    promo_discount_total: float
    total_due: float
    created_at: datetime.datetime
    status: str  # e.g., "PENDING", "COMPLETED"


class UpsellEngine:
    def __init__(self, plans_catalog: Dict[str, Plan], promos_catalog: Dict[str, PromoCode]):
        self.plans_catalog = plans_catalog
        self.promos_catalog = promos_catalog

    def fetch_plan_details(self, plan_id: str) -> Plan:
        if plan_id not in self.plans_catalog:
            raise ValueError(f"Plan '{plan_id}' not found in catalog.")
        plan = self.plans_catalog[plan_id]
        logger.info(f"Fetched plan details: {plan}")
        return plan

    @staticmethod
    def _prorate_charge(price: float, days_remaining: int) -> float:
        # prorate over the remaining days in the billing cycle
        prorated = (price / CYCLE_DAYS) * days_remaining
        logger.debug(f"Prorated charge for price {price} over {days_remaining} days: {prorated}")
        return prorated

    @staticmethod
    def _prorate_credit(price: float, days_remaining: int) -> float:
        # credit the unused portion of the old plan (same days_remaining as prorate period)
        credit = (price / CYCLE_DAYS) * days_remaining
        logger.debug(f"Prorated credit for old price {price} over {days_remaining} days: {credit}")
        return credit

    def _is_promo_active(self, promo: PromoCode, today: datetime.date) -> bool:
        if promo.expires_at is not None and promo.expires_at < today:
            return False
        return True

    def _evaluate_promo_on_amount(self, promo: PromoCode, amount: float, today: datetime.date) -> float:
        if promo.discount_type == 'percent':
            discount = (promo.value / 100.0) * amount
        elif promo.discount_type == 'flat':
            discount = promo.value
        else:
            discount = 0.0
        discount = max(0.0, min(discount, amount))  # cap to amount
        logger.debug(f"Promo {promo.code}: type={promo.discount_type}, value={promo.value}, "
                     f"discount_on_amount={discount}, amount={amount}")
        return discount

    def _apply_promotions(self, amount: float, promo_codes: List[str], old_plan: Plan, today: datetime.date) -> Tuple[float, List[str], float]:
        """
        Apply promos to the given amount. Returns (new_amount, applied_codes, total_discount).
        - non-stacking promos: only one promo can apply (best discount)
        - stacking promos: apply sequentially if stacking_allowed
        """
        if not promo_codes:
            return amount, [], 0.0

        # Gather promos and filter by activity
        applicable = []
        for code in promo_codes:
            promo = self.promos_catalog.get(code)
            if not promo:
                logger.warning(f"Promo code '{code}' not found in catalog.")
                continue
            if not self._is_promo_active(promo, today):
                logger.info(f"Promo '{code}' is not active (expires {promo.expires_at}).")
                continue
            # Check plan applicability
            if promo.applies_to_plan_ids and old_plan.plan_id not in promo.applies_to_plan_ids:
                logger.info(f"Promo '{code}' not applicable to plan {old_plan.plan_id}.")
                continue
            applicable.append(promo)

        if not applicable:
            return amount, [], 0.0

        # Sort promos by potential discount descending
        today_date = today
        # Non-stacking handling
        non_stacking_promos = [p for p in applicable if not p.stacking_allowed]
        stacking_promos = [p for p in applicable if p.stacking_allowed]

        applied_codes: List[str] = []
        total_discount = 0.0

        # If there are any non-stacking promos, apply only the best one
        if non_stacking_promos:
            best = max(non_stacking_promos, key=lambda p: self._evaluate_promo_on_amount(p, amount, today_date))
            discount = self._evaluate_promo_on_amount(best, amount, today_date)
            amount -= discount
            total_discount += discount
            applied_codes.append(best.code)
            logger.info(f"Applied non-stacking promo {best.code} for discount {discount}. New amount: {amount}")
            # Do not apply stacking promos if a non-stacking promo was used
            return max(0.0, amount), applied_codes, total_discount

        # Apply stacking promos sequentially
        for promo in stacking_promos:
            discount = self._evaluate_promo_on_amount(promo, amount, today_date)
            amount -= discount
            total_discount += discount
            applied_codes.append(promo.code)
            logger.info(f"Applied stacking promo {promo.code} for discount {discount}. New amount: {amount}")

        return max(0.0, amount), applied_codes, total_discount

    def generate_upsell_order(
        self,
        user_id: str,
        old_plan_id: str,
        new_plan_id: str,
        days_remaining: int,
        promo_codes: Optional[List[str]] = None,
        as_of: Optional[datetime.date] = None
    ) -> Order:
        """
        Core method to compute prorated upsell pricing and generate an Order object.
        """
        if as_of is None:
            as_of = datetime.date.today()
        today = as_of

        old_plan = self.fetch_plan_details(old_plan_id)
        new_plan = self.fetch_plan_details(new_plan_id)

        # Proration calculations
        prorated_charge = self._prorate_charge(new_plan.monthly_price, days_remaining)
        old_plan_credit = self._prorate_credit(old_plan.monthly_price, days_remaining)

        # Subtotal before promos
        subtotal = prorated_charge - old_plan_credit
        logger.info(
            f"Proration details: days_remaining={days_remaining}, "
            f"new_plan_price={new_plan.monthly_price}, prorated_charge={prorated_charge}, "
            f"old_plan_credit={old_plan_credit}, subtotal_before_promos={subtotal}"
        )

        # Apply promos on the prorated subtotal
        promo_codes_list = promo_codes or []
        amount_after_promos, applied_codes, total_promo_discount = self._apply_promotions(
            subtotal, promo_codes_list, old_plan, today
        )

        # Total due for this upsell action
        total_due = amount_after_promos

        # Build order
        order = Order(
            order_id=str(uuid.uuid4()),
            user_id=user_id,
            old_plan=old_plan,
            new_plan=new_plan,
            days_remaining=days_remaining,
            prorated_charge=round(prorated_charge, 2),
            old_plan_credit=round(old_plan_credit, 2),
            promo_codes_applied=applied_codes,
            promo_discount_total=round(total_promo_discount, 2),
            total_due=round(total_due, 2),
            created_at=datetime.datetime.now(),
            status="PENDING",
        )

        logger.info(f"Generated upsell order: {order}")
        return order


# Example usage / exportable helper for quick runs
def sample_catalogs():
    plans = {
        "basic-plan": Plan(plan_id="basic-plan", name="Basic Plan", monthly_price=25.0),
        "premium-plan": Plan(plan_id="premium-plan", name="Premium Plan", monthly_price=45.0),
        "enterprise-plan": Plan(plan_id="enterprise-plan", name="Enterprise Plan", monthly_price=99.0),
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
            expires_at=(datetime.date.today() + datetime.timedelta(days=7)),
            applies_to_plan_ids=["premium-plan", "enterprise-plan"],
            stacking_allowed=False  # non-stacking
        ),
    }

    return plans, promos


def main_demo():
    plans, promos = sample_catalogs()
    engine = UpsellEngine(plans, promos)

    user_id = "user-123"
    old_plan_id = "basic-plan"
    new_plan_id = "premium-plan"
    days_remaining = 15  # within a 30-day cycle
    promo_codes = ["NEWUSER10", "UPSELL5"]

    order = engine.generate_upsell_order(
        user_id=user_id,
        old_plan_id=old_plan_id,
        new_plan_id=new_plan_id,
        days_remaining=days_remaining,
        promo_codes=promo_codes
    )

    print("Upsell Order Generated:")
    print(f"Order ID: {order.order_id}")
    print(f"User: {order.user_id}")
    print(f"From: {order.old_plan.name} (${order.old_plan.monthly_price}) "
          f"to {order.new_plan.name} (${order.new_plan.monthly_price})")
    print(f"Days remaining: {order.days_remaining}")
    print(f"Prorated charge for new plan: ${order.prorated_charge:.2f}")
    print(f"Credit for old plan unused: ${order.old_plan_credit:.2f}")
    print(f"Applied promos: {order.promo_codes_applied}")
    print(f"Total promo discount: ${order.promo_discount_total:.2f}")
    print(f"Total due: ${order.total_due:.2f}")
    print(f"Status: {order.status}")


if __name__ == "__main__":
    main_demo()
