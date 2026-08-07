<!--
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
-->

# トラブルシューティング

## 目的

受講者がCI失敗、品質ゲート失敗、Artifact不足、証跡不足を確認するときの入口を提供する。

## 確認できる項目

セクション5のPR CIについて、次の確認先を本書で扱う。

- `pr-ci-gate`が失敗した場合の確認順序
- JUnit XMLとJob Summaryの見方
- 証跡Artifactとevidence manifestの確認
- 証跡資源のTest run ID／workflow run ID確認
- Actions Artifactのupload時点からの`retention-days: 30`確認
- strict Required status checkでbranchが最新mainを取り込んでいない場合の確認
- Ruleset enforcement Active、空のBypass list、管理者bypassなしの確認
- VERSIONガバナンスチェック失敗時の確認先
- Terraform apply失敗時の確認先
- Ansible失敗時の確認先
- Testinfra/APIテスト失敗時の確認先
- Go単体テストは成功したがUT環境上でappが起動しない場合の確認先
- cleanup warningが出た場合の確認先
- 5.4以降の早期失敗時のcleanup対象0件と`cleanup_state: Completed`の確認
- 5.2から5.5の段階patchが適用できない場合の確認
- 5.6の期待失敗step不一致の確認
- 5.6 patch適用後の差分確認

Promotion Candidate Record、Promotion Record、Draft Release、Release Candidate登録、GHCR pushは、セクション5のPR CIでは扱わない。

## 段階patchを適用できない

5.2から5.5のpatchは、直前stageだけを入力にする。次の順で確認する。

1. `git status --short`でunstaged、staged、untrackedの変更がないことを確認する
2. `bash scripts/exercises/apply-learning-stage.sh --list`でstage順を確認する
3. `git log --oneline`で直前stageをcommit済みか確認する
4. `bash scripts/exercises/apply-learning-stage.sh --check <stage>`で適用可否を再確認する
5. 先のstageを飛ばしていないか、同じstageを二重適用していないか確認する

commit前の適用を戻す場合だけ、`git apply -R exercises/<stage>/patches/lesson.patch`を使用する。これは通常のNext stepsではなくRecoveryである。完成版を丸ごと上書きせず、`reference/completed/`から問題のある個別ファイルだけを比較する。5.6の`apply-failure-scenario.sh`は5.5完成後の異常系演習用であり、通常stageの復旧には使用しない。

## Issue入力不足

変更Issue本文に次が揃っているか確認する。

- `background`
- `change_summary`
- `acceptance_criteria`
- `affected_resources`
- `target_version`
- `required_final_stage`

Issue番号、Pull Request番号、Test run ID、Environment face ID、Build Artifact ID、candidate ID、candidate dispositionは受講者入力項目ではない。これらはGitHubまたはworkflowが生成する情報として確認する。

## Issue未関連付け

branch名にIssue番号が含まれているか、Pull Request本文に`Closes #<number>`があるかを確認する。Test run IDが`TR-UT-UNLINKED-...`になっている場合は、Issue番号を安全に確定できていない。governance-check failureの詳細を確認し、適当なIssue番号を補完しない。

## Test run ID不整合

次を確認する。

- Issue番号
- workflow run ID
- run attempt
- Test run ID形式

正常時は`TR-UT-ISSUE-<issue-number>-<workflow-run-id>-A<run-attempt>`、Issue未関連付け時は`TR-UT-UNLINKED-<workflow-run-id>-A<run-attempt>`である。

## 証跡不足

次を確認する。

- cleanup前ログ退避結果
- cleanup result
- evidence manifest
- `missing_evidence`
- Artifact upload結果

`environment-lifecycle`を接続した後は、静的解析、Go単体テスト、build-packageが失敗した場合でも通常skipされずに起動する。UT環境が作成されていなくてもcleanup対象0件としてcleanupと残存確認を記録し、`evidence-environment_<test-run-id>`を生成する。

cleanup後にdestroy log、cleanup warning、残存確認結果がmanifestへ追加されているか確認する。cleanup `NotAttempted`は許容可能なcleanup warningではなく、品質ゲートfailureである。cleanup対象0件、残存0件、`cleanup_state: Completed`であれば正常なcleanup完了である。cleanup不要を表す別状態は作らない。

## 証跡Artifactが見つからない

Job Summaryの証跡索引を確認する。期待するArtifact名は`evidence-governance_<test-run-id>`、`evidence-static-analysis_<test-run-id>`、`evidence-unit-test_<test-run-id>`、`evidence-build-package_<test-run-id>`、`evidence-environment_<test-run-id>`である。`evidence-build-package_<test-run-id>`は`build-package`が実行された場合だけ生成され、静的解析失敗またはGo単体テスト失敗で`build-package`がskippedの場合は生成されない。`evidence-environment_<test-run-id>`は早期失敗でも生成される。同じworkflow run attempt内で同名Artifactを複数回uploadする設計にはしない。

必須jobの証跡Artifact upload失敗は品質ゲートfailureである。対象jobのupload step、Artifact名、retention days、Test run ID、workflow run ID/run attemptを確認する。

environment証跡Artifact内の正式インフラ/APIテスト結果も確認する。

## Go静的解析が失敗した

`static-analysis` jobの`summary.md`、`static-analysis-result.json`、`logs/gofmt.log`、`logs/go-vet.log`を確認する。`gofmt`は自動整形しないため、`gofmt -l .`に表示されたファイルは手元で整形してから再実行する。このPR CIではTerraform / Ansible静的解析を実行しない。

## Go単体テストが失敗した

`unit-test` jobの`junit/go-unit.xml`、`logs/go-test.log`、`unit-test-result.json`を確認する。gotestsumが非0終了しても、取得できたJUnit XMLとログは証跡Artifactへ残す。Go単体テストはUT環境上のプロセス起動、port listen、Nginx経由疎通を確認するものではない。

## Build Artifactが見つからない

Build Artifact名は`build-go-app_<test-run-id>`である。これはPR CI内の一時名であり、Promotion / Releaseで使う正式Build Artifact名ではない。`build-package` jobがfailureまたはskippedの場合、Build Artifactは生成済み候補として扱わない。

`build-package`がVERSION不一致で失敗している場合は、変更Issueの`target_version`とルート`VERSION`を確認する。`target_version`に先頭`v`がある場合も、照合では`v`を除いた`X.Y.Z`として扱う。Build Artifact versionは`v<target_version>+b.<run-number>.a.<run-attempt>`形式で生成される。

Build Artifactには、少なくとも次が含まれる。

- `go-app-linux-amd64`
- `go-app-linux-amd64.sha256`
- `manifest.json`

`pr-ci-gate` SummaryでBuild Artifact名、Artifact ID、Build Artifact version、checksumが空でないか確認する。

## 証跡Checksumが見つからない

正常である。ハンズオン本線では証跡Artifact独自のchecksumを必須にしない。GitHubのplatform digestが取得できる場合は任意メタデータとして扱うが、取得できないことだけを理由に品質ゲートを失敗させない。

Build Artifactのchecksumとは用途が異なる。Build Artifact checksumは、PR CIでbuild/packageしたGoアプリbundleが変更または破損していないことを確認するために使う。

## Build Artifact checksum

`build-go-app_<test-run-id>`内のGoアプリbundle、Build Artifact manifest、`go-app-linux-amd64.sha256`、`pr-ci-gate` SummaryのBuild Artifact checksumを確認する。

## pr-ci-gateがskipまたは未完了

次を確認する。

- `if: always()`相当が設定されているか
- `needs`対象が実装済みjobだけになっているか
- workflow全体が強制キャンセルされていないか
- 必須jobやoutputがskipされていないか
- Required checkがsuccessになっていないこと

先行jobのfailure、cancelled、skippedによる通常の依存関係上のskipは`pr-ci-gate`で防ぐ。workflow全体が強制終了された場合は`pr-ci-gate`まで到達しない可能性があるが、その場合もsuccessにはならない。

## Go単体テストは成功したがUT環境上で起動しない

Go単体テストはrunner上でGoロジックを確認するものであり、UT環境上の配置やプロセス起動は確認しない。5.4のUT環境上の起動・疎通確認と5.5のインフラ/APIテストを確認する。

主な確認先は、Build Artifactから展開したbinary path、実行権限、Go process、期待port listen、direct HTTP、Nginx process/config/proxy_pass、Nginx経由HTTP、実行中app versionとBuild Artifact versionの一致である。

## environment-lifecycleが失敗した

`environment-lifecycle` Summaryと`evidence-environment_<test-run-id>`を確認する。主な確認順は次のとおり。

1. 上流job結果、Build Artifact名、Artifact ID、version、checksumが揃っているか確認する
2. `environment-lifecycle-result.json`の`prerequisites_met`、`upstream_ready`、`artifact_ready`を確認する
3. `logs/terraform-plan.log`、`logs/terraform-apply.log`でTerraform init、validate、plan、applyのどこで失敗したか確認する
4. `logs/ansible.log`でNginx構成またはGoアプリdeployの失敗を確認する
5. `logs/startup-connectivity-check.log`でbinary、PID、port、direct HTTP、Nginx経由HTTP、version一致のどれが失敗したか確認する
6. `logs/docker-state-before-cleanup.txt`、`logs/nginx.log`、`logs/go-app.log`でcleanup前の状態を確認する
7. `logs/terraform-destroy.log`、`logs/cleanup.log`、`logs/residue-verification.log`でcleanupと残存確認を確認する

上流前提不成立の場合は、Environment face IDが`NOT_CREATED`、`environment_creation_state: NotStarted`、`test_result: FailedBeforeTest`、`cleanup_target_count: 0`、`cleanup_state: Completed`になっていることを確認する。

Terraform fmt、init、validate、planで失敗した場合は、Environment face IDが生成済みでもTerraform apply前なのでTerraform管理資源は作成されていない。`cleanup_target_count: 0`、`remaining_resource_count: 0`、`cleanup_state: Completed`になっていることを確認する。Terraform destroy失敗warningが出る場合は、apply前失敗をdestroy対象ありとして扱っていないか確認する。

## インフラテストが失敗した

`environment-lifecycle`内でpytest + Testinfraの正式インフラテストを実行する。失敗時は次を確認する。

1. `manifest.json`の`infrastructure_test_execution_state`と`infrastructure_test_result`
2. `test-results/infrastructure-test-result.json`
3. `test-results/infrastructure-test-junit.xml`
4. `logs/infrastructure-test.log`
5. Docker container/network label、Nginx設定、Go app binary、process、port listen
6. cleanup log、residue verification log、`remaining_resource_count`

インフラテストが失敗した場合、APIテストは前提不成立としてskipされる。`api_test_result: Skipped`は正常系合格ではないため、`pr-ci-gate`はfailureになる。

## APIテストが失敗した

正式インフラテストが成功しているのにAPIテストが失敗した場合は、環境構成ではなくHTTP APIの振る舞いを中心に確認する。

1. `manifest.json`の`api_test_execution_state`と`api_test_result`
2. `test-results/api-test-result.json`
3. `test-results/api-test-junit.xml`
4. `logs/api-test.log`
5. `HOST_HTTP_URL`でNginx経由の`/health`へ到達できるか
6. `/health`のHTTP status、JSON body、Build Artifact version一致
7. 未対応methodや未定義pathのstatus

APIテスト失敗時も、cleanupと残存確認が実行され、environment evidenceがuploadされているか確認する。

## 正式テスト証跡が欠落している

`evidence-environment_<test-run-id>`の`manifest.json`で次を確認する。

- `expected_evidence`
- `collected_evidence`
- `missing_evidence`
- `missing_evidence_count`
- `environment_evidence_complete`
- `infrastructure_test_result_files`
- `api_test_result_files`

期待する正式テスト証跡は、`logs/infrastructure-test.log`、`logs/api-test.log`、`test-results/*-junit.xml`、`test-results/*-result.json`、`summaries/*-summary.md`である。skipや`FailedBeforeTest`の場合も、理由をJSON summaryとMarkdown summaryへ残す。placeholderは調査補助であり、証跡欠落を正常化するものではない。`missing_evidence_count`が1以上、または`environment_evidence_complete: false`の場合、テスト結果がPass/Failのどちらであっても`pr-ci-gate`はfailureになる。

## 5.6 scenario別確認

5.6の演習用patchは、正常な本線へ恒久的な不備を混入させず、演習用branchだけで失敗を発生させる。scenario定義は`exercises/5.6/scenarios.yml`、patchは`exercises/5.6/patches/`、適用入口は`scripts/exercises/apply-failure-scenario.sh`である。

scriptの確認順は次のとおり。

1. `bash scripts/exercises/apply-failure-scenario.sh --list`でscenario IDを確認する
2. `bash scripts/exercises/apply-failure-scenario.sh --dry-run <scenario-id>`でpatch適用可否を確認する。`--check`は互換aliasとして使用できる
3. `bash scripts/exercises/apply-failure-scenario.sh <scenario-id>`でpatchを適用する
4. `git diff`で`VERSION`更新と意図した不備だけが入っていることを確認する

`static-analysis-failure`では、`static-analysis` job、`summary.md`、`static-analysis-result.json`、`logs/gofmt.log`を確認する。`build-package`はskippedとなり、`environment-lifecycle`は環境未作成の早期失敗としてcleanup target 0、`cleanup_state: Completed`、environment evidence uploadを記録する。

`unit-test-failure`では、`unit-test` job、`junit/go-unit.xml`、`logs/go-test.log`、`unit-test-result.json`を確認する。Goアプリ単体テストはrunner上のGoロジックを検証するものであり、UT環境上のprocess、port、Nginx経由疎通とは分けて読む。

`infrastructure-test-failure`では、`environment-lifecycle` job内の正式インフラテスト結果を確認する。主な確認先は`logs/infrastructure-test.log`、`test-results/infrastructure-test-junit.xml`、`test-results/infrastructure-test-result.json`、`summaries/infrastructure-test-summary.md`、`manifest.json`である。正式インフラテストがFailedの場合、APIテストは`Skipped`になり得る。

`api-test-failure`では、正式インフラテストがPassedであることを先に確認し、そのうえで`logs/api-test.log`、`test-results/api-test-junit.xml`、`test-results/api-test-result.json`、`summaries/api-test-summary.md`、`manifest.json`を確認する。HTTP status、JSON body、未定義path、未対応methodのどれが期待と異なるかを見る。

`test-result-evidence-missing`では、正式テスト結果そのものではなく証跡完全性を確認する。`manifest.json`と`environment-lifecycle-result.json`で`missing_evidence`、`missing_evidence_count`、`environment_evidence_complete`を見る。`missing_evidence_count`が1以上、または`environment_evidence_complete: false`の場合、`pr-ci-gate`はfailureになる。

`pr-ci-gate` failure時は、個別jobが失敗しているのか、正式テスト結果が不合格なのか、証跡Artifact uploadやmanifest完全性が不備なのかを分けて読む。`pr-ci-gate`は再テストを実行せず、先行job結果、必須output、Artifact upload、正式テスト結果、cleanup state、残存0件、証跡完全性を集約するだけである。

### 5.6 復旧後のVERSION不一致

復旧時はscenario patch全体を戻さず、`recovery_method`に従って注入した不備だけを修正する。patch全体を戻すと`VERSION`も`0.0.0`へ戻るため、標準の復旧手順には使用しない。

次の3つがすべて`0.0.1`で一致することを確認する。

1. scenario専用Issueの`target_version`
2. scenario Pull Requestの`target_version`
3. リポジトリルートの`VERSION`

`VERSION`が`0.0.0`へ戻っていた場合は`0.0.1`へ直し、scenarioで注入した不備以外の差分がないことを`git diff`で確認してからcommit、pushする。

演習用PRは、修正後に`pr-ci-gate`がsuccessになってもmainへmergeしない。演習完了コメントをIssueへ残し、Pull RequestとIssueを手動closeする。最後にremoteとlocalのscenario branchを削除し、次のscenarioは正常なmainから開始する。

## 残存リソースがある

`pr-ci-gate`は`remaining_resource_count: 0`を要求する。cleanup warningだけなら`CompletedWithWarning`として許容できるが、残存リソースが1件以上ある場合は品質ゲートfailureである。

確認する項目は次のとおり。

1. `logs/cleanup.log`
2. `logs/residue-verification.log`
3. `logs/docker-state-before-cleanup.txt`
4. `logs/docker-state-after-cleanup.txt`
5. `manifest.json`の`remaining_resource_identifiers`

cleanup対象外のDocker資源を削除していないこと、管理対象labelに基づいて削除していることも確認する。

## 5.6 Issue不整合

scenarioごとに変更Issueを作成しているか確認する。Issue本文には`background`、`change_summary`、`acceptance_criteria`、`affected_resources`、scenario定義の`target_version`、`required_final_stage: UT`が必要である。

branch名にIssue番号が含まれ、Pull Request本文に`Closes #<Issue番号>`があるか確認する。修正後に`pr-ci-gate`が成功しても教材演習用Pull Requestはmainへmergeせずcloseし、対応Issueへ演習完了コメントを追加して手動closeする。Pull RequestとIssueのclose後にscenario branchを削除する。

scenario定義では`expected_failure_job`と`expected_failure_step`を分ける。必須scenarioでは、`static-analysis-failure`は`static-analysis/app-lint`、`unit-test-failure`は`unit-test/go-unit-test`、`infrastructure-test-failure`は`environment-lifecycle/infrastructure-test`、`api-test-failure`は`environment-lifecycle/api-test`、`test-result-evidence-missing`は`pr-ci-gate/evidence-completeness`で確認する。期待と異なるstepが先に失敗している場合は、patch内容または前提条件の不備として確認する。

## 注意

本書はPR CI、Artifact、environment evidence、品質ゲート、5.6異常系演習の確認入口である。Promotion / Release系の処理はセクション5のPR CIでは扱わない。
