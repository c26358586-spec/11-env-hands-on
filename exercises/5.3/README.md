<!--
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
-->

# 5.3 Go品質確認とBuild Artifact

5.2をcommit済みの状態へ、Go静的解析、Goアプリ単体テスト、build/package、jobごとの証跡Artifactを追加する。学習用のテスト`app/health_test.go`もこのstageで追加する。

## 適用手順

```bash
bash scripts/exercises/apply-learning-stage.sh --check 5.3
bash scripts/exercises/apply-learning-stage.sh 5.3
git diff --check
git diff
```

変更IssueとPull Requestの`target_version`は、root `VERSION`と同じ`0.0.0`を使用する。適用後は`static-analysis`、`unit-test`、`build-package`が増え、`build-go-app_<test-run-id>`と新たな3種類の証跡Artifactが生成されることを確認する。`environment-lifecycle`はまだ存在しない。

次の5.4へ進む前に、PR CI成功とBuild Artifactのchecksumを確認し、このstageをcommitする。

```bash
git apply -R exercises/5.3/patches/lesson.patch
```

復旧時は[トラブルシューティング](../../docs/troubleshooting/README.md)と[完成版参照](../../reference/completed/README.md)を比較に使う。
