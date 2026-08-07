<!--
Copyright 2026 Ranamicus Technology LLC. All rights reserved.
-->

# 正式テストケースカタログ

Lesson 5.5では、事前に定義した次の13件を正式テストとして実行する。正常なLesson 5.5のPR CIでは、インフラ9件とAPI 4件のすべてが実行対象になる。

Lesson 5.4の起動・疎通確認（readiness check）は、正式テストを開始できる状態かをfail-fastで確認する手続きであり、この13件には含めない。process、port、Nginx経由`/health`、versionは5.4でも確認するが、5.5では受入・回帰証跡をケース単位で残す目的で意図的に再確認する。

## 共通前提

Infrastructure suiteには、`TARGET_CONTAINER_NAME`または`dist/ms1/container_name.txt`、`TARGET_NETWORK_NAME`または`dist/ms1/network_name.txt`、`EXPECTED_ENVIRONMENT_FACE_ID`または`ENVIRONMENT_FACE_ID`、`EXPECTED_APP_VERSION`または`APP_VERSION`を渡す。

API suiteには、`API_BASE_URL`と`EXPECTED_APP_VERSION`または`APP_VERSION`を渡す。`API-004`のために`TARGET_CONTAINER_NAME`も渡し、値がない場合だけ同caseをskipする。

## テストケース

| ID | 種別 | 目的・確認対象 | 前提／入力 | 実行内容 | 期待結果 | 自動化function | 主な証跡path | skip条件 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INF-001 | Infrastructure | Nginx package導入 | `TARGET_CONTAINER_NAME`または`dist/ms1/container_name.txt` | target上のNginx packageを照会する | Nginx packageが導入済み | `test_nginx_is_installed` | `test-results/infrastructure-test-junit.xml`<br>`test-results/infrastructure-test-result.json`<br>`summaries/infrastructure-test-summary.md`<br>`logs/infrastructure-test.log` | なし |
| INF-002 | Infrastructure | target containerの存在、稼働状態、管理label | `TARGET_CONTAINER_NAME`または`dist/ms1/container_name.txt`<br>必要に応じて`EXPECTED_ENVIRONMENT_FACE_ID`または`ENVIRONMENT_FACE_ID`、`EXPECTED_TEST_RUN_ID`、`EXPECTED_ISSUE_NUMBER`、`EXPECTED_MANAGED_BY`、`EXPECTED_MANAGED_LABEL_KEY`／`EXPECTED_MANAGED_LABEL_VALUE`、`EXPECTED_ENVIRONMENT_PATTERN_ID` | containerの存在、稼働状態、管理labelを照会する | 対象containerが存在して稼働し、入力された管理label（environment face ID、Test run ID、Issue番号、managed-by、environment pattern ID等）が期待値に一致する。入力されていないoptional labelは確認対象へ追加されない | `test_target_container_exists_and_has_expected_labels` | `test-results/infrastructure-test-junit.xml`<br>`test-results/infrastructure-test-result.json`<br>`summaries/infrastructure-test-summary.md`<br>`logs/infrastructure-test.log` | なし |
| INF-003 | Infrastructure | target networkの存在と、入力された管理label | `TARGET_NETWORK_NAME`または`dist/ms1/network_name.txt`<br>必要に応じて`EXPECTED_ENVIRONMENT_FACE_ID`または`ENVIRONMENT_FACE_ID`、`EXPECTED_TEST_RUN_ID`、`EXPECTED_ISSUE_NUMBER`、`EXPECTED_MANAGED_BY`、`EXPECTED_MANAGED_LABEL_KEY`／`EXPECTED_MANAGED_LABEL_VALUE`、`EXPECTED_ENVIRONMENT_PATTERN_ID` | networkの存在を確認し、入力された期待値に対応する管理labelを照会する | 対象networkが存在し、入力された管理label（environment face ID、Test run ID、Issue番号、managed-by、任意管理label、environment pattern ID等）が期待値に一致する。`EXPECTED_TEST_RUN_ID`が指定され、`EXPECTED_ENVIRONMENT_PATTERN_ID`が明示されていない場合、`environment_pattern_id`は`UT`である | `test_target_network_exists_and_has_expected_labels` | `test-results/infrastructure-test-junit.xml`<br>`test-results/infrastructure-test-result.json`<br>`summaries/infrastructure-test-summary.md`<br>`logs/infrastructure-test.log` | なし |
| INF-004 | Infrastructure | site enable設定の存在・symlink | `TARGET_CONTAINER_NAME`または`dist/ms1/container_name.txt` | Nginxの有効化済みsite設定を確認する | 設定fileが存在し、期待するsymlinkである | `test_nginx_configuration_file_exists` | `test-results/infrastructure-test-junit.xml`<br>`test-results/infrastructure-test-result.json`<br>`summaries/infrastructure-test-summary.md`<br>`logs/infrastructure-test.log` | なし |
| INF-005 | Infrastructure | Nginx設定の妥当性 | `TARGET_CONTAINER_NAME`または`dist/ms1/container_name.txt` | target上で`nginx -t`を実行する | 設定検証が成功する | `test_nginx_configuration_is_valid` | `test-results/infrastructure-test-junit.xml`<br>`test-results/infrastructure-test-result.json`<br>`summaries/infrastructure-test-summary.md`<br>`logs/infrastructure-test.log` | なし |
| INF-006 | Infrastructure | port 80／8080 listen | `TARGET_CONTAINER_NAME`または`dist/ms1/container_name.txt` | targetのlisten portを照会する | 80と8080がlistenしている | `test_required_ports_are_listening` | `test-results/infrastructure-test-junit.xml`<br>`test-results/infrastructure-test-result.json`<br>`summaries/infrastructure-test-summary.md`<br>`logs/infrastructure-test.log` | なし |
| INF-007 | Infrastructure | Go application binaryの存在・実行権限 | `TARGET_CONTAINER_NAME`または`dist/ms1/container_name.txt` | 配置済みbinaryのfile属性を確認する | binaryが存在し、実行可能である | `test_go_application_binary_exists` | `test-results/infrastructure-test-junit.xml`<br>`test-results/infrastructure-test-result.json`<br>`summaries/infrastructure-test-summary.md`<br>`logs/infrastructure-test.log` | なし |
| INF-008 | Infrastructure | Go application process稼働 | `TARGET_CONTAINER_NAME`または`dist/ms1/container_name.txt` | targetのprocess一覧を確認する | Go application processが稼働している | `test_go_application_process_is_running` | `test-results/infrastructure-test-junit.xml`<br>`test-results/infrastructure-test-result.json`<br>`summaries/infrastructure-test-summary.md`<br>`logs/infrastructure-test.log` | なし |
| INF-009 | Infrastructure | Nginx経由healthのJSON bodyに含まれるpayload status／service／version | `TARGET_CONTAINER_NAME`または`dist/ms1/container_name.txt`<br>`EXPECTED_APP_VERSION`または`APP_VERSION` | target内部からNginx経由でhealth JSONを取得する | Nginx経由でhealth JSONを取得でき、payloadのstatusがok、serviceがms1-go-api、versionが期待値に一致する | `test_nginx_proxies_to_go_application` | `test-results/infrastructure-test-junit.xml`<br>`test-results/infrastructure-test-result.json`<br>`summaries/infrastructure-test-summary.md`<br>`logs/infrastructure-test.log` | なし |
| API-001 | API | `GET /health`のHTTP status、Content-Type、JSON payloadのstatus、service、version | `API_BASE_URL`<br>`EXPECTED_APP_VERSION`または`APP_VERSION` | Nginx経由で`GET /health`を実行する | HTTP 200を返す。Content-Typeがapplication/jsonで始まる。JSON payloadのstatusがok、serviceがms1-go-api、versionが期待値に一致する | `test_health_endpoint_via_nginx` | `test-results/api-test-junit.xml`<br>`test-results/api-test-result.json`<br>`summaries/api-test-summary.md`<br>`logs/api-test.log` | なし |
| API-002 | API | 未対応methodの拒否 | `API_BASE_URL` | Nginx経由で`POST /health`を実行する | HTTP 405を返す | `test_health_endpoint_rejects_unsupported_method` | `test-results/api-test-junit.xml`<br>`test-results/api-test-result.json`<br>`summaries/api-test-summary.md`<br>`logs/api-test.log` | なし |
| API-003 | API | 未定義pathの拒否 | `API_BASE_URL` | Nginx経由で未定義pathへGETする | HTTP 404を返す | `test_unknown_path_returns_not_found` | `test-results/api-test-junit.xml`<br>`test-results/api-test-result.json`<br>`summaries/api-test-summary.md`<br>`logs/api-test.log` | なし |
| API-004 | API | container直接応答とNginx経由応答のJSON bodyの一致 | `API_BASE_URL`<br>`TARGET_CONTAINER_NAME` | containerの8080番portからhealth JSON bodyを取得し、Nginx経由応答のJSON bodyと比較する | container直接応答とNginx経由応答のJSON bodyが一致する | `test_direct_container_health_matches_nginx_when_container_is_available` | `test-results/api-test-junit.xml`<br>`test-results/api-test-result.json`<br>`summaries/api-test-summary.md`<br>`logs/api-test.log` | `TARGET_CONTAINER_NAME`がない場合だけskip |

## 共通証跡

各自動化functionはpytestの`record_property`で表のIDをJUnit XMLの`test_case_id` propertyへ記録する。正式テストのcase単位結果はJUnit XMLで確認し、suite全体の結果はJSON result、Markdown summary、logで確認する。正常系ではINF-001～INF-009を各1回、API-001～API-004を各1回収集し、failed、errors、skipped、期待ID欠落、想定外ID、重複ID、property欠落を0件とする。`manifest.json`、`environment-lifecycle-result.json`、`pr-ci-gate` Job Summaryを併せて、証跡完全性とGate判定を追跡する。
