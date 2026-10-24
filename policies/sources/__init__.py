"""Policy source adapters. Local YAML is the live corpus. Remote catalogs that do not serve rule text stay candidates."""

from policies.sources.base import PolicySourceAdapter
from policies.sources.local_yaml import LocalYamlAdapter

__all__ = ["LocalYamlAdapter", "PolicySourceAdapter"]
