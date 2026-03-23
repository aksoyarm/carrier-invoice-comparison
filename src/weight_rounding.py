from src.utils import normalize_country, round_up

HICCUP_EMAIL = "ops@hiccup.com"


def apply_rounding(
    carrier: str,
    weight_kg: float,
    service: str | None = None,
    destination: str | None = None,
    customer_email: str | None = None,
) -> float:
    """Apply carrier-specific weight rounding. Weight must already be in kg."""
    if weight_kg is None:
        return None

    dispatch = {
        "UPS": lambda: _round_ups(weight_kg, service),
        "FedEx": lambda: _round_fedex(weight_kg),
        "THY": lambda: _round_thy(weight_kg, destination, customer_email),
        "PTT": lambda: _round_ptt(weight_kg),
        "Aramex": lambda: _round_aramex(weight_kg),
    }

    fn = dispatch.get(carrier)
    if fn is None:
        raise ValueError(f"Unknown carrier for rounding: {carrier}")
    return fn()


def _round_ups(weight_kg: float, service: str | None) -> float:
    """UPS rounding. Skip rounding if service is unknown."""
    if service is None:
        return weight_kg

    svc = service.strip().lower()
    if "expedited" in svc:
        return round_up(weight_kg, 1.0)
    elif "express" in svc:
        if weight_kg < 10:
            return round_up(weight_kg, 0.5)
        else:
            return round_up(weight_kg, 1.0)
    else:
        # Unrecognized service — skip rounding
        return weight_kg


def _round_fedex(weight_kg: float) -> float:
    if weight_kg < 71:
        return round_up(weight_kg, 0.5)
    else:
        return round_up(weight_kg, 1.0)


def _round_thy(weight_kg: float, destination: str | None, customer_email: str | None) -> float:
    """THY rounding with priority-ordered rules. First match wins."""
    dest = normalize_country(destination) if destination else ""
    email = customer_email.strip().lower() if customer_email else ""
    is_hiccup = email == HICCUP_EMAIL

    # Priority 1: GB + hiccup
    if dest == "GB" and is_hiccup:
        if weight_kg < 5:
            return round_up(weight_kg, 0.5)
        else:
            return round_up(weight_kg, 1.0)

    # Priority 2: US + hiccup
    if dest == "US" and is_hiccup:
        if weight_kg < 2.5:
            return round_up(weight_kg, 0.5)
        else:
            return round_up(weight_kg, 1.0)

    # Priority 3: AU or US (non-hiccup)
    if dest in ("AU", "US") and not is_hiccup:
        if weight_kg < 0.5:
            return round_up(weight_kg, 0.1)
        elif weight_kg <= 3:
            return round_up(weight_kg, 0.5)
        else:
            return round_up(weight_kg, 1.0)

    # Priority 4: catch-all
    if weight_kg < 10:
        return round_up(weight_kg, 0.5)
    else:
        return round_up(weight_kg, 1.0)


def _round_ptt(weight_kg: float) -> float:
    """PTT rounding. Weight should already be in kg."""
    if weight_kg < 0.5:
        return round_up(weight_kg, 0.1)
    else:
        return round_up(weight_kg, 0.5)


def _round_aramex(weight_kg: float) -> float:
    if weight_kg < 10:
        return round_up(weight_kg, 0.5)
    else:
        return round_up(weight_kg, 1.0)
