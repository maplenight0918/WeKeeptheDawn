"""Bounded, reviewed scientific statements tied to exact original-text hashes.

This is not an automated verifier of arbitrary LLM prose. Changes to source text
invalidate the review rather than inheriting a trusted label by document ID.
"""
import hashlib

REVIEWED = {
    'bvad_2022-p72-0-72b803e99f': {
        'hash': '72b803e99ffca43c4ad25627233480c2576a1a83677c2c93847fd1ee1b59958a',
        'claims': [
            'BVAD Rev2 Table 3-31 lists nominal food energy 12.778 MJ/CM-d, potable water 3.217 kg/CM-d, and oxygen consumption 0.895 kg/CM-d.',
            'The nominal reference is an 82 kg crewmember during IVA, with 30 minutes aerobic and 60 minutes resistance exercise daily; actual needs vary with workload, diet and metabolism.'
        ]
    },
    'bvad_2022-p73-0-bfe0e18801': {
        'hash': 'bfe0e18801e7e98ab4685ec3521b566f42f78ef9403590e2d67ea70086f0c9f5',
        'claims': [
            'BVAD potable water includes 0.5 kg for food preparation, 2.00 kg drinking water and 0.717 kg associated with the increased exercise profile and mass balance.',
            'BVAD separately describes water already in food before rehydration; potable water is not a measure of all vehicle hygiene water.'
        ]
    }
}

def reviewed_claims(chunk_id, text):
    record=REVIEWED.get(chunk_id)
    if not record or hashlib.sha256(text.encode()).hexdigest()!=record['hash']:
        return []
    return list(record['claims'])
