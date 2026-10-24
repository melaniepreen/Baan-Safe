"""System 2 interface. Owner: Melanie.

decide() calls the Nemotron orchestrator, then the Sapling verifier for
aid-eligibility and denial outcomes, before the Decision Router. The
orchestrator still raises while its model and hosting are unset. Aid
exception proposals are a separate stub. Neither decides a case yet.
"""
