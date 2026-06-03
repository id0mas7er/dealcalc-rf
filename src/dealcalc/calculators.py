"""Real estate investment calculators for the DealCalc engine.

See :mod:`dealcalc.primitives` for the shared conventions. Every function
here is pure, validates its inputs (raising ``ValueError`` on bad data),
and returns a JSON-serializable ``dict`` ready for an MCP tool. Currency is
rounded to 2 decimals; rates/ratios to 2 decimals. Where a denominator can
be 0, the affected field is returned as ``None`` with an explanatory
``note`` rather than raising.
"""

from __future__ import annotations

from typing import List, Optional

import numpy_financial as npf

from .primitives import (
    effective_gross_income,
    monthly_mortgage_payment,
    net_operating_income,
)


# ---------------------------------------------------------------------------
# Group A — Offer / acquisition logic
# ---------------------------------------------------------------------------


def arv(comp_price_per_sqft: float, subject_sqft: float) -> dict:
    """After-repair value from comparable price per square foot.

    Formula: ``arv = comp_price_per_sqft * subject_sqft``.

    :returns: ``{arv}``.
    """
    if comp_price_per_sqft < 0:
        raise ValueError("comp_price_per_sqft must be non-negative")
    if subject_sqft < 0:
        raise ValueError("subject_sqft must be non-negative")
    return {"arv": round(comp_price_per_sqft * subject_sqft, 2)}


def seventy_percent_rule(arv: float, rehab_cost: float, rule_pct: float = 70) -> dict:
    """Classic 70% rule maximum offer.

    Formula: ``arv*(rule_pct/100) - rehab_cost``.

    :returns: ``{max_allowable_offer}``.
    """
    if arv < 0:
        raise ValueError("arv must be non-negative")
    if rehab_cost < 0:
        raise ValueError("rehab_cost must be non-negative")
    mao_value = arv * (rule_pct / 100) - rehab_cost
    return {"max_allowable_offer": round(mao_value, 2)}


def mao(
    arv: float,
    rehab_cost: float,
    rule_pct: float = 70,
    desired_profit: float = 0,
    holding_costs: float = 0,
    closing_costs: float = 0,
    wholesale_fee: float = 0,
) -> dict:
    """Maximum allowable offer with explicit cost/profit deductions.

    Formula: ``arv*(rule_pct/100) - rehab_cost - desired_profit
    - holding_costs - closing_costs - wholesale_fee``.

    :returns: ``{max_allowable_offer}``.
    """
    if arv < 0:
        raise ValueError("arv must be non-negative")
    for name, value in (
        ("rehab_cost", rehab_cost),
        ("desired_profit", desired_profit),
        ("holding_costs", holding_costs),
        ("closing_costs", closing_costs),
        ("wholesale_fee", wholesale_fee),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
    mao_value = (
        arv * (rule_pct / 100)
        - rehab_cost
        - desired_profit
        - holding_costs
        - closing_costs
        - wholesale_fee
    )
    return {"max_allowable_offer": round(mao_value, 2)}


def wholesale(
    arv: float,
    rehab_cost: float,
    assignment_fee: float,
    buyer_rule_pct: float = 70,
) -> dict:
    """Wholesale offer math: buyer's max, your fee, and seller offer.

    Formula: ``buyer_max = arv*(buyer_rule_pct/100) - rehab_cost;
    max_offer_to_seller = buyer_max - assignment_fee``.

    :returns: ``{buyer_max_offer, assignment_fee, max_offer_to_seller}``.
    """
    if arv < 0:
        raise ValueError("arv must be non-negative")
    if rehab_cost < 0:
        raise ValueError("rehab_cost must be non-negative")
    if assignment_fee < 0:
        raise ValueError("assignment_fee must be non-negative")
    buyer_max = arv * (buyer_rule_pct / 100) - rehab_cost
    max_offer_to_seller = buyer_max - assignment_fee
    return {
        "buyer_max_offer": round(buyer_max, 2),
        "assignment_fee": round(assignment_fee, 2),
        "max_offer_to_seller": round(max_offer_to_seller, 2),
    }


# ---------------------------------------------------------------------------
# Group B — Metric helpers
# ---------------------------------------------------------------------------


def cap_rate(noi_annual: float, property_value: float) -> dict:
    """Capitalization rate.

    Formula: ``noi_annual / property_value * 100``.

    :returns: ``{cap_rate_pct}``; if ``property_value == 0`` returns
        ``{cap_rate_pct: None, note: ...}``.
    """
    if property_value < 0:
        raise ValueError("property_value must be non-negative")
    if property_value == 0:
        return {
            "cap_rate_pct": None,
            "note": "property_value is 0 — cap rate is undefined",
        }
    return {"cap_rate_pct": round(noi_annual / property_value * 100, 2)}


def noi(
    gross_rent_annual: float,
    operating_expenses_annual: float,
    other_income_annual: float = 0,
    vacancy_pct: float = 0,
) -> dict:
    """Net operating income with effective gross income breakout.

    Formula: ``egi = (gross_rent_annual + other_income_annual)*(1 - vacancy_pct/100);
    noi = egi - operating_expenses_annual``.

    :returns: ``{effective_gross_income, noi}``.
    """
    egi = effective_gross_income(
        gross_rent_annual, other_income_annual, vacancy_pct
    )
    noi_value = net_operating_income(egi, operating_expenses_annual)
    return {"effective_gross_income": egi, "noi": noi_value}


def cash_on_cash(annual_pre_tax_cash_flow: float, total_cash_invested: float) -> dict:
    """Cash-on-cash return.

    Formula: ``annual_pre_tax_cash_flow / total_cash_invested * 100``.

    :returns: ``{coc_pct}``; if ``total_cash_invested == 0`` returns
        ``{coc_pct: None, note: ...}``.
    """
    if total_cash_invested < 0:
        raise ValueError("total_cash_invested must be non-negative")
    if total_cash_invested == 0:
        return {
            "coc_pct": None,
            "note": "total_cash_invested is 0 — cash-on-cash is undefined",
        }
    return {"coc_pct": round(annual_pre_tax_cash_flow / total_cash_invested * 100, 2)}


def dscr(noi_annual: float, annual_debt_service: float) -> dict:
    """Debt-service coverage ratio.

    Formula: ``noi_annual / annual_debt_service``.

    :returns: ``{dscr}``; if ``annual_debt_service == 0`` returns
        ``{dscr: None, note: ...}``.
    """
    if annual_debt_service < 0:
        raise ValueError("annual_debt_service must be non-negative")
    if annual_debt_service == 0:
        return {
            "dscr": None,
            "note": "annual_debt_service is 0 — DSCR is undefined",
        }
    return {"dscr": round(noi_annual / annual_debt_service, 2)}


def gross_rent_multiplier(price: float, gross_annual_rent: float) -> dict:
    """Gross rent multiplier.

    Formula: ``price / gross_annual_rent``.

    :returns: ``{grm}``; if ``gross_annual_rent == 0`` returns
        ``{grm: None, note: ...}``.
    """
    if price < 0:
        raise ValueError("price must be non-negative")
    if gross_annual_rent < 0:
        raise ValueError("gross_annual_rent must be non-negative")
    if gross_annual_rent == 0:
        return {"grm": None, "note": "gross_annual_rent is 0 — GRM is undefined"}
    return {"grm": round(price / gross_annual_rent, 2)}


# ---------------------------------------------------------------------------
# Group C — Composite analyzers
# ---------------------------------------------------------------------------


def mortgage(
    loan_amount: float,
    annual_rate_pct: float,
    term_years: float,
    annual_taxes: float = 0,
    annual_insurance: float = 0,
    monthly_hoa: float = 0,
) -> dict:
    """Mortgage payment with PITI and lifetime totals.

    Formula: ``monthly_pi`` from :func:`monthly_mortgage_payment`;
    ``monthly_piti = monthly_pi + annual_taxes/12 + annual_insurance/12 + monthly_hoa``.

    :returns: ``{monthly_pi, monthly_piti, total_interest, total_paid}``.
    """
    if loan_amount < 0:
        raise ValueError("loan_amount must be non-negative")
    for name, value in (
        ("annual_taxes", annual_taxes),
        ("annual_insurance", annual_insurance),
        ("monthly_hoa", monthly_hoa),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")

    monthly_pi = monthly_mortgage_payment(loan_amount, annual_rate_pct, term_years)
    monthly_piti = monthly_pi + annual_taxes / 12 + annual_insurance / 12 + monthly_hoa
    total_paid = round(monthly_pi * term_years * 12, 2)
    total_interest = round(total_paid - loan_amount, 2)
    return {
        "monthly_pi": round(monthly_pi, 2),
        "monthly_piti": round(monthly_piti, 2),
        "total_interest": total_interest,
        "total_paid": total_paid,
    }


def rental_cash_flow(
    monthly_rent: float,
    monthly_operating_expenses: float,
    monthly_debt_service: float,
    vacancy_pct: float = 0,
    other_monthly_income: float = 0,
) -> dict:
    """Monthly and annual cash flow for a rental.

    Formula: ``effective = (monthly_rent + other_monthly_income)*(1 - vacancy_pct/100);
    monthly_cash_flow = effective - monthly_operating_expenses - monthly_debt_service``.

    :returns: ``{effective_monthly_income, monthly_cash_flow, annual_cash_flow}``.
    """
    if monthly_rent < 0:
        raise ValueError("monthly_rent must be non-negative")
    for name, value in (
        ("monthly_operating_expenses", monthly_operating_expenses),
        ("monthly_debt_service", monthly_debt_service),
        ("other_monthly_income", other_monthly_income),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")

    effective = (monthly_rent + other_monthly_income) * (1 - vacancy_pct / 100)
    monthly_cash_flow = effective - monthly_operating_expenses - monthly_debt_service
    return {
        "effective_monthly_income": round(effective, 2),
        "monthly_cash_flow": round(monthly_cash_flow, 2),
        "annual_cash_flow": round(monthly_cash_flow * 12, 2),
    }


def fix_and_flip(
    purchase_price: float,
    rehab_cost: float,
    arv: float,
    holding_costs: float = 0,
    closing_costs_buy: float = 0,
    financing_costs: float = 0,
    selling_costs_pct: float = 8,
    project_months: Optional[float] = None,
) -> dict:
    """Fix-and-flip profitability and ROI.

    Formula: ``total_invested = purchase_price + rehab_cost + holding_costs
    + closing_costs_buy + financing_costs;
    selling_costs = arv*selling_costs_pct/100;
    net_profit = arv - total_invested - selling_costs;
    roi_pct = net_profit/total_invested*100;
    annualized_roi_pct = roi_pct*(12/project_months) if project_months else None``.

    :returns: ``{total_invested, selling_costs, net_profit, roi_pct,
        annualized_roi_pct}``.
    """
    if purchase_price < 0:
        raise ValueError("purchase_price must be non-negative")
    if arv < 0:
        raise ValueError("arv must be non-negative")
    for name, value in (
        ("rehab_cost", rehab_cost),
        ("holding_costs", holding_costs),
        ("closing_costs_buy", closing_costs_buy),
        ("financing_costs", financing_costs),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
    if project_months is not None and project_months <= 0:
        raise ValueError("project_months must be greater than 0")

    total_invested = (
        purchase_price + rehab_cost + holding_costs + closing_costs_buy + financing_costs
    )
    selling_costs = arv * selling_costs_pct / 100
    net_profit = arv - total_invested - selling_costs
    if total_invested == 0:
        return {
            "total_invested": 0.0,
            "selling_costs": round(selling_costs, 2),
            "net_profit": round(net_profit, 2),
            "roi_pct": None,
            "annualized_roi_pct": None,
            "note": "total_invested is 0 — ROI is undefined",
        }
    roi_pct = net_profit / total_invested * 100
    annualized_roi_pct = (
        round(roi_pct * (12 / project_months), 2) if project_months else None
    )
    return {
        "total_invested": round(total_invested, 2),
        "selling_costs": round(selling_costs, 2),
        "net_profit": round(net_profit, 2),
        "roi_pct": round(roi_pct, 2),
        "annualized_roi_pct": annualized_roi_pct,
    }


def brrrr(
    purchase_price: float,
    rehab_cost: float,
    arv: float,
    refinance_ltv_pct: float,
    loan_rate_pct: float,
    loan_term_years: float,
    monthly_rent: float,
    monthly_operating_expenses: float,
    vacancy_pct: float = 0,
    closing_costs: float = 0,
    holding_costs: float = 0,
) -> dict:
    """Buy, Rehab, Rent, Refinance, Repeat (BRRRR) analysis.

    Formula: ``total_cash_invested = purchase_price + rehab_cost + closing_costs
    + holding_costs;
    refinance_loan_amount = arv*refinance_ltv_pct/100;
    cash_left_in_deal = max(total_cash_invested - refinance_loan_amount, 0);
    new_monthly_payment = monthly_mortgage_payment(refinance_loan_amount,
    loan_rate_pct, loan_term_years);
    effective_rent = monthly_rent*(1 - vacancy_pct/100);
    monthly_cash_flow = effective_rent - monthly_operating_expenses - new_monthly_payment;
    post_refi_coc_pct = (monthly_cash_flow*12)/cash_left_in_deal*100
    if cash_left_in_deal > 0 else None``.

    :returns: ``{total_cash_invested, refinance_loan_amount, cash_left_in_deal,
        new_monthly_payment, monthly_cash_flow, post_refi_coc_pct}``.
    """
    if purchase_price < 0:
        raise ValueError("purchase_price must be non-negative")
    if arv < 0:
        raise ValueError("arv must be non-negative")
    for name, value in (
        ("rehab_cost", rehab_cost),
        ("monthly_rent", monthly_rent),
        ("monthly_operating_expenses", monthly_operating_expenses),
        ("closing_costs", closing_costs),
        ("holding_costs", holding_costs),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")

    total_cash_invested = purchase_price + rehab_cost + closing_costs + holding_costs
    refinance_loan_amount = arv * refinance_ltv_pct / 100
    cash_left_in_deal = max(total_cash_invested - refinance_loan_amount, 0)
    new_monthly_payment = monthly_mortgage_payment(
        refinance_loan_amount, loan_rate_pct, loan_term_years
    )
    effective_rent = monthly_rent * (1 - vacancy_pct / 100)
    monthly_cash_flow = (
        effective_rent - monthly_operating_expenses - new_monthly_payment
    )

    result = {
        "total_cash_invested": round(total_cash_invested, 2),
        "refinance_loan_amount": round(refinance_loan_amount, 2),
        "cash_left_in_deal": round(cash_left_in_deal, 2),
        "new_monthly_payment": round(new_monthly_payment, 2),
        "monthly_cash_flow": round(monthly_cash_flow, 2),
    }
    if cash_left_in_deal > 0:
        result["post_refi_coc_pct"] = round(
            (monthly_cash_flow * 12) / cash_left_in_deal * 100, 2
        )
    else:
        result["post_refi_coc_pct"] = None
        result["note"] = "all capital recovered — infinite/undefined CoC"
    return result


def rental_property_analysis(
    purchase_price: float,
    down_payment_pct: float,
    annual_rate_pct: float,
    term_years: float,
    monthly_rent: float,
    monthly_operating_expenses: float,
    vacancy_pct: float = 0,
    closing_costs: float = 0,
    other_monthly_income: float = 0,
) -> dict:
    """Flagship rental aggregate: financing, cash flow, and key metrics.

    Formula: ``down = purchase_price*down_payment_pct/100;
    loan = purchase_price - down; total_cash = down + closing_costs;
    payment = monthly_mortgage_payment(loan, annual_rate_pct, term_years);
    effective = (monthly_rent + other_monthly_income)*(1 - vacancy_pct/100);
    monthly_cash_flow = effective - monthly_operating_expenses - payment;
    annual_cash_flow = monthly_cash_flow*12;
    noi_annual = effective*12 - monthly_operating_expenses*12;
    cap_rate_pct = noi_annual/purchase_price*100;
    cash_on_cash_pct = annual_cash_flow/total_cash*100;
    dscr = noi_annual/(payment*12); grm = purchase_price/((monthly_rent+other)*12)``.

    :returns: ``{loan_amount, total_cash_invested, monthly_payment,
        effective_monthly_income, monthly_cash_flow, annual_cash_flow,
        noi_annual, cap_rate_pct, cash_on_cash_pct, dscr, grm}``.
    """
    if purchase_price <= 0:
        raise ValueError("purchase_price must be greater than 0")
    for name, value in (
        ("monthly_rent", monthly_rent),
        ("monthly_operating_expenses", monthly_operating_expenses),
        ("closing_costs", closing_costs),
        ("other_monthly_income", other_monthly_income),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")

    down = purchase_price * down_payment_pct / 100
    loan = purchase_price - down
    total_cash = down + closing_costs
    payment = monthly_mortgage_payment(loan, annual_rate_pct, term_years)
    effective = (monthly_rent + other_monthly_income) * (1 - vacancy_pct / 100)
    monthly_cash_flow = effective - monthly_operating_expenses - payment
    annual_cash_flow = monthly_cash_flow * 12
    noi_annual = effective * 12 - monthly_operating_expenses * 12

    cap_rate_pct = noi_annual / purchase_price * 100
    cash_on_cash_pct = (
        round(annual_cash_flow / total_cash * 100, 2) if total_cash > 0 else None
    )
    annual_debt_service = payment * 12
    dscr_value = (
        round(noi_annual / annual_debt_service, 2)
        if annual_debt_service > 0
        else None
    )
    gross_annual = (monthly_rent + other_monthly_income) * 12
    grm = round(purchase_price / gross_annual, 2) if gross_annual > 0 else None

    return {
        "loan_amount": round(loan, 2),
        "total_cash_invested": round(total_cash, 2),
        "monthly_payment": round(payment, 2),
        "effective_monthly_income": round(effective, 2),
        "monthly_cash_flow": round(monthly_cash_flow, 2),
        "annual_cash_flow": round(annual_cash_flow, 2),
        "noi_annual": round(noi_annual, 2),
        "cap_rate_pct": round(cap_rate_pct, 2),
        "cash_on_cash_pct": cash_on_cash_pct,
        "dscr": dscr_value,
        "grm": grm,
    }


def multifamily_analysis(
    num_units: int,
    avg_monthly_rent: float,
    annual_operating_expenses: float,
    purchase_price: float,
    vacancy_pct: float = 0,
    market_cap_rate_pct: Optional[float] = None,
) -> dict:
    """Multifamily underwriting: GPR, EGI, NOI, cap rate, and valuation.

    Formula: ``gross_potential_rent = num_units*avg_monthly_rent*12;
    egi = gpr*(1 - vacancy_pct/100); noi = egi - annual_operating_expenses;
    cap_rate_pct = noi/purchase_price*100; price_per_unit = purchase_price/num_units;
    value_by_market_cap = noi/(market_cap_rate_pct/100) if market_cap_rate_pct else None``.

    :returns: ``{gross_potential_rent, effective_gross_income, noi_annual,
        cap_rate_pct, price_per_unit, value_by_market_cap}``.
    """
    if num_units <= 0:
        raise ValueError("num_units must be greater than 0")
    if avg_monthly_rent < 0:
        raise ValueError("avg_monthly_rent must be non-negative")
    if annual_operating_expenses < 0:
        raise ValueError("annual_operating_expenses must be non-negative")
    if purchase_price <= 0:
        raise ValueError("purchase_price must be greater than 0")

    gross_potential_rent = num_units * avg_monthly_rent * 12
    egi = gross_potential_rent * (1 - vacancy_pct / 100)
    noi_value = egi - annual_operating_expenses
    cap_rate_pct = noi_value / purchase_price * 100
    price_per_unit = purchase_price / num_units
    value_by_market_cap = (
        round(noi_value / (market_cap_rate_pct / 100), 2)
        if market_cap_rate_pct
        else None
    )
    return {
        "gross_potential_rent": round(gross_potential_rent, 2),
        "effective_gross_income": round(egi, 2),
        "noi_annual": round(noi_value, 2),
        "cap_rate_pct": round(cap_rate_pct, 2),
        "price_per_unit": round(price_per_unit, 2),
        "value_by_market_cap": value_by_market_cap,
    }


def irr(cash_flows: List[float]) -> dict:
    """Internal rate of return for a series of periodic cash flows.

    ``cash_flows`` is a list whose period 0 is the (negative) initial
    investment; subsequent entries are net cash flows, and the final entry
    typically includes sale proceeds.
    Formula: ``irr_pct = numpy_financial.irr(cash_flows)*100``.

    :returns: ``{irr_pct}``; if no real solution exists returns
        ``{irr_pct: None, note: ...}``.
    """
    if len(cash_flows) < 2:
        raise ValueError("cash_flows must contain at least two periods")

    rate = npf.irr(cash_flows)
    if rate is None or rate != rate:  # NaN check
        return {
            "irr_pct": None,
            "note": "no real IRR solution for the given cash flows",
        }
    return {"irr_pct": round(float(rate) * 100, 2)}


def build_cash_flows(
    initial_investment: float,
    annual_cash_flows: List[float],
    sale_proceeds: float = 0,
) -> List[float]:
    """Assemble an IRR cash-flow series.

    Period 0 is ``-abs(initial_investment)``; the remaining periods are
    ``annual_cash_flows`` with ``sale_proceeds`` added to the final period.

    :returns: A list of cash flows suitable for :func:`irr`.
    """
    if not annual_cash_flows:
        raise ValueError("annual_cash_flows must contain at least one period")

    series = [-abs(initial_investment)] + list(annual_cash_flows)
    series[-1] += sale_proceeds
    return series


# ---------------------------------------------------------------------------
# Group D — Cost estimators
# ---------------------------------------------------------------------------


def closing_costs(
    title_fees: float = 0,
    lender_fees: float = 0,
    points_pct: float = 0,
    loan_amount: float = 0,
    prepaids: float = 0,
    other: float = 0,
) -> dict:
    """Estimate buyer closing costs including discount/origination points.

    Formula: ``points_cost = loan_amount*points_pct/100;
    total = title_fees + lender_fees + points_cost + prepaids + other``.

    :returns: ``{points_cost, total_closing_costs, breakdown}``.
    """
    for name, value in (
        ("title_fees", title_fees),
        ("lender_fees", lender_fees),
        ("points_pct", points_pct),
        ("loan_amount", loan_amount),
        ("prepaids", prepaids),
        ("other", other),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")

    points_cost = round(loan_amount * points_pct / 100, 2)
    total = round(title_fees + lender_fees + points_cost + prepaids + other, 2)
    breakdown = {
        "title_fees": round(title_fees, 2),
        "lender_fees": round(lender_fees, 2),
        "points_cost": points_cost,
        "prepaids": round(prepaids, 2),
        "other": round(other, 2),
    }
    return {
        "points_cost": points_cost,
        "total_closing_costs": total,
        "breakdown": breakdown,
    }


def construction_cost(
    square_feet: float, cost_per_sqft: float, contingency_pct: float = 0
) -> dict:
    """Construction/rehab budget with a contingency allowance.

    Formula: ``base = square_feet*cost_per_sqft;
    contingency = base*contingency_pct/100; total = base + contingency``.

    :returns: ``{base_cost, contingency, total_cost}``.
    """
    if square_feet < 0:
        raise ValueError("square_feet must be non-negative")
    if cost_per_sqft < 0:
        raise ValueError("cost_per_sqft must be non-negative")
    if contingency_pct < 0:
        raise ValueError("contingency_pct must be non-negative")

    base = square_feet * cost_per_sqft
    contingency = base * contingency_pct / 100
    total = base + contingency
    return {
        "base_cost": round(base, 2),
        "contingency": round(contingency, 2),
        "total_cost": round(total, 2),
    }
