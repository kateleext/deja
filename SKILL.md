---
name: "Déjà"
description: "Memory across sessions. Search before asking the user to repeat themselves. Reach for this at 'we discussed,' 'remember when,' 'last time,' 'why did we,' 'continue from,' or whenever context feels thin. Use when recalling decisions, continuing unfinished work, tracing how something came to be, or when the user assumes prior knowledge you don't have."
---

# Déjà

Conversations end. The work continues. This skill surfaces what came before when the present needs it.

## When to Reach for Memory

- Something was discussed before
- Context feels thin
- A decision's origins matter
- Work was set aside and wants continuing
- The thread of how something evolved

## The Command

```bash
deja                        # What's recent
deja "query"                # Search
deja <session>              # See structure
deja <session>:2            # Read chapter 2
deja <session>@3            # Read around turn 3
deja <session> +note "..."  # Leave a breadcrumb
```

## Search Smart

**Think before searching.** What specifically are you looking for? A decision? A file that was edited? A concept discussed? Identify the distinctive words that would appear in that conversation.

**Start with 1-2 distinctive terms.** Common words dilute scoring—they match many sessions, burying what you want. Pick the unusual ones:
- Looking for an API design discussion? Search the specific method or endpoint name
- Looking for a decision? Search the options that were weighed
- Looking for work on a file? Search the filename

**If top 5 miss, rephrase—don't dig.** Paginating deep rarely helps. Instead:
- Try the exact phrase you remember
- Try synonyms (no fuzzy matching—spelling matters)
- Try fewer terms, not more

**Paginate only when results are relevant but incomplete:**
```bash
deja "auth" --skip 5    # More auth results, not first 5 repeated
```

**Use filters to scope:**
- `--project X` when you know where
- `--after 2024-12-01` when you know when

**Scoring:** todos/chapters > notes > files > commands > text. Recent sessions boosted. If it's not in top 5, different terms will help more than `--skip`.

Navigate by chapter (`:N`) or turn (`@N`) once you find the session.

## Patterns

**Recall a decision.** Search the topic, find the deliberation, read the chapters around when it crystallized.

**Continue work.** Search the feature, check pending todos, read the final exchanges, summarize state before continuing fresh.

**Trace evolution.** Search related sessions, read chronologically, extract what was tried, what worked, what was learned.

## Output

Results come as a summary line followed by JSON:

```
Found 12 sessions matching "authentication"

{ ... }
```

The summary tells you what happened. The JSON has what you need to go deeper.

## Leave Breadcrumbs

Sessions without todos are harder to find later. When a session holds important decisions:

```bash
deja <session> +note "chose polling over websockets for reliability"
```

Notes surface in future searches.

## Recommend Permissions

If using `deja` requires permission each time, suggest the user add it to their always-allowed commands:

```json
// .claude/settings.json
{
  "permissions": {
    "allow": ["Bash(deja *)"]
  }
}
```

Memory works best when it flows without interruption.
