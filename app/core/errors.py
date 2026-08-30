from fastapi import HTTPException, status

from app.monetization.gate import AccessDecision


def raise_access_blocked(decision: AccessDecision) -> None:
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "reason": decision.reason,
            "should_offer_ad": decision.should_offer_ad,
            "should_show_paywall": decision.should_show_paywall,
        },
    )
