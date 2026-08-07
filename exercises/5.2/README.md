<!--
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
-->

# 5.2 最小PR CI

公開スターターのworkflowは手動確認専用で、Pull Requestでは起動しない。このstageでは`governance-check`、Test run ID、governance証跡、Job Summary、`pr-ci-gate`だけを追加する。

## 適用手順

1. 変更Issueを作成し、`target_version: 0.0.0`と`required_final_stage: UT`を確認する。
2. Issue番号を含むbranchを作成する。Draft Pull Requestはpatch適用後に作成する。
3. 次を実行する。

```bash
bash scripts/exercises/apply-learning-stage.sh --check 5.2
bash scripts/exercises/apply-learning-stage.sh 5.2
git diff --check
git diff
```

4. workflowに`governance-check`と`pr-ci-gate`だけがあることを確認する。
5. stageをcommitしてからDraft Pull Requestを作成する。
6. `evidence-governance_<test-run-id>`とJob Summaryを確認する。

次の5.3へ進む条件は、`governance-check`と`pr-ci-gate`がsuccessで、RulesetのRequired status checkへ`pr-ci-gate`を登録できていることである。

適用前へ戻す場合は、commit前に次を実行する。

```bash
git apply -R exercises/5.2/patches/lesson.patch
```

patchが適用できない場合は[トラブルシューティング](../../docs/troubleshooting/README.md)を確認する。完成状態との比較には[完成版参照](../../reference/completed/README.md)を使用できるが、一括copyは行わない。
