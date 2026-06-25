# Git 操作规则
> 🔴 Must | 每次 git 操作前过一遍

## 提交
- 不 amend 已推送的 commit
- 不 `--no-verify` / `--no-gpg-sign` / `-c commit.gpgsign=false` — hook 挂了修 hook
- commit message 结尾加 `Co-Authored-By: Claude <noreply@anthropic.com>`
- 在默认分支上改代码之前先切分支

## 推送
- 不 `--force` 推默认分支
- 推之前确认在正确的分支上

## 回滚
- `git reset --hard` / `git checkout --` → 先确认有没有更安全的替代
- 能 `git revert` 不 `git reset --hard origin/main`

## 快照
- 每次 session 结束自动 git snapshot（SessionEnd hook）
- 大的改动前手动 `git add -A && git commit -m "snapshot: <what>"`
