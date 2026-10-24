"""Caller simulation for training and eval. Not on the live path.

Ideas from MIMESIS, "Learning User Simulators as Training Environments
for Interactive Agents", arXiv:2610.09484,
https://huggingface.co/papers/2610.09484. No paper source is copied.
The scripted caller is the default. A model backend goes through llm/client.py.
"""

PAPER_ID = "2610.09484"
PAPER_URL = "https://huggingface.co/papers/2610.09484"

__all__ = ["PAPER_ID", "PAPER_URL"]
