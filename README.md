# atlas-plugins

Claude Code plugin marketplace by [Atlas-X-AI](https://github.com/Atlas-X-AI).

Hardened, tested plugins for AI-driven operations.

## Plugins

| Plugin | Description | Status |
|--------|-------------|--------|
| [atlas-ralph-loop](plugins/atlas-ralph-loop/) | Hardened Ralph Loop with reliable termination | Stable |

## Installation

Add this marketplace to your Claude Code:

```bash
# Claude Code will prompt to add it, or manually add to ~/.claude/plugins/known_marketplaces.json:
{
  "atlas-plugins": {
    "source": {
      "source": "github",
      "repo": "Atlas-X-AI/atlas-plugins"
    }
  }
}
```

Then enable plugins in Claude Code settings.

## Contributing

All plugins must have:
- Regression test suite
- No stubs or placeholder code
- Documented termination/exit conditions
