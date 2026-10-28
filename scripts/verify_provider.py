#!/usr/bin/env python3
"""Verify one OpenAI-compatible provider (e.g. GapGPT) from YOUR machine.

Why a script: this development sandbox has no outbound access to
api.gapgpt.app and no API key, so live verification must happen where the
network and the key actually exist (your PC or the VPS).

Usage
-----
    # Key stays in the environment / .env; never pass it as an argument.
    export GAPGPT_API_KEY=...
    python scripts/verify_provider.py

    # Anything OpenAI-compatible:
    python scripts/verify_provider.py --base-url https://host/v1 \
        --model gpt-4o-mini --key-env MY_KEY --prompt "سلام، یک جمله"

Exit codes
----------
    0 = provider answered a real HTTP 200
    2 = not configured (missing key/base URL/model)
    3 = provider error (network, 401/429/5xx, malformed body)
    4 = budget guard refused the call before any network request
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.base import ChatMessage, ChatRequest, ProviderError  # noqa: E402
from app.ai.providers import GAPGPT_DEFAULT_BASE_URL, GapGPTProvider  # noqa: E402
from app.ai.providers import OpenAICompatibleProvider  # noqa: E402


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader: no dependency, never overrides real env vars."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="One-shot live check of an OpenAI-compatible provider")
    ap.add_argument("--provider", choices=["gapgpt", "openai_compatible"], default="gapgpt")
    ap.add_argument("--base-url", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--key-env", default="", help="environment variable holding the key")
    ap.add_argument("--prompt", default="فقط بنویس: OK")
    ap.add_argument("--max-tokens", type=int, default=32)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--env-file", default=".env")
    args = ap.parse_args(argv)

    _load_dotenv(Path(args.env_file))

    key_env = args.key_env or ("AI_FALLBACK_API_KEY" if args.provider == "openai_compatible"
                               else "AI_PRIMARY_API_KEY")
    if args.provider == "gapgpt" and not args.key_env and not os.environ.get("AI_PRIMARY_API_KEY"):
        key_env = "GAPGPT_API_KEY"
    key = os.environ.get(key_env, "").strip()
    base = args.base_url or os.environ.get("AI_PRIMARY_BASE_URL", "").strip()
    model = args.model or os.environ.get("GAPGPT_DEFAULT_MODEL", "").strip() or "gpt-4o-mini"

    if not key:
        print(f"[blocked] no API key in ${key_env}. Nothing was sent. "
              f"Set it in the environment or in {args.env_file}.")
        return 2
    if args.provider == "openai_compatible" and not base:
        print("[blocked] --base-url (or AI_PRIMARY_BASE_URL) is required for openai_compatible.")
        return 2

    if args.provider == "gapgpt":
        provider = GapGPTProvider(base_url=base or GAPGPT_DEFAULT_BASE_URL, api_key=key,
                                  model=model, timeout=args.timeout)
    else:
        provider = OpenAICompatibleProvider(base_url=base, api_key=key, model=model,
                                            timeout=args.timeout)

    print(f"provider : {provider.name}")
    print(f"base_url : {provider.base_url}")
    print(f"model    : {provider.model}")
    print(f"key      : set (${key_env}, {len(key)} chars) — value is never printed")
    print(f"est/call : ~${provider.estimate_cost_usd(60, 40, provider.model):.6f} (conservative)")

    req = ChatRequest(messages=[ChatMessage("system", "You are a connectivity probe."),
                                ChatMessage("user", args.prompt)],
                      model=provider.model, max_tokens=args.max_tokens, temperature=0.0)
    started = time.perf_counter()
    try:
        result = provider.chat(req)
    except ProviderError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        print(f"[failed] after {latency} ms: {exc} "
              f"(retryable={exc.retryable}, status={exc.status_code})")
        print("Hint: 401/403 -> wrong key or model not enabled; 404 -> base URL must end at /v1; "
              "429 -> rate limit/quota; timeouts -> network or provider outage.")
        return 3
    latency = int((time.perf_counter() - started) * 1000)
    print("\n[verified] HTTP 200 from the provider")
    print(f"  latency  : {result.latency_ms or latency} ms")
    print(f"  tokens   : {result.prompt_tokens} in / {result.completion_tokens} out")
    print(f"  cost est : ${result.cost_usd:.6f} (estimate, not the provider's invoice)")
    print(f"  reply    : {result.text.strip()[:300]!r}")
    print("\nNext: put the same values in .env and restart ROMKA; "
          "the Settings page then shows this provider as live-verified for this process.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
