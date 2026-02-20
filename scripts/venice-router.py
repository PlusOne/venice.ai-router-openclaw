#!/usr/bin/env python3
"""
Venice.ai Supreme Router — cost-optimized model routing for OpenClaw.

Classifies prompt complexity and routes to the cheapest Venice.ai model
that can handle the task adequately. Supports streaming, tier overrides,
and direct model selection.

Usage:
    python3 venice-router.py --prompt "your question here"
    python3 venice-router.py --tier mid --prompt "explain recursion"
    python3 venice-router.py --stream --prompt "write a story"
    python3 venice-router.py --classify "your question"
    python3 venice-router.py --list-models
"""

import argparse
import json
import os
import re
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ── Venice.ai API ────────────────────────────────────────────────────────────

VENICE_API_BASE = "https://api.venice.ai/api/v1"

# ── Model Tiers (sorted cheapest → most expensive) ──────────────────────────
# Prices per 1M tokens [input_usd, output_usd]

MODEL_TIERS = {
    "cheap": {
        "description": "Simple Q&A, greetings, math, lookups",
        "models": [
            {"id": "qwen3-4b",            "name": "Venice Small",        "input": 0.05,  "output": 0.15,  "ctx": 32000,   "private": True},
            {"id": "openai-gpt-oss-120b",  "name": "GPT OSS 120B",       "input": 0.07,  "output": 0.30,  "ctx": 128000,  "private": True},
            {"id": "zai-org-glm-4.7-flash","name": "GLM 4.7 Flash",      "input": 0.13,  "output": 0.50,  "ctx": 128000,  "private": True},
            {"id": "llama-3.2-3b",         "name": "Llama 3.2 3B",        "input": 0.15,  "output": 0.60,  "ctx": 128000,  "private": True},
        ],
        "default": "qwen3-4b",
    },
    "budget": {
        "description": "Moderate questions, summaries, translations",
        "models": [
            {"id": "olafangensan-glm-4.7-flash-heretic", "name": "GLM 4.7 Flash Heretic", "input": 0.14, "output": 0.80, "ctx": 128000, "private": True},
            {"id": "qwen3-235b-a22b-instruct-2507", "name": "Qwen 3 235B",  "input": 0.15,  "output": 0.75,  "ctx": 128000,  "private": True},
            {"id": "venice-uncensored",    "name": "Venice Uncensored",   "input": 0.20,  "output": 0.90,  "ctx": 32000,   "private": True},
            {"id": "qwen3-vl-235b-a22b",   "name": "Qwen3 VL 235B",      "input": 0.25,  "output": 1.50,  "ctx": 256000,  "private": True},
        ],
        "default": "qwen3-235b-a22b-instruct-2507",
    },
    "mid": {
        "description": "Code generation, analysis, longer writing",
        "models": [
            {"id": "grok-code-fast-1",     "name": "Grok Code Fast",     "input": 0.25,  "output": 1.87,  "ctx": 256000,  "private": False},
            {"id": "deepseek-v3.2",        "name": "DeepSeek V3.2",      "input": 0.40,  "output": 1.00,  "ctx": 160000,  "private": True},
            {"id": "minimax-m21",          "name": "MiniMax M2.1",       "input": 0.40,  "output": 1.60,  "ctx": 198000,  "private": True},
            {"id": "minimax-m25",          "name": "MiniMax M2.5",       "input": 0.40,  "output": 1.60,  "ctx": 198000,  "private": True},
            {"id": "qwen3-next-80b",       "name": "Qwen 3 Next 80B",   "input": 0.35,  "output": 1.90,  "ctx": 256000,  "private": True},
            {"id": "mistral-31-24b",       "name": "Venice Medium",      "input": 0.50,  "output": 2.00,  "ctx": 128000,  "private": True},
            {"id": "llama-3.3-70b",        "name": "Llama 3.3 70B",      "input": 0.70,  "output": 2.80,  "ctx": 128000,  "private": True},
        ],
        "default": "deepseek-v3.2",
    },
    "high": {
        "description": "Complex reasoning, multi-step tasks, code review",
        "models": [
            {"id": "grok-41-fast",         "name": "Grok 4.1 Fast",      "input": 0.50,  "output": 1.25,  "ctx": 256000,  "private": False},
            {"id": "zai-org-glm-4.7",      "name": "GLM 4.7",            "input": 0.55,  "output": 2.65,  "ctx": 198000,  "private": True},
            {"id": "gemini-3-flash-preview","name": "Gemini 3 Flash",    "input": 0.70,  "output": 3.75,  "ctx": 256000,  "private": False},
            {"id": "kimi-k2-thinking",     "name": "Kimi K2 Thinking",   "input": 0.75,  "output": 3.20,  "ctx": 256000,  "private": True},
            {"id": "qwen3-coder-480b-a35b-instruct", "name": "Qwen 3 Coder 480B", "input": 0.75, "output": 3.00, "ctx": 256000, "private": True},
            {"id": "zai-org-glm-5",        "name": "GLM 5",              "input": 1.00,  "output": 3.20,  "ctx": 198000,  "private": True},
        ],
        "default": "deepseek-v3.2" if False else "kimi-k2-thinking",
    },
    "premium": {
        "description": "Expert-level analysis, architecture, research",
        "models": [
            {"id": "openai-gpt-52",        "name": "GPT-5.2",            "input": 2.19,  "output": 17.50, "ctx": 256000,  "private": False},
            {"id": "gemini-3-pro-preview",  "name": "Gemini 3 Pro",      "input": 2.50,  "output": 15.00, "ctx": 198000,  "private": False},
            {"id": "claude-sonnet-4-6",     "name": "Claude Sonnet 4.6", "input": 3.75,  "output": 18.75, "ctx": 1000000, "private": False},
            {"id": "claude-sonnet-45",      "name": "Claude Sonnet 4.5", "input": 3.75,  "output": 18.75, "ctx": 198000,  "private": False},
            {"id": "claude-opus-45",        "name": "Claude Opus 4.5",   "input": 6.00,  "output": 30.00, "ctx": 198000,  "private": False},
            {"id": "claude-opus-4-6",       "name": "Claude Opus 4.6",   "input": 6.00,  "output": 30.00, "ctx": 1000000, "private": False},
        ],
        "default": "gemini-3-pro-preview",
    },
}

TIER_ORDER = ["cheap", "budget", "mid", "high", "premium"]

# ── Complexity Classifier ────────────────────────────────────────────────────

# Patterns that indicate higher complexity
PREMIUM_PATTERNS = [
    r"\b(architect(ure)?s?|design\s+pattern|system\s+design|distributed\s+system)\b",
    r"\b(research\s+paper|academic|peer.review|hypothesis|theorem)\b",
    r"\b(security\s+audit|penetration\s+test|vulnerability\s+assess)\b",
    r"\b(optimize|refactor)\s+(the\s+)?(entire|whole|complete|full)\b",
    r"\b(compare\s+and\s+contrast|comprehensive\s+analysis)\b",
    r"\b(write|design|create|build|implement)\s+(a\s+)?(complete|full|production|entire|comprehensive)\b",
    r"\bprove\s+(that|why|mathematically)\b",
    r"\b(formal\s+verification|type\s+theory|category\s+theory)\b",
    r"\b(machine\s+learning|deep\s+learning|neural\s+network|transformer)\b",
    r"\b(business\s+plan|go.to.market|competitive\s+analysis)\b",
    r"\b(event\s+sourc|cqrs|saga\s+pattern|domain.driven|hexagonal)\b",
    r"\b(microservices?|distributed)\b.*\b(architect|design|scal|pattern)\b",
    r"\b(horizontal|vertical)\s+scal\b",
    r"\b(real.time).*(platform|system|architect|infra)\b",
]

HIGH_PATTERNS = [
    r"\b(explain|describe)\s+(in\s+detail|thoroughly|step.by.step)\b",
    r"\b(debug|fix|troubleshoot|diagnose)\b",
    r"\b(review|analyze|evaluate|assess|critique)\b",
    r"\b(code\s+review|pull\s+request|merge\s+request)\b",
    r"\b(algorithm|data\s+structure|complexity|big.?o)\b",
    r"\b(api|endpoint|microservices?|database\s+schema)\b",
    r"\b(deploy|ci.?cd|docker|kubernetes|infrastructure)\b",
    r"\b(test|unit\s+test|integration\s+test|e2e)\b",
    r"\b(regex|regular\s+expression)\b",
    r"\b(concurren(t|cy)|parallel|async(hronous)?|thread)\b",
    r"\bwrite\s+(a\s+)?(function|class|module|script|program)\b",
    r"\b(typescript|python|rust|golang|javascript|java|c\+\+|swift)\b.*\b(implement|write|create|build)\b",
    r"\b(implement|build|create)\s+(a|an)\s+\w+\s+(in|using|with)\b",
    r"\b(pros?\s+and\s+cons?|trade.?offs?|advantages?\s+and\s+disadvantages?)\b",
]

MID_PATTERNS = [
    r"\b(explain|describe|summarize|outline)\b",
    r"\b(how\s+(do|does|to|can|would))\b",
    r"\b(what\s+(is|are|does|do)\s+the\s+difference)\b",
    r"\b(convert|transform|translate|format)\b",
    r"\b(list|enumerate|give\s+me|provide)\s+\d+\b",
    r"\b(write|draft|compose)\s+(a|an)\s+(email|letter|message|blog|article)\b",
    r"\b(code|script|function|snippet)\b",
    r"\bexample(s)?\s+(of|for)\b",
    r"\b(compare|versus|vs\.?)\b",
    r"\b(why|how\s+come|what\s+causes)\b",
]

CHEAP_PATTERNS = [
    r"^(hi|hello|hey|yo|sup|greetings|good\s+(morning|afternoon|evening))[\s!?.]*$",
    r"^(thanks?|thank\s+you|thx|ty|cheers)[\s!?.]*$",
    r"^(yes|no|ok(ay)?|sure|nope|yep|yup|nah)[\s!?.]*$",
    r"^(what\s+time|what\s+day|what\s+date)\b",
    r"^\d+\s*[\+\-\*\/\%\^]\s*\d+\s*[=?]?\s*$",
    r"^(who\s+(is|was|are))\s+\w+[\s\w]*\??\s*$",
    r"^(define|meaning\s+of|what\s+does\s+\w+\s+mean)\b",
    r"^(translate|say)\s+.{1,50}\s+(in|to)\s+\w+\s*\??\s*$",
    r"^.{1,30}$",  # Very short queries
]


def classify_complexity(prompt: str) -> str:
    """Classify prompt complexity into a tier name."""
    prompt_lower = prompt.strip().lower()
    prompt_len = len(prompt)

    # ── Check for trivial / cheap patterns first ─────────────────────────
    # But skip the short-text catch-all if the prompt has complex keywords
    has_complex_signal = any(
        re.search(p, prompt_lower, re.IGNORECASE)
        for p in PREMIUM_PATTERNS + HIGH_PATTERNS
    )
    if not has_complex_signal:
        for pattern in CHEAP_PATTERNS:
            if re.search(pattern, prompt_lower, re.IGNORECASE):
                return "cheap"

    # ── Score-based classification ───────────────────────────────────────
    score = 0

    # Length heuristic
    if prompt_len > 1000:
        score += 3
    elif prompt_len > 500:
        score += 2
    elif prompt_len > 200:
        score += 1
    elif prompt_len < 50:
        score -= 1

    # Code block detection
    if "```" in prompt:
        score += 2
    if re.search(r"(def |class |function |const |let |var |import |from )", prompt):
        score += 1

    # Multi-step instructions
    bullet_count = len(re.findall(r"^\s*[-*\d+\.]\s", prompt, re.MULTILINE))
    if bullet_count >= 5:
        score += 2
    elif bullet_count >= 3:
        score += 1

    # Question complexity (multiple questions = higher complexity)
    question_marks = prompt.count("?")
    if question_marks >= 3:
        score += 2
    elif question_marks >= 2:
        score += 1

    # Premium pattern matching (accumulate — multiple premium signals = stronger)
    premium_matches = 0
    for pattern in PREMIUM_PATTERNS:
        if re.search(pattern, prompt_lower, re.IGNORECASE):
            premium_matches += 1
    if premium_matches >= 2:
        score += 5
    elif premium_matches == 1:
        score += 3

    # High pattern matching
    high_matches = 0
    for pattern in HIGH_PATTERNS:
        if re.search(pattern, prompt_lower, re.IGNORECASE):
            high_matches += 1
    score += min(high_matches, 3)

    # Mid pattern matching
    mid_matches = 0
    for pattern in MID_PATTERNS:
        if re.search(pattern, prompt_lower, re.IGNORECASE):
            mid_matches += 1
    if mid_matches > 0 and score < 2:
        score += 1

    # ── Map score to tier ────────────────────────────────────────────────
    if score >= 6:
        return "premium"
    elif score >= 4:
        return "high"
    elif score >= 2:
        return "mid"
    elif score >= 1:
        return "budget"
    else:
        return "cheap"


def get_effective_tier(classified_tier: str, max_tier: str | None = None) -> str:
    """Apply max_tier cap if configured."""
    if max_tier and max_tier in TIER_ORDER:
        max_idx = TIER_ORDER.index(max_tier)
        classified_idx = TIER_ORDER.index(classified_tier)
        if classified_idx > max_idx:
            return max_tier
    return classified_tier


def select_model(tier: str, prefer_private: bool = True) -> dict:
    """Select the best model from a tier, preferring private models."""
    tier_data = MODEL_TIERS[tier]
    models = tier_data["models"]

    if prefer_private:
        private_models = [m for m in models if m.get("private", False)]
        if private_models:
            return private_models[0]

    return models[0]


# ── Venice.ai API Client ─────────────────────────────────────────────────────

def venice_chat(
    api_key: str,
    model_id: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    stream: bool = False,
) -> str | None:
    """Send a chat completion request to Venice.ai."""
    url = f"{VENICE_API_BASE}/chat/completions"

    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if stream:
        headers["Accept"] = "text/event-stream"

    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="POST")

    try:
        with urlopen(req) as resp:
            if stream:
                return _handle_stream(resp)
            else:
                body = json.loads(resp.read().decode("utf-8"))
                return _extract_response(body)
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"\n❌ Venice API error ({e.code}): {error_body}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"\n❌ Connection error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def _handle_stream(resp) -> str:
    """Handle SSE streaming response."""
    full_content = []
    for line in resp:
        line = line.decode("utf-8").strip()
        if not line or not line.startswith("data: "):
            continue
        data_str = line[6:]
        if data_str == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
            choices = chunk.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    print(content, end="", flush=True)
                    full_content.append(content)
        except json.JSONDecodeError:
            continue
    print()  # Final newline
    return "".join(full_content)


def _extract_response(body: dict) -> str:
    """Extract content from a non-streaming response."""
    choices = body.get("choices", [])
    if not choices:
        return "(no response)"
    message = choices[0].get("message", {})
    content = message.get("content", "(empty)")

    # Show usage if available
    usage = body.get("usage", {})
    if usage:
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        print(
            f"\n📊 Tokens: {prompt_tokens} in → {completion_tokens} out ({total_tokens} total)",
            file=sys.stderr,
        )

    return content


# ── List Models ──────────────────────────────────────────────────────────────

def list_models():
    """Print all model tiers and their models."""
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║              Venice.ai Supreme Router — Model Tiers            ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print()

    for tier_name in TIER_ORDER:
        tier = MODEL_TIERS[tier_name]
        emoji = {"cheap": "💚", "budget": "💙", "mid": "💛", "high": "🧡", "premium": "💎"}
        print(f"  {emoji.get(tier_name, '⚪')} {tier_name.upper()} — {tier['description']}")
        print(f"  {'─' * 60}")

        for m in tier["models"]:
            privacy = "🔒 private" if m["private"] else "🔀 anon"
            default_marker = " ⭐" if m["id"] == tier["default"] else ""
            ctx_k = m["ctx"] // 1000
            print(
                f"    {m['name']:.<30s} {m['id']:<40s}"
            )
            print(
                f"      ${m['input']:<6.2f} in / ${m['output']:<6.2f} out  "
                f"| {ctx_k}K ctx | {privacy}{default_marker}"
            )
        print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Venice.ai Supreme Router — cost-optimized model routing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --prompt "What is 2+2?"
  %(prog)s --tier mid --prompt "Explain recursion"
  %(prog)s --stream --prompt "Write a haiku"
  %(prog)s --classify "Design a microservices architecture"
  %(prog)s --list-models
  %(prog)s --model deepseek-v3.2 --prompt "Hello"
        """,
    )

    parser.add_argument("--prompt", "-p", type=str, help="Prompt to send")
    parser.add_argument("--tier", "-t", type=str, choices=TIER_ORDER, help="Force a specific tier")
    parser.add_argument("--model", "-m", type=str, help="Force a specific model ID")
    parser.add_argument("--classify", "-c", type=str, help="Classify prompt complexity (no API call)")
    parser.add_argument("--list-models", "-l", action="store_true", help="List all model tiers")
    parser.add_argument("--stream", "-s", action="store_true", help="Enable streaming output")
    parser.add_argument("--temperature", type=float, default=None, help="Temperature (0.0–2.0)")
    parser.add_argument("--max-tokens", type=int, default=None, help="Max tokens")
    parser.add_argument("--system", type=str, default=None, help="System prompt")
    parser.add_argument("--prefer-anon", action="store_true", help="Prefer anonymized models over private")
    parser.add_argument("--json", "-j", action="store_true", help="Output routing info as JSON")

    args = parser.parse_args()

    # ── List models ──────────────────────────────────────────────────────
    if args.list_models:
        list_models()
        return

    # ── Classify only ────────────────────────────────────────────────────
    if args.classify:
        tier = classify_complexity(args.classify)
        model = select_model(tier, prefer_private=not args.prefer_anon)
        max_tier = os.environ.get("VENICE_MAX_TIER")
        effective_tier = get_effective_tier(tier, max_tier)
        effective_model = select_model(effective_tier, prefer_private=not args.prefer_anon)

        if args.json:
            result = {
                "classified_tier": tier,
                "effective_tier": effective_tier,
                "model_id": effective_model["id"],
                "model_name": effective_model["name"],
                "input_cost_per_1m": effective_model["input"],
                "output_cost_per_1m": effective_model["output"],
                "context_window": effective_model["ctx"],
                "private": effective_model["private"],
                "prompt_length": len(args.classify),
            }
            if max_tier and tier != effective_tier:
                result["capped_by_max_tier"] = max_tier
            print(json.dumps(result, indent=2))
        else:
            emoji = {"cheap": "💚", "budget": "💙", "mid": "💛", "high": "🧡", "premium": "💎"}
            print(f"  Complexity:  {emoji.get(effective_tier, '⚪')} {effective_tier.upper()}")
            if max_tier and tier != effective_tier:
                print(f"  (classified as {tier}, capped to {effective_tier} by VENICE_MAX_TIER)")
            print(f"  Model:       {effective_model['name']} ({effective_model['id']})")
            print(f"  Cost:        ${effective_model['input']}/M in, ${effective_model['output']}/M out")
            print(f"  Context:     {effective_model['ctx'] // 1000}K tokens")
            print(f"  Privacy:     {'🔒 private' if effective_model['private'] else '🔀 anonymized'}")
        return

    # ── Send prompt ──────────────────────────────────────────────────────
    if not args.prompt:
        # Read from stdin if no prompt flag
        if not sys.stdin.isatty():
            args.prompt = sys.stdin.read().strip()
        if not args.prompt:
            parser.print_help()
            sys.exit(1)

    api_key = os.environ.get("VENICE_API_KEY")
    if not api_key:
        print("❌ VENICE_API_KEY environment variable not set.", file=sys.stderr)
        print("   Get one at: https://venice.ai/settings/api", file=sys.stderr)
        sys.exit(1)

    # Determine model
    if args.model:
        model_id = args.model
        model_name = args.model
        tier_name = "custom"
    elif args.tier:
        tier_name = args.tier
        model_info = select_model(tier_name, prefer_private=not args.prefer_anon)
        model_id = model_info["id"]
        model_name = model_info["name"]
    else:
        tier_name = classify_complexity(args.prompt)
        max_tier = os.environ.get("VENICE_MAX_TIER")
        tier_name = get_effective_tier(tier_name, max_tier)
        model_info = select_model(tier_name, prefer_private=not args.prefer_anon)
        model_id = model_info["id"]
        model_name = model_info["name"]

    # Env defaults
    temperature = args.temperature or float(os.environ.get("VENICE_TEMPERATURE", "0.7"))
    max_tokens = args.max_tokens or int(os.environ.get("VENICE_MAX_TOKENS", "4096"))
    stream = args.stream or os.environ.get("VENICE_STREAM", "false").lower() == "true"

    # Build messages
    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": args.prompt})

    # Route info
    emoji = {"cheap": "💚", "budget": "💙", "mid": "💛", "high": "🧡", "premium": "💎", "custom": "⚙️"}
    print(f"🦞 Venice Router → {emoji.get(tier_name, '⚪')} {tier_name.upper()} → {model_name} ({model_id})", file=sys.stderr)

    # Call Venice API
    response = venice_chat(
        api_key=api_key,
        model_id=model_id,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=stream,
    )

    if response and not stream:
        print(response)


if __name__ == "__main__":
    main()
