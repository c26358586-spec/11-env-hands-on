<!--
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
-->

# 5.3 比較ポイント

```text
governance-check
  |-> static-analysis: gofmt -l, go vet
  |-> unit-test: gotestsum, JUnit XML
  `-> build-package: Linux amd64 binary, checksum, manifest
        -> build-go-app_<test-run-id>
```

Build Artifactと証跡Artifactは別々に保存する。
