# atlas-go

Zero-config goal-to-tasks engine for Claude Code. Takes any goal, runs adaptive discovery, generates a validated spec, parses tasks, and executes with CDD verification.

## Install

```bash
npm install -g atlas-go
```

Requires `task-master-ai` installed globally (peer dependency):

```bash
npm install -g task-master-ai
```

## Usage

In any Claude Code session:

```
/atlas-go:go
```

Claude will guide you through the 5-phase pipeline: SETUP → DISCOVER → GENERATE → HANDOFF → EXECUTE.

## Customize

After HANDOFF, edit files in `.atlas-ai/customizations/` to inject your own rules, system prompts, and verification preferences. See `.atlas-ai/customizations/README.md`.

## Pipeline

```
goal → discovery → spec → tasks → plan → execute → verify → done
```

## License

MIT
