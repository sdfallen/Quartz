"""Explainable learning quality derived from evidence, never from model text.

A record's findings have already passed ``validate_finding`` at write and read
time. This module classifies them for reuse *without* trusting the model's own
``confidence_basis`` prose: the tier of a claim comes only from how many
independent host verifications it cites, whether it is reproducible, whether it
is contradicted, and whether a later failed verification invalidated it.

Pure functions over an already-loaded, already-verified knowledge record (the
dict returned by ``InvestigationMemory.lookup``/``context_for_target`` callers
hold). No IO, no grants, no task state, no numeric "confidence percentage".
Observations and hypotheses are kept distinct from verified procedures so a
hypothesis is never handed onward as an answer.
"""
from __future__ import annotations

from copy import deepcopy

# Ordinal tiers, most to least trustworthy. Deliberately not a 0-100 score:
# there is no evidence basis for a fabricated percentage.
TIERS = ('verified_procedure', 'observed', 'hypothesis', 'unverified', 'contradicted')
MAX_FINDINGS = 128


def _independent_live(finding, evidence):
    """Distinct evidence ids that are LIVE host verifications (not duplicates)."""
    ids = set()
    for ref in finding.get('evidence_ids', []):
        item = evidence.get(ref)
        if isinstance(item, dict) and item.get('level') == 'LIVE' and item.get('origin') == 'host-verification':
            ids.add(ref)
    return ids


def finding_quality(finding, evidence):
    """Typed, explainable quality for one finding. Tier is structural only."""
    if not isinstance(finding, dict) or not isinstance(evidence, dict):
        raise ValueError('invalid-finding-input')
    claim_type = finding.get('claim_type')
    refs = finding.get('evidence_ids', []) if isinstance(finding.get('evidence_ids'), list) else []
    counters = finding.get('counter_evidence_ids', []) if isinstance(finding.get('counter_evidence_ids'), list) else []
    live = _independent_live(finding, evidence)
    reproducible = finding.get('reproducible') is True
    basis = {
        'independent_live_verifications': len(live),
        'source_evidence': sum(1 for r in set(refs) if isinstance(evidence.get(r), dict)
                               and evidence[r].get('level') == 'SOURCE'),
        'counter_evidence': len(set(counters)),
        'reproducible': reproducible,
    }
    blocked_by = []
    if counters:
        tier = 'contradicted'
        blocked_by.append('has_counter_evidence')
    elif claim_type == 'verified_procedure':
        if len(live) >= 2 and reproducible:
            tier = 'verified_procedure'
        else:
            tier = 'unverified'
            if len(live) < 2: blocked_by.append('needs_two_independent_live_verifications')
            if not reproducible: blocked_by.append('not_marked_reproducible')
    elif claim_type == 'observation':
        tier = 'observed'
    elif claim_type == 'hypothesis':
        tier = 'hypothesis'
        blocked_by.append('hypothesis_not_verified')
    else:
        tier = 'unverified'
        blocked_by.append('unknown_claim_type')
    return {
        'claim_id': finding.get('claim_id'),
        'claim_type': claim_type,
        'tier': tier,
        'basis': basis,
        'blocked_by': blocked_by,
        # Recorded for display, never used to decide the tier.
        'stated_basis': finding.get('confidence_basis') if isinstance(finding.get('confidence_basis'), str) else None,
        'instruction_authority': False,
    }


def assess_record(record):
    """Bounded explainable quality roll-up for a whole knowledge record.

    Reflects invalidation the memory layer already applied: a claim dropped by a
    later failed verification is not in ``record['findings']`` and so cannot be
    reported as reusable. ``invalidated_claim_ids`` is surfaced for transparency.
    """
    if not isinstance(record, dict):
        raise ValueError('invalid-record')
    evidence = record.get('evidence') if isinstance(record.get('evidence'), dict) else {}
    findings = record.get('findings') if isinstance(record.get('findings'), list) else []
    qualities = [finding_quality(f, evidence) for f in findings[:MAX_FINDINGS] if isinstance(f, dict)]
    counts = {tier: 0 for tier in TIERS}
    for q in qualities:
        counts[q['tier']] = counts.get(q['tier'], 0) + 1
    return {
        'schema_version': 1,
        'target_sha256': record.get('target_sha256'),
        'tier_counts': counts,
        'findings': qualities,
        'invalidated_claim_ids': list(record.get('invalidated_claim_ids', []))[:MAX_FINDINGS],
        # Reusable only if at least one structurally verified procedure survived.
        'has_reusable_procedure': counts['verified_procedure'] > 0,
        'historical': True,
        'requires_current_grant': True,
        'instruction_authority': False,
    }


def separate_by_type(record, *, maximum_per_type=24):
    """Bounded retrieval that keeps claim types apart.

    A ``hypothesis`` is returned tagged as such so a caller presents it as an
    open question, never as a confirmed answer. ``verified_procedure`` entries
    are included only when they still classify as verified here, independent of
    what the record labels them.
    """
    if not isinstance(record, dict):
        raise ValueError('invalid-record')
    evidence = record.get('evidence') if isinstance(record.get('evidence'), dict) else {}
    buckets = {'verified_procedures': [], 'observations': [], 'hypotheses': []}
    for finding in (record.get('findings') or [])[:MAX_FINDINGS]:
        if not isinstance(finding, dict):
            continue
        quality = finding_quality(finding, evidence)
        entry = deepcopy({k: finding.get(k) for k in ('claim_id', 'claim', 'claim_type', 'limitations')})
        entry['quality'] = {k: quality[k] for k in ('tier', 'basis', 'blocked_by')}
        entry['instruction_authority'] = False
        entry['requires_current_grant'] = True
        if quality['tier'] == 'verified_procedure' and len(buckets['verified_procedures']) < maximum_per_type:
            buckets['verified_procedures'].append(entry)
        elif finding.get('claim_type') == 'observation' and quality['tier'] == 'observed' \
                and len(buckets['observations']) < maximum_per_type:
            buckets['observations'].append(entry)
        elif finding.get('claim_type') == 'hypothesis' and len(buckets['hypotheses']) < maximum_per_type:
            buckets['hypotheses'].append(entry)
    return buckets
