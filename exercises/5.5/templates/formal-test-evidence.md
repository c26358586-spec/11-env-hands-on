<!--
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
-->

# 5.5 比較ポイント

```text
formal infrastructure test
  -> INF-001 ... INF-009
  -> log + JUnit XML + JSON result + Markdown summary
formal API test
  -> API-001 ... API-004
  -> log + JUnit XML + JSON result + Markdown summary
environment evidence
  -> manifest.json
  -> environment-lifecycle-result.json
  -> missing_evidence_count
  -> environment_evidence_complete
  -> cleanup_state
  -> remaining_resource_count
pr-ci-gate
  -> Job Summary
```

正式テストケースの詳細、automation function、前提、期待結果、skip条件は`tests/testcases/README.md`で確認する。正常なLesson 5.5のPR CIでは13件すべてを実行対象とし、`API-004`だけは`TARGET_CONTAINER_NAME`がない場合にskipする。

5.4の起動・疎通確認は正式テスト開始前のreadiness checkであり、正式テストではない。5.5でprocess、port、Nginx経由`/health`、versionを再確認するのは、受入・回帰証跡をcase単位で残すためである。テスト合格と証跡完全性は別々に確認する。
