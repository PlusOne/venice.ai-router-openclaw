---
name: venice-router
description: Supreme model router for Venice.ai — automatically classifies query complexity and routes to the cheapest adequate model tier. Supports all Venice.ai text models with cost-optimized tiered routing. Use when the user wants to chat via Venice.ai, send prompts through Venice, or needs smart model selection to minimize API costs.
homepage: https://venice.ai
user-invocable: true
metadata:
  { "openclaw": { "emoji": "🦞🚀", "requires": { "bins": ["python3"], "env": ["VENICE_API_KEY"] }, "primaryEnv": "VENICE_API_KEY" } }
---

# Venice.ai Supreme Router

Smart, cost-optimized model routing for Venice.ai. Classifies query complexity and routes to the cheapest model that can handle it well.

## Setup

1. Get a Venice.ai API key from [venice.ai/settings/api](https://venice.ai/settings/api)
2. Set the environment variable:

```bash
export VENICE_API_KEY="your-key-here"
```

Or configure in `~/.openclaw/openclaw.json`:

```json
{
  "skills": {
    "entries": {
      "venice-router": {
        "enabled": true,
        "apiKey": "YOUR_VENICE_API_KEY"
      }
    }
  }
}
```

## Usage

### Route a prompt (auto-selects model)

```bash
python3 {baseDir}/scripts/venice-router.py --prompt "What is 2+2?"
```

### Force a specific tier

```bash
python3 {baseDir}/scripts/venice-router.py --tier cheap --prompt "Tell me a joke"
python3 {baseDir}/scripts/venice-router.py --tier mid --prompt "Explain quantum computing"
python3 {baseDir}/scripts/venice-router.py --tier premium --prompt "Write a distributed systems architecture"
```

### Stream output

```bash
python3 {baseDir}/scripts/venice-router.py --stream --prompt "Write a poem about lobsters"
```

### Classify only (no API call)

```bash
python3 {baseDir}/scripts/venice-router.py --classify "Explain the Riemann hypothesis and its implications for prime number distribution"
```

### List available models and tiers

```bash
python3 {baseDir}/scripts/venice-router.py --list-models
```

### Override model directly

```bash
python3 {baseDir}/scripts/venice-router.py --model deepseek-v3.2 --prompt "Hello"
```

## Tiers

| Tier | Models | Cost (input/output per 1M tokens) | Best For |
|------|--------|-----------------------------------|----------|
| **cheap** | Venice Small (qwen3-4b), GLM 4.7 Flash, GPT OSS 120B, Llama 3.2 3B | $0.05–$0.15 / $0.15–$0.60 | Simple Q&A, greetings, math, lookups |
| **budget** | Qwen 3 235B, Venice Uncensored, GLM 4.7 Flash Heretic | $0.14–$0.20 / $0.75–$0.90 | Moderate questions, summaries, translations |
| **mid** | Grok Code Fast, DeepSeek V3.2, MiniMax M2.1/M2.5, Venice Medium, Llama 3.3 70B | $0.25–$0.70 / $1.00–$2.80 | Code generation, analysis, longer writing |
| **high** | GLM 5, Kimi K2 Thinking, Grok 4.1 Fast, Gemini 3 Flash | $0.50–$0.75 / $1.25–$3.75 | Complex reasoning, multi-step tasks, code review |
| **premium** | GPT-5.2, Gemini 3 Pro, Claude Opus 4.5/4.6, Claude Sonnet 4.5/4.6 | $2.19–$6.00 / $15.00–$30.00 | Expert-level analysis, architecture, research papers |

## Routing Strategy

The router classifies each prompt using keyword + heuristic analysis:

1. **Length** — longer prompts suggest more complex tasks
2. **Keywords** — domain-specific terms (e.g., "architecture", "optimize", "prove") signal complexity
3. **Code markers** — presence of code blocks, function names, or technical syntax
4. **Instruction depth** — multi-step instructions, comparisons, or "explain in detail" bump the tier
5. **Conversational simplicity** — greetings, yes/no, small talk stay on the cheapest tier

The classifier errs on the side of cheaper models — it only escalates when there's strong signal for complexity.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VENICE_API_KEY` | Venice.ai API key (required) | — |
| `VENICE_DEFAULT_TIER` | Default tier when classification is ambiguous | `budget` |
| `VENICE_MAX_TIER` | Maximum tier to ever use (cost cap) | `premium` |
| `VENICE_TEMPERATURE` | Default temperature | `0.7` |
| `VENICE_MAX_TOKENS` | Default max tokens | `4096` |
| `VENICE_STREAM` | Enable streaming by default | `false` |

## Tips

- Use `--classify` to preview which tier a prompt would hit before spending tokens
- Set `VENICE_MAX_TIER=mid` to cap costs and never hit premium models
- The router prefers **private** (self-hosted) Venice models over anonymized ones when available at the same tier
- Combine with OpenClaw WebChat for a seamless chat experience routed through Venice.ai
