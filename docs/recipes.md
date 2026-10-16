# Check recipes

A check is one shell command that exits non-zero while the break is real and 0 once it is fixed.
It runs from the register's folder. Copy one, fill in the `<placeholders>`, and pass it to
`broken_rules.py file --check '...'`.

Two habits make checks trustworthy:

- **Test the outcome, not the intent.** Check the file, the commit or the setting the rule is
  about. "The agent promised to stop" is not checkable; "the file no longer contains X" is.
- **Guard a negation.** `! grep -q X file` passes when the file is missing, because grep's error
  exit (2) is negated too. Write `test -f file && ! grep -q X file`. The same goes for pipes:
  `! git log | grep X` passes outside a git repo, so check that git works first.

## Commits

No AI co-author trailer in the last 50 commits:

```sh
git rev-parse -q --verify HEAD >/dev/null && ! git log -50 --format=%B | grep -Eqi '^co-authored-by:.*(claude|copilot|cursor|codex|gemini|gpt|anthropic|openai|devin|aider)'
```

Commit subjects stay within 72 characters:

```sh
git rev-parse -q --verify HEAD >/dev/null && git log -50 --format=%s | awk 'length > 72 { bad = 1 } END { exit bad }'
```

Conventional commit subjects (`type(scope): what changed`) in the last 20 commits:

```sh
git rev-parse -q --verify HEAD >/dev/null && ! git log -20 --no-merges --format=%s | grep -Ev '^(feat|fix|docs|chore|refactor|test|perf|build|ci|style|revert)(\([^)]+\))?!?: '
```

A commit-msg hook is installed, either in `.git/hooks` or through `core.hooksPath`:

```sh
test -x .git/hooks/commit-msg || test -x "$(git config core.hooksPath)/commit-msg"
```

Main's history was not rewritten (no force push) since a known commit:

```sh
git fetch -q origin && git merge-base --is-ancestor <commit on main> origin/main
```

## Secrets

No private key or AWS access key in tracked files:

```sh
git rev-parse -q --verify HEAD >/dev/null && ! git grep -qE -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' -e 'AKIA[0-9A-Z]{16}'
```

## Files and settings

A skill that publishes or sends anything cannot be started by the model on its own:

```sh
grep -q '^disable-model-invocation: true$' <path/to/SKILL.md>
```

A banned command is gone from a file:

```sh
test -f <file> && ! grep -q '<banned command>' <file>
```

A required line is present, for example a safety line in an agent definition:

```sh
grep -qi '<required phrase>' <file>
```

## Output

A job's output is fresh: a file in the folder changed within the last 2 days:

```sh
find <folder> -name '*.md' -mtime -2 | grep -q .
```

The tests pass:

```sh
<your test command>
```
