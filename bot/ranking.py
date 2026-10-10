"""Which scraped inmates make the nightly queue.

Order: has a charge, then distinctiveness (CLIP, rescaled 0..1 within the batch) plus a
severity bonus (config.SEVERITY_BONUS), then bail dollar amount. If CLIP can't run,
distinctiveness is 0 for everyone and ranking falls back to charge, severity and bail.
"""
import os
import re

from . import config

SEVERITY_ORDER = ['', 'Misdemeanor', 'Gross Misdemeanor', 'Felony']


def classify_severity(text):
    """Map severity text or charge text to Felony / Gross Misdemeanor / Misdemeanor / ''."""
    t = (text or '').upper()
    if 'FELONY' in t:
        return 'Felony'
    if 'GROSS' in t or re.search(r'\bGM\b', t):
        return 'Gross Misdemeanor'
    if 'MISD' in t:
        return 'Misdemeanor'
    return ''


def most_severe(values):
    return max((classify_severity(v) for v in values), key=SEVERITY_ORDER.index, default='')


def _bail_amount(bail):
    match = re.search(r'\$[\d,]+\.?\d*', bail or '')
    return float(match.group()[1:].replace(',', '')) if match else 0


def _has_charge(inmate):
    return inmate.get('Charge 1', 'No charge listed') != 'No charge listed'


def _severity(inmate):
    return most_severe([inmate.get('Severity', ''), inmate.get('Charge 1', '')]) if _has_charge(inmate) else ''


def rank(inmates, n):
    """Top n inmates, best first."""
    raw = {}
    try:
        # torch/transformers are optional: the scrape workflow keeps going if their install fails
        from .clip_model import score_mugshots
        raw = score_mugshots([i['Mugshot_File'] for i in inmates if os.path.exists(i.get('Mugshot_File', ''))])
    except Exception as e:
        print(f"⚠️  Distinctiveness ranking unavailable, using severity + bail only: {e}")

    # Rescale to 0..1 within today's batch so the spread is comparable to the severity bonus
    lo, hi = min(raw.values(), default=0), max(raw.values(), default=0)
    distinct = {p: (v - lo) / (hi - lo) if hi > lo else 0 for p, v in raw.items()}

    def total(inmate):
        return distinct.get(inmate.get('Mugshot_File'), 0) + config.SEVERITY_BONUS[_severity(inmate)]

    ranked = sorted(inmates, key=lambda i: (not _has_charge(i), -total(i), -_bail_amount(i.get('Bail', ''))))
    for i, inmate in enumerate(ranked[:n], 1):
        print(f"🏆 #{i}: {inmate.get('Full Name')} | total {total(inmate):.2f} = "
              f"distinct {distinct.get(inmate.get('Mugshot_File'), 0):.2f} + {_severity(inmate) or 'no severity'}")
    return ranked[:n]
