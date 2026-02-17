"""
dcn_client.py — Thin client for the DCN HTTP API with resilient token handling:
- ensure_auth(acct) to log in once
- try_refresh_or_reauth(acct) on 401 refresh failures
- post_feature/post_particle/execute_particle retries after refresh/reauth
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import json

import requests
from eth_account import Account
from eth_account.messages import encode_defunct


class DCNClient:
    REQUIRED_TRANSFORMATIONS: Dict[str, str] = {
        "add": "return x + args[0];",
        "subtract": "return x - args[0];",
        "mul": "return x * args[0];",
        "div": "return args[0] == 0 ? 0 : x / args[0];",
    }

    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url: str = base_url
        self.timeout: float = float(timeout)
        self.session: requests.Session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self.access_token: Optional[str] = None

    # ---------- internals ----------
    def _handle_response(self, r: requests.Response):
        try:
            data = r.json()
        except Exception:
            r.raise_for_status()
            return {"raw": r.text}
        if not r.ok:
            raise requests.HTTPError(f"{r.status_code} {data}", response=r)
        return data

    def _authz_headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if self.access_token:
            h["Authorization"] = f"Bearer {self.access_token}"
        return h

    def _post_with_retry(self, path: str, payload: Dict[str, Any], *, acct: Account) -> requests.Response:
        self.ensure_auth(acct)
        url = f"{self.base_url}{path}"
        r = self.session.post(url, json=payload, headers=self._authz_headers(), timeout=self.timeout)
        if r.status_code == 401:
            self.try_refresh_or_reauth(acct)
            r = self.session.post(url, json=payload, headers=self._authz_headers(), timeout=self.timeout)
        return r

    # ---------- public HTTP ----------
    def get_nonce(self, address: str) -> str:
        url = f"{self.base_url}/nonce/{address}"
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        js = r.json()
        if "nonce" not in js:
            raise ValueError(f"Unexpected nonce response: {js}")
        return str(js["nonce"])

    def post_auth(self, address: str, message: str, signature: str) -> Dict:
        url = f"{self.base_url}/auth"
        r = self.session.post(
            url,
            json={"address": address, "message": message, "signature": signature},
            timeout=self.timeout,
        )
        data = self._handle_response(r)
        self.access_token = data.get("access_token")
        return data

    # ---------- robust auth helpers ----------
    def ensure_auth(self, acct: Account):
        """Login if we don't yet have tokens."""
        if self.access_token:
            return
        nonce = self.get_nonce(acct.address)
        msg = f"Login nonce: {nonce}"
        sig = acct.sign_message(encode_defunct(text=msg)).signature.hex()
        self.post_auth(acct.address, msg, sig)
        if not self.access_token:
            raise RuntimeError("Auth failed — missing tokens")

    def try_refresh_or_reauth(self, acct: Account):
        """Do a fresh /auth with the same account (server currently exposes no refresh route)."""
        nonce = self.get_nonce(acct.address)
        msg = f"Login nonce: {nonce}"
        sig = acct.sign_message(encode_defunct(text=msg)).signature.hex()
        self.post_auth(acct.address, msg, sig)

    # ---------- feature/particle/execute ----------
    def post_feature(self, payload: Dict[str, Any], *, acct: Account) -> Dict[str, Any]:
        r = self._post_with_retry("/feature", payload, acct=acct)
        return self._handle_response(r)

    def post_particle(self, payload: Dict[str, Any], *, acct: Account) -> Dict[str, Any]:
        r = self._post_with_retry("/particle", payload, acct=acct)
        return self._handle_response(r)

    def get_feature(self, name: str) -> Dict[str, Any]:
        url = f"{self.base_url}/feature/{name}"
        r = self.session.get(url, headers=self._authz_headers(), timeout=self.timeout)
        return self._handle_response(r)

    def get_particle(self, name: str) -> Dict[str, Any]:
        url = f"{self.base_url}/particle/{name}"
        r = self.session.get(url, headers=self._authz_headers(), timeout=self.timeout)
        return self._handle_response(r)

    def get_transformation(self, name: str) -> Dict[str, Any]:
        url = f"{self.base_url}/transformation/{name}"
        r = self.session.get(url, headers=self._authz_headers(), timeout=self.timeout)
        return self._handle_response(r)

    def post_transformation(self, payload: Dict[str, Any], *, acct: Account) -> Dict[str, Any]:
        r = self._post_with_retry("/transformation", payload, acct=acct)
        return self._handle_response(r)

    def has_transformation(self, name: str) -> bool:
        url = f"{self.base_url}/transformation/{name}"
        r = self.session.get(url, headers=self._authz_headers(), timeout=self.timeout)
        if r.status_code == 404:
            return False
        if 200 <= r.status_code < 300:
            return True
        body_preview = (r.text or "").strip().replace("\n", " ")
        if len(body_preview) > 300:
            body_preview = body_preview[:300] + "..."
        raise RuntimeError(
            f"Failed to check transformation '{name}': status={r.status_code}, response={body_preview}"
        )

    def ensure_required_transformations(
        self,
        *,
        acct: Account,
        required: Optional[Dict[str, str]] = None,
        auto_create: bool = True,
    ) -> None:
        required = required or self.REQUIRED_TRANSFORMATIONS
        missing: List[str] = []

        for name, sol_src in required.items():
            if self.has_transformation(name):
                continue

            if not auto_create:
                missing.append(name)
                continue

            payload = {"name": name, "sol_src": sol_src}
            try:
                self.post_transformation(payload, acct=acct)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to auto-create required transformation '{name}'. "
                    f"Payload: {json.dumps(payload, ensure_ascii=False)}. Error: {exc}"
                ) from exc

            if not self.has_transformation(name):
                raise RuntimeError(
                    f"Transformation '{name}' still missing after creation attempt. "
                    f"Payload: {json.dumps(payload, ensure_ascii=False)}"
                )

        if missing:
            raise RuntimeError(
                "Missing required transformations: "
                + ", ".join(missing)
                + ". Either create them on the server or set auto-bootstrap on."
            )

    def execute_particle(
        self,
        acct: Account,
        particle_name: str,
        samples_count: int,
        running_instances: List[Dict[str, int]],
    ) -> List[Dict[str, Any]]:
        payload = {
            "particle_name": particle_name,
            "samples_count": int(samples_count),
            "running_instances": running_instances,
        }
        r = self._post_with_retry("/execute", payload, acct=acct)
        data = self._handle_response(r)
        if isinstance(data, list):
            return data
        raise RuntimeError(f"Unexpected /execute response shape: {type(data).__name__}")

    # ---------- startup checks ----------
    def preflight_endpoints(
        self,
        *,
        acct: Account,
        ensure_transformations: bool = True,
        auto_create_transformations: bool = True,
    ) -> None:
        """
        Lightweight endpoint availability check before generation.
        Sends intentionally invalid payloads and expects 400 parsing failures.
        """
        if ensure_transformations:
            self.ensure_required_transformations(
                acct=acct,
                auto_create=auto_create_transformations,
            )

        checks = [
            (
                "feature",
                "/feature",
                {"_preflight": True},
                {"name": "my_feature", "dimensions": [{"transformations": [{"name": "add", "args": [1]}]}]},
            ),
            (
                "particle",
                "/particle",
                {"_preflight": True},
                {
                    "name": "my_particle",
                    "feature_name": "my_feature",
                    "composite_names": ["", "", "", "", "", ""],
                    "condition_name": "",
                    "condition_args": [],
                },
            ),
            (
                "execute",
                "/execute",
                {"_preflight": True},
                {
                    "particle_name": "my_particle",
                    "samples_count": 4,
                    "running_instances": [{"start_point": 0, "transformation_shift": 0}],
                },
            ),
        ]

        for _, path, invalid_payload, sample_payload in checks:
            try:
                r = self._post_with_retry(path, invalid_payload, acct=acct)
            except requests.RequestException as exc:
                raise RuntimeError(
                    f"Preflight failed for {path}: {exc}. "
                    f"Sample payload: {json.dumps(sample_payload, ensure_ascii=False)}"
                ) from exc

            if r.status_code in (200, 201, 204, 400):
                continue

            body_preview = (r.text or "").strip().replace("\n", " ")
            if len(body_preview) > 500:
                body_preview = body_preview[:500] + "..."
            raise RuntimeError(
                f"Preflight failed for {path}: status={r.status_code}, response={body_preview}. "
                f"Sample payload: {json.dumps(sample_payload, ensure_ascii=False)}"
            )
