"""Explicit, device-scoped SSH-2 algorithm policy. No global SSH defaults change."""
from functools import lru_cache
from hashlib import sha256
import json

import asyncssh

from .contracts import SSHAlgorithms

FIELDS = tuple(SSHAlgorithms.model_fields)
LEGACY = {
    "kex_algs": ["diffie-hellman-group14-sha1", "diffie-hellman-group-exchange-sha1",
                 "diffie-hellman-group1-sha1"],
    "server_host_key_algs": ["ssh-rsa", "ssh-dss"],
    "signature_algs": ["ssh-rsa", "ssh-dss"],
    "encryption_algs": ["aes128-cbc", "aes192-cbc", "aes256-cbc", "3des-cbc"],
    "mac_algs": ["hmac-sha1-etm@openssh.com", "hmac-sha1", "hmac-sha1-96", "hmac-md5", "hmac-md5-96"],
}
LABELS = {
    "auto": "Otomatik", "standard": "Standart", "huawei_legacy": "Eski VRP",
    "legacy_sha1": "Eski SSH · SHA-1", "legacy_cbc": "Eski SSH · CBC/Group1",
    "advanced": "Gelişmiş",
}


@lru_cache(maxsize=1)
def algorithms():
    defaults = asyncssh.SSHClientConnectionOptions(config=[])
    modern = {}
    for field in FIELDS:
        values = [v.decode() if isinstance(v, bytes) else v for v in getattr(defaults, field)]
        if field == "server_host_key_algs":
            values = ["ssh-ed25519", "ssh-ed448", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384",
                      "ecdsa-sha2-nistp521", "rsa-sha2-512", "rsa-sha2-256"]
        modern[field] = list(dict.fromkeys(v for v in values
            if v not in LEGACY[field] and "sha1" not in v and not v.startswith("gss-")
            and v != "none" and "umac-64" not in v))
    available = {}
    for field in FIELDS:
        available[field] = []
        for value in [*modern[field], *LEGACY[field]]:
            try:
                asyncssh.SSHClientConnectionOptions(config=[], **{field: [value]})
                available[field].append(value)
            except (ValueError, asyncssh.Error):
                continue
    return modern, available


def legacy_allowed(device):
    # Existing huawei_legacy records already required explicit consent before 0006.
    return device.allow_legacy_ssh or device.ssh_profile == "huawei_legacy"


def options_for(profile, device):
    modern, available = algorithms()
    if profile == "standard":
        return {key: list(values) for key, values in modern.items()}
    if not legacy_allowed(device) and profile != "advanced":
        raise ValueError("legacy_ssh_confirmation_required")
    if profile == "advanced":
        explicit = device.ssh_algorithms.model_dump()
        if not any(explicit.values()):
            raise ValueError("ssh_algorithms_required")
        result = {}
        for field, values in explicit.items():
            if any(value not in available[field] for value in values):
                raise ValueError("ssh_algorithm_unavailable")
            if not legacy_allowed(device) and any(value not in modern[field] for value in values):
                raise ValueError("legacy_ssh_confirmation_required")
            result[field] = values or list(modern[field])
        return result
    additions = {field: [] for field in FIELDS}
    additions["kex_algs"] = LEGACY["kex_algs"][:2]
    additions["server_host_key_algs"] = ["ssh-rsa"]
    additions["signature_algs"] = ["ssh-rsa"]
    additions["mac_algs"] = LEGACY["mac_algs"][:2]
    if profile in {"huawei_legacy", "legacy_cbc", "legacy_ancient"}:
        additions["kex_algs"].append("diffie-hellman-group1-sha1")
        additions["encryption_algs"] = LEGACY["encryption_algs"][:3]
    if profile == "huawei_legacy":
        additions["encryption_algs"] = ["aes128-cbc"]
    if profile == "legacy_ancient":
        additions = LEGACY
    if profile not in {"huawei_legacy", "legacy_sha1", "legacy_cbc", "legacy_ancient"}:
        raise ValueError("invalid_ssh_profile")
    return {field: list(dict.fromkeys([*modern[field], *(
        value for value in additions[field] if value in available[field])])) for field in FIELDS}


def attempt_profiles(device, cached=None):
    if device.ssh_profile != "auto":
        return [device.ssh_profile]
    profiles = ["standard"]
    if legacy_allowed(device):
        profiles.extend(["legacy_sha1", "legacy_cbc", "legacy_ancient"])
    # Cached presets still contain modern algorithms first, permitting upgrades.
    if cached in profiles:
        profiles.remove(cached)
        profiles.insert(0, cached)
    return profiles


def target_signature(device):
    fields = ("management_address", "ssh_port", "site", "collector", "ssh_profile",
              "allow_legacy_ssh", "connection_revision", "host_key_fingerprint",
              "configured_profile_id", "resolved_profile_id", "profile_revision",
              "management_mode", "profile_resolution_status")
    values = {key: getattr(device, key) for key in fields}
    values["ssh_algorithms"] = device.ssh_algorithms.model_dump()
    return sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def catalog():
    modern, available = algorithms()
    return {"profiles": [{"id": name, "label": label,
                         "legacy": name in {"huawei_legacy", "legacy_sha1", "legacy_cbc"}}
                        for name, label in LABELS.items()],
            "algorithms": {field: [{"id": value, "legacy": value not in modern[field]}
                                  for value in values] for field, values in available.items()},
            "protocol": "SSH-2", "max_attempts": 4, "timeout_seconds": 30}
