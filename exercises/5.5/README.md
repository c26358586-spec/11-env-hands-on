<!--
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
-->

# 5.5 正式テストと証跡完全性

5.4をcommit済みの状態へ正式インフラテストと正式APIテストを追加し、PR CIを完成状態にする。

## 適用手順

```bash
bash scripts/exercises/apply-learning-stage.sh --check 5.5
bash scripts/exercises/apply-learning-stage.sh 5.5
git diff --check
git diff
```

pytest + Testinfra、pytest + requests、test log、JUnit XML、JSON result、Markdown summaryを確認する。environment evidence manifestの`missing_evidence_count: 0`、`environment_evidence_complete: true`、cleanup state、`remaining_resource_count: 0`を`pr-ci-gate`が集約する。

PR CI成功後、[完成版参照](../../reference/completed/README.md)との比較で不足ファイルがないことを確認してこのstageをcommitする。5.6はこの完成状態から開始する。

```bash
git apply -R exercises/5.5/patches/lesson.patch
```

証跡不足やテスト失敗は[トラブルシューティング](../../docs/troubleshooting/README.md)を確認する。
