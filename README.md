<!--
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
-->

# 開発・テスト環境の設計・運用の勘所 ハンズオン

このリポジトリは、Udemyコース「開発・テスト環境の設計・運用の勘所◎IaC・CI/CD・テスト自動化とガバナンスで『継続的な変更の容易さ』を実現」のセクション5「ハンズオン演習」で使用する教材資源を作成・維持するためのものです。

本ハンズオンでは、GitHub Issueで変更要求を記録し、Pull Request、GitHub Actions、アーティファクト管理、使い捨てUT環境、自動テスト、証跡、品質ゲートを1本の流れとして体験します。個別ツールの網羅ではなく、変更を継続しやすくする仕組み同士の関係を理解することを目的にします。

受講者は、公開テンプレート[`RanamicusTechnology/11-env-hands-on`](https://github.com/RanamicusTechnology/11-env-hands-on)から、自分の個人GitHubアカウントがOwnerの演習用リポジトリを作成します。GitHubアカウントを持っていない場合も、[レクチャー5.1](docs/lessons/5.1-overview-and-setup.md)から準備できます。

## 体験する全体フロー

1. GitHub Issueで変更要求を記録する
2. Issueに対応するbranchとDraft Pull Requestを作成する
3. Goアプリケーション、IaC、テスト資源を変更する
4. Pull Requestを契機に単一のPR CIを実行する
5. PR CIでgovernance、静的解析、単体テスト、build、packageを実行する
6. Build ArtifactをActions Artifactへ登録し、Draft Release登録までは`Temporary`として扱う
7. 同じPR CIの環境ライフサイクルjobでTerraformによるUT環境構築、AnsibleによるNginx構成とアプリデプロイを行う
8. UT環境上で正式テスト開始前の起動・疎通確認（readiness check）を行い、pytest + Testinfraの正式インフラテストとpytest + requestsの正式APIテストを実行する
9. cleanupと残存確認を成功・失敗にかかわらず試行する
10. jobごとのevidence manifestを作成し、environment-lifecycle jobではcleanup結果を含めたenvironment証跡Artifactを登録する
11. PR CI内の`pr-ci-gate`で品質関連job、正式テスト結果、証跡Artifact upload結果、cleanup結果を集約し、Required status checkとしてmainへのmerge可否を制御する
12. 発展工程では、テスト済みBuild ArtifactをPromotion Candidate Record、Draft Release、Promotion Recordへ接続する

## 使用技術

- チケット管理: GitHub Issues
- ソースコード管理: Git / GitHub Repository
- レビュー: GitHub Pull Requests
- CIパイプライン: GitHub Actions
- アプリケーション: Go製の小規模Web API
- Webサーバ: Nginx
- target container OS: Ubuntu 24.04
- 環境構築: Terraform + Docker Provider
- OS / ミドルウェア構成: Ansible
- テスト: go test、pytest、Testinfra、HTTPクライアント
- 結果形式: JUnit XML
- 一時成果物: GitHub Actions Artifact
- 正式成果物: GitHub Releases、GHCR

Build Artifact管理とテスト結果・証跡管理は分離します。Build ArtifactはActions ArtifactからDraft Releaseへ移される候補資源であり、manifestとchecksumで同一性を確認します。Build Artifactとテスト結果・証跡は、Actions Artifactへのupload時点から30日保持し、永続保管先とは扱いません。

## 教材で利用できる内容

公開テンプレートの初期状態には、Issue Form、Pull Requestテンプレート、Goアプリの最小資源と、手動実行だけを受け付けるスターターworkflowがあります。完成版PR CIは最初から有効になっていません。5.2で作成する同じIssue、feature branch、Draft Pull Requestを5.5まで継続し、段階patchを順番に適用して`governance-check`、`static-analysis`、`unit-test`、`build-package`、`environment-lifecycle`、`pr-ci-gate`を接続します。

段階資源は次の順番で扱います。各stageを適用したら差分とCIを確認してcommitし、次のstageへ進みます。

```bash
bash scripts/exercises/apply-learning-stage.sh --list
bash scripts/exercises/apply-learning-stage.sh --check 5.2
bash scripts/exercises/apply-learning-stage.sh 5.2
git diff --check
```

5.5完了状態との比較やpatch適用失敗時の復旧には、非アクティブな[`reference/completed/`](reference/completed/)を使用します。完成版を一括コピーすることは通常の演習手順ではありません。5.6では、5.5を完了した正常状態へ異常系scenario patchを適用します。

`governance-check`はPull Request本文とbranch名からIssue番号候補を抽出し、`target_version`と`required_final_stage: UT`を検査します。`static-analysis`はGoアプリケーションへ`gofmt -l .`と`go vet ./...`を実行し、`unit-test`はgotestsumでJUnit XMLを生成します。`build-package`はGoアプリのLinux amd64バイナリ、checksum、manifestを生成し、`build-go-app_<test-run-id>`として保存します。

`environment-lifecycle`はBuild Artifactを再buildせず、Terraform Docker Providerで作成したUT環境面へAnsible Docker connectionでデプロイします。正式テスト開始前の起動・疎通確認（readiness check）、pytest + Testinfraの正式インフラテスト、pytest + requestsの正式APIテスト、cleanup、残存確認を同じjobで実行します。readiness checkはfail-fastの前提確認であり、Lesson 5.5の正式テスト13件には含めません。

`environment-lifecycle`は上流jobが失敗しても通常skipされません。環境未作成の早期失敗ではcleanup target 0としてcleanupと残存確認を記録し、残存がなければ`cleanup_state: Completed`とします。`pr-ci-gate`は必須job、証跡Artifact、Build Artifact、正式テスト結果、cleanup state、`remaining_resource_count: 0`を集約します。

変更Issueには、変更要求、受入条件、変更対象、`target_version`、`required_final_stage: UT`を記録します。Issue番号、Test run ID、Environment face ID、Build Artifact IDなどの実行時情報はGitHubまたはworkflowが生成します。

証跡Artifactはjobごとに分け、`evidence-governance_<test-run-id>`、`evidence-static-analysis_<test-run-id>`、`evidence-unit-test_<test-run-id>`、`evidence-build-package_<test-run-id>`、`evidence-environment_<test-run-id>`を使用します。証跡Artifact独自のchecksumは必須にしません。

Terraform / Ansible静的解析、Promotion Candidate Record、Release Candidate登録、Draft Release、GHCR pushは、セクション5のPR CIでは扱いません。

実務では、S3、CloudWatch Logs、組織標準のログ管理基盤、テスト管理製品などへ証跡を保存し、保持期間、アクセス制御、改ざん防止、監査対応を別途設計します。このハンズオンではAWS等の外部環境を使わず、GitHub Actions UIとActions Artifactで流れを確認します。

## 前提条件

GitHubアカウントを持っていない場合は、[準備手順](docs/setup/github-account-and-template.md)に従って作成します。公開テンプレートから、受講者本人の個人GitHubアカウントがOwnerの独立した演習用リポジトリを作成します。fork方式は使用しません。

ローカルPCで必要なのはGitとBashです。WindowsではGit for WindowsとGit Bash、macOS／Linuxでは利用可能なterminalとGitを使用します。自分の演習用リポジトリをHTTPSでcloneし、Repositoryルートで以降のコマンドを実行します。Docker、Terraform、AnsibleはGitHub-hosted runner上で動作するため、ローカル導入は必須ではありません。

```bash
git clone https://github.com/<account>/<repository>.git
cd <repository>
git status
```

教材本線の説明と画面例は、GitHub Free + Publicリポジトリを標準構成とします。GitHub FreeでPrivateリポジトリを使う場合は本線の品質ゲート演習に対応しません。個人アカウントでGitHub Proを利用している場合は、PublicまたはPrivateを選択できます。Organization所有は本線の対象外です。

Publicリポジトリは第三者から閲覧可能であり、GitHubの標準機能として閲覧やforkを技術的に防止できません。secret、token、パスワード、秘密鍵、個人情報、顧客情報、業務情報、実在システムの設定値や認証情報は登録せず、教材用のダミー情報だけを使用します。

## レクチャー構成

- [5.1 ハンズオンの全体像と演習環境の準備](docs/lessons/5.1-overview-and-setup.md)
- [5.2 変更要求・資源更新とCIパイプラインの準備](docs/lessons/5.2-change-and-pipeline-setup.md)
- [5.3 静的解析・単体テスト・ビルド・アーティファクト管理](docs/lessons/5.3-static-analysis-unit-test-build-artifact.md)
- [5.4 使い捨てテスト環境の構築・デプロイ・削除](docs/lessons/5.4-disposable-environment.md)
- [5.5 自動テスト・結果証跡管理とCIパイプラインの完成](docs/lessons/5.5-automated-test-and-evidence.md)
- [5.6 品質ゲートと異常系のハンドリング](docs/lessons/5.6-quality-gate-and-failures.md)

各レクチャーの想定時間は20分程度を目安にしますが、経験や操作速度により変動します。

## リポジトリ構成

このリポジトリには、ハンズオンで使用するアプリケーション、環境定義、テスト資源、レクチャー別の補足資料、セットアップ手順、トラブルシューティング、5.2から5.6の演習用patch、完成版参照を格納します。

## 異常系演習

5.6では、受講者がscenarioごとに変更Issueを作成し、正常系mainから異常系演習用branchを作成し、リポジトリ内で管理されたpatchを適用します。テンプレートから異常系branchを受講者リポジトリへコピーする方式は採用しません。修正後に`pr-ci-gate`が成功しても教材演習用Pull Requestはmainへmergeせずcloseし、対応Issueへ演習完了コメントを追加して手動closeします。

5.6の入口は[Lesson 5.6](docs/lessons/5.6-quality-gate-and-failures.md)です。scenario定義は[exercises/5.6/scenarios.yml](exercises/5.6/scenarios.yml)、patchは[exercises/5.6/patches/](exercises/5.6/patches/)、適用補助scriptは[scripts/exercises/apply-failure-scenario.sh](scripts/exercises/apply-failure-scenario.sh)に配置しています。scenarioを選ぶときは、まず次を確認します。

```bash
bash scripts/exercises/apply-failure-scenario.sh --list
bash scripts/exercises/apply-failure-scenario.sh --dry-run static-analysis-failure
bash scripts/exercises/apply-failure-scenario.sh static-analysis-failure
```

各scenarioは、`VERSION`を演習用PRの`target_version`と一致する値へ更新し、意図した不備を1件だけ注入します。Pull Request作成後は、失敗jobのSummary、該当する`evidence-*_<test-run-id>` Artifact、environment manifest、`pr-ci-gate` Summaryを確認します。演習後は`git apply --unidiff-zero -R exercises/5.6/patches/<scenario>.patch`でpatchを戻すか、同等の修正を行い、`pr-ci-gate`がsuccessへ戻ることを確認します。

## 開始手順と確認先

演習環境の準備は[GitHubアカウント、テンプレート、ローカルGitの準備](docs/setup/github-account-and-template.md)と[リポジトリ設定](docs/setup/repository-settings.md)に整理しています。`Template作成 → Repository設定Phase A → clone → 5.2`の順に進めます。受講者は5.1から5.6まで順に進め、CI失敗、Artifact不足、証跡不足、5.6異常系の確認で迷った場合は[トラブルシューティング](docs/troubleshooting/README.md)を参照します。

## ライセンス上の注意

本教材はオープンソースとして再利用・再配布する前提ではありません。受講者がPublicな演習用リポジトリを作成できることは、教材へOSSライセンスを付与することを意味しません。公開テンプレートへの`LICENSE`掲載は、この教材資源では確定しません。
