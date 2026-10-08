"""
Worker service package.
"""

from .processor import process_stripe_event

__all__ = ["process_stripe_event"]
