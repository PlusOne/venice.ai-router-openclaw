# 🦞🚀 Venice.ai Router for OpenClaw

A cost-optimized model routing skill for [OpenClaw](https://github.com/PlusOne/openclaw) that automatically selects the cheapest [Venice.ai](https://venice.ai) model capable of handling your query.

Instead of always hitting expensive models, the router classifies each prompt's complexity and routes it to an appropriate tier — saving up to **99%** on simple queries compared to always using premium models.

## How It Works

```
User prompt → Complexity Classifier → Tier Selection → Venice.ai API
                                          │
              ┌───────────┬───────────┬───┴───────┬───────────┐
            CHEAP      BUDGET       MID        HIGH      PREMIUM
           $0.05/M    $0.15/M    $0.25/M    $0.50/M     $2.19/M
```

The classifier uses heuristic analysis:

- **Length** — longer prompts suggest more complex tasks
- **Keywords** — domain-specific terms signal complexity (e.g., "architecture", "prove", "optimize")
- **Code markers** — code blocks, function names, technical syntax
- **Instruction depth** — multi-step instructions, comparisons
- **Conversational simplicity** — greetings and small talk stay cheap

## Model Tiers

| Tier | Models | Input Cost | Best For |
|------|--------|-----------|----------|
| **💚 Cheap** | Venice Small, GPT OSS 120B, GLM 4.7 Flash, Llama 3.2 3B | $0.05–$0.15/M | Simple Q&A, greetings, math |
| **💙 Budget** | Qwen 3 235B, Venice Uncensored, GLM 4.7 Flash Heretic | $0.14–$0.25/M | Summaries, translations |
| **💛 Mid** | DeepSeek V3.2, MiniMax M2.1/M2.5, Llama 3.3 70B | $0.25–$0.70/M | Code generation, analysis |
| **🧡 High** | GLM 5, Kimi K2 Thinking, Grok 4.1 Fast, Gemini 3 Flash | $0.50–$1.00/M | Complex reasoning, code review |
| **💎 Premium** | GPT-5.2, Gemini 3 Pro, Claude Opus/Sonnet 4.5/4.6 | $2.19–$6.00/M | Expert analysis, architecture |

Full model pricing in [references/models.md](references/models.md).

## Requirements

- **Python 3.8+** (no external dependencies — stdlib only)
- **Venice.ai API key** — get one at [venice.ai/settings/api](https://venice.ai/settings/api)
- **OpenClaw** (optional — works standalone too)

## Installation

### Quick Install (OpenClaw)

```bash
git clone git@github.com:PlusOne/venice.ai-router-openclaw.git
cd venice.ai-router-openclaw
chmod +x install.sh
./install.sh
```

The installer auto-detects your OpenClaw workspace and copies the skill files.

Then enable in `~/.openclaw/openclaw.json`:

```json
{
  "env": {
    "VENICE_API_KEY": "your-api-key-here"
  },
  "skills": {
    "entries": {
      "venice-router": {
        "enabled": true
      }
    }
  }
}
```

Restart the gateway or wait for auto-reload (if `skills.load.watch` is enabled).

### Manual Install

Copy the files to your OpenClaw skills directory:

```bash
mkdir -p ~/.openclaw/workspace/skills/venice-router
cp -r SKILL.md scripts/ references/ ~/.openclaw/workspace/skills/venice-router/
```

### Standalone (without OpenClaw)

```bash
export VENICE_API_KEY="your-api-key-here"
python3 scripts/venice-router.py --prompt "Hello world"
```

## Usage

### Via OpenClaw WebChat / Telegram

Type `/venice_router` followed by your prompt:

```
/venice_router What is the capital of France?
```

### CLI — Auto-Routed Prompt

```bash
python3 scripts/venice-router.py --prompt "What is 2+2?"
# → 💚 CHEAP → Venice Small

python3 scripts/venice-router.py --prompt "Write a Python async web scraper with error handling"
# → 💛 MID → DeepSeek V3.2

python3 scripts/venice-router.py --prompt "Design a distributed event-driven microservices architecture"
# → 💎 PREMIUM → Gemini 3 Pro
```

### CLI — Force a Tier

```bash
python3 scripts/venice-router.py --tier mid --prompt "Tell me a joke"
```

### CLI — Stream Output

```bash
python3 scripts/venice-router.py --stream --prompt "Write a poem about lobsters"
```

### CLI — Classify Only (No API Call)

```bash
python3 scripts/venice-router.py --classify "Explain quantum entanglement"
# → 💛 MID → DeepSeek V3.2
```

### CLI — List All Models

```bash
python3 scripts/venice-router.py --list-models
```

### CLI — Override Model Directly

```bash
python3 scripts/venice-router.py --model deepseek-v3.2 --prompt "Hello"
```

### CLI — JSON Output

```bash
python3 scripts/venice-router.py --classify "Design a system" --json
```

```json
{
  "classified_tier": "premium",
  "effective_tier": "premium",
  "model_id": "gemini-3-pro-preview",
  "model_name": "Gemini 3 Pro",
  "input_cost_per_1m": 2.5,
  "output_cost_per_1m": 15.0,
  "context_window": 198000,
  "private": false,
  "prompt_length": 15
}
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VENICE_API_KEY` | Venice.ai API key **(required)** | — |
| `VENICE_DEFAULT_TIER` | Default tier when classification is ambiguous | `budget` |
| `VENICE_MAX_TIER` | Maximum tier to use (cost cap) | `premium` |
| `VENICE_TEMPERATURE` | Default temperature | `0.7` |
| `VENICE_MAX_TOKENS` | Default max tokens | `4096` |
| `VENICE_STREAM` | Enable streaming by default | `false` |

### Cost Control

Cap your spending by setting `VENICE_MAX_TIER`:

```bash
export VENICE_MAX_TIER=mid  # Never use high or premium models
```

### Privacy

The router prefers **private** (self-hosted) Venice models over anonymized ones when available at the same tier:

- **🔒 Private** — Venice hosts the model directly, data stays within Venice infrastructure
- **🔀 Anonymized** — request proxied to external provider (OpenAI, Anthropic, Google, xAI) with identity stripped

Use `--prefer-anon` to override this behavior.

## CLI Reference

```
usage: venice-router.py [-h] [--prompt PROMPT] [--tier {cheap,budget,mid,high,premium}]
                        [--model MODEL] [--classify CLASSIFY] [--list-models]
                        [--stream] [--temperature TEMP] [--max-tokens N]
                        [--system SYSTEM] [--prefer-anon] [--json]

Options:
  --prompt, -p       Prompt to send to Venice.ai
  --tier, -t         Force a specific tier (cheap|budget|mid|high|premium)
  --model, -m        Force a specific model ID
  --classify, -c     Classify complexity without calling the API
  --list-models, -l  List all model tiers and pricing
  --stream, -s       Enable streaming output
  --temperature      Temperature (0.0–2.0)
  --max-tokens       Max output tokens
  --system           System prompt
  --prefer-anon      Prefer anonymized over private models
  --json, -j         Output routing info as JSON
```

## Project Structure

```
venice.ai-router-openclaw/
├── README.md              ← You are here
├── SKILL.md               ← OpenClaw skill definition (AgentSkills format)
├── install.sh             ← Auto-installer for OpenClaw
├── scripts/
│   ├── venice-router.py   ← Core router engine (Python 3, stdlib only)
│   └── venice-router.sh   ← Bash wrapper
└── references/
    └── models.md          ← Full Venice.ai model pricing reference
```

## License

MIT License — see [LICENSE](LICENSE).

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -am 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

## Links

- [Venice.ai](https://venice.ai) — AI inference platform
- [Venice.ai API Docs](https://docs.venice.ai) — API reference
- [OpenClaw](https://github.com/PlusOne/openclaw) — Personal AI assistant
