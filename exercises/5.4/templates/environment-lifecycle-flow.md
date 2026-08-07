<!--
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
-->

# 5.4 比較ポイント

```text
Build Artifact download and validation
  -> Environment face ID
  -> Terraform apply
  -> Ansible infra and deploy
  -> startup/connectivity readiness checks
     (formal test start prerequisite; not part of the 13 formal cases)
  -> pre-cleanup logs
  -> cleanup and residue verification
  -> environment evidence
```

readiness checkは、Build Artifactを展開してappを起動でき、process／port／HTTPの最低限の前提が成立したことをfail-fastで確認する。process、port、Nginx経由`/health`、versionは5.5でも受入・回帰証跡のために意図的に再確認する。

環境未作成の早期失敗でもcleanupと残存確認を省略しない。
