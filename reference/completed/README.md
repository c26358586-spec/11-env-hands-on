<!--
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
-->

# 完成版参照

このディレクトリは、5.5完了時点のファイルを比較、復旧、最終確認するための非アクティブな参照資源である。演習の本線は5.2から5.5のpatchを順番に適用し、各stageの差分と役割を確認する。

workflowは`workflows/pr-ci.yml`に配置しているため、この参照資源からGitHub Actionsが自動起動することはない。rootのアクティブな`.github/workflows/pr-ci.yml`と比較する場合は、次を使用できる。

```bash
git diff --no-index .github/workflows/pr-ci.yml reference/completed/workflows/pr-ci.yml
```

`manifest.yml`には、rootのsource path、参照path、SHA-256を記録している。参照資源の一括copyを通常の演習手順にはしない。patch適用に失敗したファイルや、自分の変更との差分を限定して確認するときに使用する。

5.5の確認では、次を重点的に比較する。

- `workflows/pr-ci.yml`: 最終job集合と`pr-ci-gate`の集約
- `scripts/pr-ci/`: governance、品質確認、環境ライフサイクル、品質ゲート
- `app/`: GoアプリとGoアプリ単体テスト
- `terraform/`、`ansible/`、`images/target/`: UT環境面と構成・デプロイ
- `tests/infrastructure/`、`tests/api/`、`tests/testcases/`: 正式テストとテスト観点

参照資源に実行結果、cache、Artifact実体、credential、secretは含めない。
