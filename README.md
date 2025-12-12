# Déjà

Episodic memory for Claude Code.

## The Idea

Your conversation history already exists on disk. Déjà lets Claude access it.

No more broken telephone - agents documenting while dying, passing notes to the next one who does the same. Instead, Claude reaches back and recalls what you actually said when the situation calls for it.

Sessions become episodes, todos become structure. Start fresh freely. The past is there when context demands it.

Paste into Claude Code:

> Hey Claude, load the Déjà skill from https://github.com/kateleext/deja

## Installation

Clone to your skills directory:

```bash
gh repo clone kateleext/deja ~/.claude/skills/memory
```

Then read `~/.claude/skills/memory/ONBOARDING.md` and follow every step.

The skill loads as `memory` - more intuitive for the agent than the brand name.

## How It Works

Your todos become episodes. Every time you use TodoWrite and complete tasks, those become navigable structure in your history. The more you use todos, the more your memory organizes itself.

Search indexes everything: user messages, assistant responses, todos, files touched, commands run. Results rank by signal strength then recency. Signal weighs todos > files > text, boosted by match breadth (finding more of your words beats finding one word repeatedly).

Reading sessions shows both sides of the conversation, but **truncates long assistant responses** by default. Use `--full` for complete content, or fetch a specific message directly.

Under the hood, the skill gives Claude a CLI:

```
deja                        # Recent sessions
deja "query"                # Search sessions
deja <session>              # Session overview (episodes, todos, work)
deja <session>:2            # Read episode 2
deja <session>@3            # Read around turn 3
deja <session>.15           # Get message 15
deja <session> +note "..."  # Leave a breadcrumb
deja --help                 # Usage reference
```

Partial session IDs work. Ambiguous IDs show matching sessions to choose from.

## Customizing

The skill description controls when Claude reaches for memory. Edit `SKILL.md` if Claude isn't using it enough (make it more aggressive) or uses it too often (make it narrower). Current triggers: "we discussed," "remember when," "last time," "why did we," "continue from."

## Privacy

All data stays on your machine. Read-only access to conversation files.

## License

MIT
