<!--
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
-->

# リポジトリ設定手順

## 目的

GitHub Actionsの権限、merge方式、default branch用Rulesetを設定する。5.2の初回PR CI成功後に`pr-ci-gate`をRequired checkへ接続し、5.5でReady for reviewへ変更した後にmerge条件を最終確認する。

## 前提

- [GitHubアカウント、テンプレート、ローカルGitの準備](github-account-and-template.md)で、自分の演習用リポジトリを作成している。
- 演習用リポジトリのOwnerは受講者本人の個人GitHubアカウントである。
- 受講者は演習用リポジトリの`Settings`を変更できる。

教材本線は個人アカウントのGitHub Free + Publicリポジトリを使用する。GitHub ProではPublicまたはPrivateを選択できる。Organization所有は、Organizationのプラン、権限、上位ポリシーに従うため補足扱いとする。

## Phase A: レクチャー5.1で行う設定

Phase Aでは、Required check以外を設定したRulesetを`Disabled`で保存する。`pr-ci-gate`はまだ実行されていないため追加しない。

### 1. GitHub Actionsの利用可否を確認する

1. 演習用リポジトリで`Settings`を開く。
2. 左サイドバーの`Actions` → `General`を開く。
3. `Actions permissions`でGitHub Actionsが無効になっていないことを確認する。
4. 利用を制限している場合は、教材workflowが参照するGitHub公式Actionと許可済みの第三者Actionを実行できることを確認する。

### 2. Workflow permissionsを確認する

1. 同じ`Settings` → `Actions` → `General`画面の`Workflow permissions`を確認する。
2. `Read repository contents and packages permissions`を選択する。
3. `Allow GitHub Actions to create and approve pull requests`は有効にしない。
4. 設定を変更した場合は`Save`を選択する。

PR CIはworkflow内の`permissions`で必要なread権限だけを宣言する。GitHub Release、Draft Release、GHCRへのwrite権限は与えず、`pull_request_target`も使用しない。

### 3. merge方式を設定する

1. `Settings` → `General`を開く。
2. `Pull Requests`までスクロールする。
3. `Allow squash merging`を有効にする。
4. `Allow merge commits`を有効にする。
5. `Allow rebase merging`を無効にする。

### 4. `main-protection` Rulesetの基本設定を保存する

1. `Settings` → `Rules` → `Rulesets`を開く。
2. `New ruleset` → `New branch ruleset`を選択する。
3. `Ruleset name`へ`main-protection`と入力する。
4. `Enforcement status`は`Disabled`を選択する。
5. `Bypass list`は空のままにする。管理者や自分自身を追加しない。
6. `Target branches` → `Add target` → `Include default branch`を選択する。
7. `Restrict deletions`を有効にする。
8. `Require a pull request before merging`を有効にする。
9. Required approvalsは`0`のままにする。
10. `Block force pushes`を有効にする。
11. `Require status checks to pass`はまだ有効にしない。
12. `Create`を選択して保存する。

教材本線では`Include default branch`を使用する。UIの版や既存設定によりbranch patternを指定する場合は`main`を対象にできるが、これは補足手順である。

受講者自身はリポジトリ管理者であり、Rulesetを編集、無効化、削除できる。演習中は品質ゲートを迂回する変更を行わない。

## Phase A完了チェック

- [ ] GitHub Actionsが利用可能である。
- [ ] Workflow permissionsはreadを基本とし、Pull Requestの作成・承認権限を与えていない。
- [ ] Squash mergeとMerge commitが有効、Rebase mergeが無効である。
- [ ] `main-protection`のBypass listが空である。
- [ ] `Target branches` → `Add target` → `Include default branch`でdefault branchを対象にした。
- [ ] default branchの削除とforce pushを許可しない。
- [ ] `Require a pull request before merging`が有効、Required approvalsは`0`である。
- [ ] `Require status checks to pass`はまだ有効にしていない。
- [ ] Enforcement statusは`Disabled`である。

## Phase B: レクチャー5.2の初回PR CI成功後に行う設定

5.2でIssue、feature branch、Draft Pull Requestを作成し、最小PR CIを実行する。Pull Requestの`Checks`タブで`pr-ci-gate`が初めてsuccessになった後に、次を行う。

```text
Settings
→ Rules
  → Rulesets
    → main-protection
      → Require status checks to pass
        → Show additional settings
        → Add checks
          → pr-ci-gateを検索して選択
        → Require branches to be up to date before merging: 有効
      → Enforcement status: Active
      → Save changes
```

画面操作は次のとおり。

1. Pull Requestの`Checks`タブで、現在のheadに対する`pr-ci-gate`がsuccessであることを確認する。
2. `Settings` → `Rules` → `Rulesets` → `main-protection`を開く。
3. `Require status checks to pass`を有効にする。
4. `Show additional settings`を開き、`Add checks`を選択する。
5. `pr-ci-gate`を検索し、表示された同名checkを選択する。
6. `Require branches to be up to date before merging`を有効にする。
7. `Enforcement status`を`Active`へ変更する。
8. Bypass listが空で、`Restrict deletions`、`Require a pull request before merging`、`Block force pushes`が有効であることを再確認する。
9. `Save changes`を選択する。

GitHub UIの版により補助設定の展開方法や保存ボタンの表示が少し異なる場合がある。その場合も、`Require status checks to pass`の配下で`pr-ci-gate`を選択し、branchを最新にする条件とEnforcement `Active`を設定する。

5.2では、次の3点までを確認する。

- Pull Requestの`Checks`タブで`pr-ci-gate`がsuccessである。
- Rulesetに`pr-ci-gate`がRequired checkとして登録されている。
- RulesetのEnforcement statusが`Active`である。

Draft Pull RequestはDraftであること自体がmerge不可条件になる。Conversation画面下部のmerge条件は5.2では確認せず、5.5で`Ready for review`へ変更した後に確認する。

Required checkは`pr-ci-gate`の1本だけにする。`pr-ci-gate`は解析やテストを再実行せず、品質関連job、必須output、Artifact upload、cleanup、残存確認を集約する。

## Phase B完了チェック

- [ ] Pull Requestの`Checks`タブで`pr-ci-gate`のsuccessを確認した。
- [ ] `Require status checks to pass`で`pr-ci-gate`だけをRequired checkにした。
- [ ] `Require branches to be up to date before merging`を有効にした。
- [ ] Enforcement statusは`Active`である。
- [ ] Bypass listは空である。
- [ ] Draft状態ではConversation画面下部のmerge条件確認をまだ行わない。

## 5.5で行う最終確認

5.5の変更をpushし、Draft Pull Requestを`Ready for review`へ変更した後に、次を確認する。

1. `ready_for_review`で起動した最新PR CIが完了している。
2. 最新headの`pr-ci-gate`がsuccessである。
3. feature branchが最新mainを取り込んでいる。
4. Conversation画面下部でRulesetのmerge条件をすべて満たしている。

この確認が終わるまでmergeしない。

## 設定できない場合の確認先

- `Settings`が表示されない場合は、受講者本人の個人アカウントがOwnerか確認する。
- Rulesetを作成できない場合は、GitHubプランとVisibilityを確認する。GitHub Freeの本線はPublicを使用する。
- `pr-ci-gate`が`Add checks`の候補に表示されない場合は、5.2のPull Requestの`Checks`タブで同名checkが一度successになっているか確認する。
- GitHub Actionsを実行できない場合は、`Settings` → `Actions` → `General`の`Actions permissions`を確認する。
- CIやArtifactの調査は[トラブルシューティング](../troubleshooting/README.md)を参照する。

## 演習終了後のリポジトリ保持・削除

- 演習履歴が不要なら、リポジトリを削除できる。
- 復習やポートフォリオとして残す場合は、Publicの内容を第三者が閲覧できることを理解して保持する。
- GitHub Pro利用者はPrivateへ変更することも選択できる。
- 一度Publicにした情報は、削除やPrivate化だけでは完全に回収できない。
