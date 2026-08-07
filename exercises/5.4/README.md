<!--
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
-->

# 5.4 使い捨てUT環境ライフサイクル

5.3をcommit済みの状態へ`environment-lifecycle`を追加し、Build Artifactを再buildせず使い捨てUT環境面へ配置する。

## 適用手順

```bash
bash scripts/exercises/apply-learning-stage.sh --check 5.4
bash scripts/exercises/apply-learning-stage.sh 5.4
git diff --check
git diff
```

Terraform Docker Provider、Ubuntu 24.04 target container、Ansible、起動・疎通確認（readiness check）、cleanup前ログ退避、destroy、残存確認、environment evidenceが接続される。readiness checkは正式テスト開始の前提確認であり、正式インフラテストと正式APIテストはまだ接続されない。

上流失敗時にも`environment-lifecycle`が起動し、cleanup target 0、残存0件、`cleanup_state: Completed`を記録することを確認する。次の5.5へ進む前に、このstageをcommitする。

```bash
git apply -R exercises/5.4/patches/lesson.patch
```

復旧時は[トラブルシューティング](../../docs/troubleshooting/README.md)と[完成版参照](../../reference/completed/README.md)を確認する。
