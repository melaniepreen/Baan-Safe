"""Sources that were probed and not wired as adapters.

A candidate is not fetched at runtime. TODO_HUMAN means a person still has
to decide whether it may become an adapter. None of these payloads were
turned into eligibility, safeguarding, or triage rules.
"""

from __future__ import annotations

# Probed 24 October 2026 from this environment. No API key and no email were sent.
CANDIDATES: tuple[dict[str, str], ...] = (
    {
        "source_id": "sphere_handbook_api",
        "url": "https://handbook.spherestandards.org/",
        "probed": "2026-10-24",
        "accessible": "no",
        "why": (
            "The public handbook host and https://spherestandards.org/wp-json/wp/v2/pages "
            "returned HTTP 403. Sphere describes a search API that needs a key from "
            "learning@spherestandards.org. No key is stored. The 2018 handbook wording "
            "already in the local YAML was read from an archive capture, not from this API."
        ),
    },
    {
        "source_id": "ifrc_go",
        "url": "https://goadmin.ifrc.org/api/v2/disaster_type/",
        "probed": "2026-10-24",
        "accessible": "yes",
        "why": (
            "HTTP 200 returned a disaster-type list. The summary fields were empty. "
            "That list is an event taxonomy, not the protection, gender and inclusion "
            "standards. It was not normalised into rules."
        ),
    },
    {
        "source_id": "ifrc_documents",
        "url": "https://www.ifrc.org/api/documents",
        "probed": "2026-10-24",
        "accessible": "no",
        "why": "HTTP 403. The PGI minimum standards stay in the local YAML excerpt.",
    },
    {
        "source_id": "iasc",
        "url": "https://interagencystandingcommittee.org/jsonapi",
        "probed": "2026-10-24",
        "accessible": "no",
        "why": (
            "HTTP 202 with an empty body and a WAF challenge header. No product JSON "
            "was retrieved. A ReliefWeb copy of an IASC catalogue was not used."
        ),
    },
    {
        "source_id": "hdx_hapi",
        "url": "https://hapi.humdata.org/api/v2/util/version",
        "probed": "2026-10-24",
        "accessible": "partial",
        "why": (
            "The version endpoint returned HTTP 200 and named API 0.9.15. "
            "HAPI serves indicators (needs, funding, risk), and every data query "
            "needs an app identifier made from an application name and an email. "
            "No email was sent. Indicator rows are not policy text."
        ),
    },
    {
        "source_id": "hdx_ckan",
        "url": "https://data.humdata.org/api/3/action/package_search",
        "probed": "2026-10-24",
        "accessible": "yes",
        "why": (
            "HTTP 200. A search for Sphere standards returned operational datasets, "
            "not handbook text. Dataset rows are already ingested elsewhere. "
            "They were not normalised into rules."
        ),
    },
    {
        "source_id": "ocha_hpc_fts",
        "url": "https://api.hpc.tools/v1/public/fts/flow",
        "probed": "2026-10-24",
        "accessible": "yes",
        "why": (
            "HTTP 200 returned funding-flow records for Thailand. Those totals are "
            "not copied here and are not eligibility rules."
        ),
    },
    {
        "source_id": "data_go_th",
        "url": "https://data.go.th/api/3/action/package_search",
        "probed": "2026-10-24",
        "accessible": "no",
        "why": "HTTP 403. No dataset body was read.",
    },
    {
        "source_id": "gdcatalog_ratchakitcha",
        "url": "https://gdcatalog.go.th/api/3/action/package_show?id=gdpublish-dataset-02-04",
        "probed": "2026-10-24",
        "accessible": "partial",
        "why": (
            "Package metadata returned HTTP 200 and lists monthly Royal Gazette JSON. "
            "robots.txt for User-agent * disallows /. The JSON host timed out. "
            "Gazette titles were not downloaded and were not turned into rules."
        ),
    },
    {
        "source_id": "worldbank_documents",
        "url": "https://search.worldbank.org/api/v3/wds",
        "probed": "2026-10-24",
        "accessible": "yes",
        "why": (
            "HTTP 200 returned document metadata for a Thailand social-protection "
            "query. Titles and links are not a rule corpus. No abstract was stored."
        ),
    },
    {
        "source_id": "worldbank_aspire",
        "url": "https://www.worldbank.org/en/data/datatopics/aspire",
        "probed": "2026-10-24",
        "accessible": "no",
        "why": (
            "ASPIRE publishes indicator files, not a verified JSON API of legal rules. "
            "No indicator was copied into a rule."
        ),
    },
    {
        "source_id": "krisdika",
        "url": "https://www.krisdika.go.th/",
        "probed": "2026-10-24",
        "accessible": "no",
        "why": "The TLS certificate did not verify. No law text was fetched.",
    },
)
