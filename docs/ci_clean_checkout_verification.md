# Clean-checkout verification

A green test run from a dirty working tree is not evidence that a checkpoint
contains all of its runtime, test, fixture, or data dependencies. Checkpoint,
release, and `main` push verification must run from committed content only.

Use a temporary worktree at the candidate commit, outside the primary working
tree, and run at least:

```powershell
git -c core.longpaths=true worktree add --detach <temporary-path> <candidate-sha>
Push-Location <temporary-path>
py -m pytest --collect-only
py -m pytest
Pop-Location
git worktree remove <temporary-path>
```

The temporary path is verification state, not Engineering Knowledge evidence.
