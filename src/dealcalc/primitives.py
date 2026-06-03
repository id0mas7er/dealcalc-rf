"""Shared math primitives for the DealCalc engine.

Conventions (apply to every function in this package):
  * Pure functions: deterministic, no network, no file I/O, no globals.
  * Currency values are plain USD numbers (e.g. ``300000``).
  * Rates and percentages are *percent numbers*, not decimals:
    ``6.5`` means 6.5%, ``70`` means 70%, ``5`` means 5% vacancy.
    Conversion to decimals happens internally.
  * Currency results are rounded to 2 decimals; rates/ratios to 2 decimals.
  * Invalid inputs raise ``ValueError``.
"""

from __future__ import annotations


def monthly_mortgage_payment(
    principal: float, annual_rate_pct: float, term_years: float
) -> float:
    """Fully-amortizing monthly mortgage payment (principal & interest).

    Formula: ``r = annual_rate_pct/100/12; n = term_years*12;
    payment = principal/n if r == 0 else principal*r/(1-(1+r)**-n)``.
    Equivalent to ``-numpy_financial.pmt(r, n, principal)``.

    :param principal: Loan principal in USD.
    :param annual_rate_pct: Annual nominal interest rate as a percent (e.g. ``6.5``).
    :param term_years: Loan term in years.
    :returns: Monthly payment rounded to 2 decimals.
    """
    if principal < 0:
        raise ValueError("principal must be non-negative")
    if annual_rate_pct < 0:
        raise ValueError("annual_rate_pct must be non-negative")
    if term_years <= 0:
        raise ValueError("term_years must be greater than 0")

    r = annual_rate_pct / 100 / 12
    n = term_years * 12
    if r == 0:
        payment = principal / n
    else:
        payment = principal * r / (1 - (1 + r) ** -n)
    return round(payment, 2)


def effective_gross_income(
    gross_income_annual: float,
    other_income_annual: float = 0,
    vacancy_pct: float = 0,
) -> float:
    """Effective gross income (EGI) after vacancy/credit loss.

    Formula: ``(gross_income_annual + other_income_annual) * (1 - vacancy_pct/100)``.

    :param gross_income_annual: Scheduled gross rental income per year, USD.
    :param other_income_annual: Other annual income (laundry, parking, etc.), USD.
    :param vacancy_pct: Vacancy / credit loss as a percent (e.g. ``5``).
    :returns: Effective gross income rounded to 2 decimals.
    """
    if gross_income_annual < 0:
        raise ValueError("gross_income_annual must be non-negative")
    if other_income_annual < 0:
        raise ValueError("other_income_annual must be non-negative")
    if vacancy_pct < 0:
        raise ValueError("vacancy_pct must be non-negative")

    egi = (gross_income_annual + other_income_annual) * (1 - vacancy_pct / 100)
    return round(egi, 2)


def net_operating_income(
    effective_gross_income_annual: float, operating_expenses_annual: float
) -> float:
    """Net operating income (NOI). Debt service is NOT an operating expense.

    Formula: ``effective_gross_income_annual - operating_expenses_annual``.

    :param effective_gross_income_annual: EGI per year, USD.
    :param operating_expenses_annual: Operating expenses per year, USD.
    :returns: NOI rounded to 2 decimals.
    """
    if operating_expenses_annual < 0:
        raise ValueError("operating_expenses_annual must be non-negative")

    return round(effective_gross_income_annual - operating_expenses_annual, 2)


def amortization_summary(
    principal: float, annual_rate_pct: float, term_years: float
) -> dict:
    """Summarize a fully-amortizing loan over its full term.

    Formula: ``monthly_payment`` from :func:`monthly_mortgage_payment`;
    ``total_paid = monthly_payment * term_years * 12``;
    ``total_interest = total_paid - principal``.

    :param principal: Loan principal in USD.
    :param annual_rate_pct: Annual nominal interest rate as a percent.
    :param term_years: Loan term in years.
    :returns: ``{monthly_payment, total_paid, total_interest}``.
    """
    monthly_payment = monthly_mortgage_payment(principal, annual_rate_pct, term_years)
    total_paid = round(monthly_payment * term_years * 12, 2)
    total_interest = round(total_paid - principal, 2)
    return {
        "monthly_payment": monthly_payment,
        "total_paid": total_paid,
        "total_interest": total_interest,
    }
