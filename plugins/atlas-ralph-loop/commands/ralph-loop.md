---
description: "Start Ralph Loop in current session"
argument-hint: "PROMPT [--max-iterations N] [--completion-promise TEXT]"
allowed-tools: ["Bash(bash *setup-ralph-loop.sh*)"]
hide-from-slash-command-tool: "true"
---

# Ralph Loop Command

Initialize the Ralph loop by running the setup script with the Bash tool.

IMPORTANT: The prompt text MUST be wrapped in double quotes to protect special characters (apostrophes, backticks, etc). Flags go OUTSIDE the quoted prompt.

Example:
```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup-ralph-loop.sh" "the prompt text goes here" --completion-promise "DONE" --max-iterations 20
```

Now run the command with the user's arguments. Quote the prompt portion in double quotes:
```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup-ralph-loop.sh" $ARGUMENTS
```

Please work on the task. When you try to exit, the Ralph loop will feed the SAME PROMPT back to you for the next iteration. You'll see your previous work in files and git history, allowing you to iterate and improve.

CRITICAL RULE: If a completion promise is set, you may ONLY output it when the statement is completely and unequivocally TRUE. Do not output false promises to escape the loop, even if you think you're stuck or should exit for other reasons.

TERMINATION PROTOCOL: When genuinely complete, signal completion via EITHER method:
1. Write the promise word to `.claude/ralph-done` using the Write tool (most reliable — position-independent)
2. Output `<promise>WORD</promise>` as the ABSOLUTE LAST line of your response — no tool calls or text after it

Method 1 (file write) is preferred because it works regardless of what you do after. Method 2 requires strict discipline about outputting nothing afterward. Using both is ideal (belt and suspenders).
