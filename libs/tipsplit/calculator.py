"""
Tip splitting calculation engine with strict integer minor unit arithmetic.
Uses the largest remainder method (Hamilton-Hare) to guarantee zero cent drift.
"""

from typing import List, Dict, Any


class TipSplitError(ValueError):
    """Raised when tip split rules or inputs are invalid."""
    pass


def split_tips(
    total_tip_minor: int,
    rules: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Splits `total_tip_minor` amongst staff members according to their allocated basis points.
    
    Each rule dict must contain:
      - 'staff_id': str
      - 'basis_points': int (out of 10,000, i.e. 50% = 5000 bps)
    
    Returns a list of dicts:
      [{'staff_id': str, 'amount_minor': int, 'basis_points': int}]
      
    Guarantees:
      sum(split['amount_minor']) == total_tip_minor
    """
    if total_tip_minor < 0:
        raise TipSplitError(f"Total tip cannot be negative: {total_tip_minor}")
    
    if not rules:
        if total_tip_minor == 0:
            return []
        raise TipSplitError("Cannot split a non-zero tip with empty rules.")
    
    total_bps = sum(r.get("basis_points", 0) for r in rules)
    if total_bps != 10000:
        raise TipSplitError(
            f"Rule basis points must sum to 10,000 (100.00%). Found: {total_bps}"
        )
    
    if total_tip_minor == 0:
        return [
            {"staff_id": r["staff_id"], "amount_minor": 0, "basis_points": r["basis_points"]}
            for r in rules
        ]

    # Step 1: Compute floor shares and remainders
    allocations = []
    total_allocated = 0

    for idx, rule in enumerate(rules):
        staff_id = rule["staff_id"]
        bps = rule["basis_points"]
        if bps < 0:
            raise TipSplitError(f"Staff basis points cannot be negative: {bps}")
        
        # Exact product in minor-point units
        exact_scaled = total_tip_minor * bps
        base_share = exact_scaled // 10000
        remainder = exact_scaled % 10000

        allocations.append({
            "idx": idx,
            "staff_id": staff_id,
            "basis_points": bps,
            "base_share": base_share,
            "remainder": remainder,
        })
        total_allocated += base_share

    # Step 2: Distribute leftover cents to highest remainders
    unallocated_cents = total_tip_minor - total_allocated

    # Sort descending by remainder, tie-breaking by original rule order
    allocations.sort(key=lambda x: (x["remainder"], -x["idx"]), reverse=True)

    for i in range(unallocated_cents):
        allocations[i]["base_share"] += 1

    # Restore original ordering
    allocations.sort(key=lambda x: x["idx"])

    result = [
        {
            "staff_id": a["staff_id"],
            "amount_minor": a["base_share"],
            "basis_points": a["basis_points"],
        }
        for a in allocations
    ]

    # Invariant verification
    final_sum = sum(item["amount_minor"] for item in result)
    assert final_sum == total_tip_minor, (
        f"Tip split rounding invariant violated! Expected {total_tip_minor}, got {final_sum}"
    )

    return result
