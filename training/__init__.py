"""Training data. The event log is append-only. Exporters are separate."""

from training.log import AppendResult, append_event, events_path, read_events

__all__ = ["AppendResult", "append_event", "events_path", "read_events"]
