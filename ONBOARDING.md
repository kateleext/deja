# Onboarding Déjà

You just cloned the skill. Now walk the user through setup.

**Follow every step. Do not skip any.**

## Step 1: Create Symlink

Explain:

> I'll create a symlink so I can run `deja` instead of the full path `~/.claude/skills/memory/deja`. This makes the command accessible from anywhere and keeps the output cleaner when you see me using it. Want me to set this up?

If yes:
```bash
mkdir -p ~/.local/bin
ln -sf ~/.claude/skills/memory/deja ~/.local/bin/deja
```

## Step 2: Add Permission

Ask if they want uninterrupted access. Add `"Bash(deja *)"` to the `permissions.allow` array in `~/.claude/settings.json`.

## Step 3: Demonstrate

**You must do this. Do not skip.**

Run `deja --limit 5` and show the user their real history.

Pick a session with interesting content and read into it:
```bash
deja <session_id>
deja <session_id>:1
```

Share something real you found:

> I can see you were working on [specific thing] recently. You mentioned [real detail from their history].

## Step 4: Recommend Retention

Claude Code deletes sessions older than 30 days by default. For Déjà to be useful long-term:

> **Important**: By default, Claude Code deletes conversation history older than 30 days. I recommend adding this to your `~/.claude/settings.json`:
>
> ```json
> "cleanupPeriodDays": 1000
> ```
>
> This keeps about 3 years of history. Want me to add it now?

If they agree, add `"cleanupPeriodDays": 1000` to their settings file.

## Step 5: Finish

Say:

> Déjà is installed. I found [X] sessions in your history. From now on, when you reference past work, I can look it up.

**Do not list commands. The user never runs them—you do.**
