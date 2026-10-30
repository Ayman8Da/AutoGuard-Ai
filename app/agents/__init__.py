"""Specialised agents: Diagnostic, Risk Assessment, Maintenance, Reporting.

Each agent is a pure, independently testable unit that receives a typed payload
and returns a typed result. LangGraph nodes in ``app.orchestration`` compose
them; the Monitoring Agent observes them without being part of the vehicle
diagnosis chain.
"""
