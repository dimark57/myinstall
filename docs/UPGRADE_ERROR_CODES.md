# Коды ошибок upgrade

`myinstall` возвращает ненулевой exit code и JSON с устойчивым
`error_code` при ошибке обновления. Текст `message` и `hint` предназначены
оператору, а автоматизация должна использовать `error_code`, `reason` и
`retryable`, а не разбирать русский текст.

Формат следует распространённой практике CLI/API: стабильный машинный
идентификатор (`error_code`/`reason`), отдельные `stage`, `message`, `hint`,
`details` и явный результат rollback. Прогресс остаётся в stderr, результат —
в stdout. Для Docker Compose отдельно различаются pull и запуск: `docker
compose pull` загружает образ, но не запускает контейнеры; `docker compose up`
возвращает ошибку уже на этапе запуска. При откате основной `error_code`
сохраняет первопричину, а `rollback_code` показывает результат восстановления:
`UPG-012` — успешно, `UPG-013` — восстановление не удалось.

| № | Код | Этап | Что означает | Что проверить |
|---:|---|---|---|---|
| 1 | `UPG-001` | Проверка запроса | Не указана версия для native/systemd/launchd | `--version vMAJOR.MINOR.PATCH` |
| 2 | `UPG-002` | Проверка запроса | `--image` передан не для Docker runtime | manifest и параметры команды |
| 3 | `UPG-003` | Проверка запроса | Для Docker/mixed не указаны image или version | `--image` или `--version` |
| 4 | `UPG-004` | Проверка запроса | Образ не immutable | semver `vX.Y.Z` или digest |
| 5 | `UPG-005` | Подготовка релиза | Release metadata или Compose template недоступны | `release_source`, `compose_source`, URL, token |
| 6 | `UPG-006` | Проверка Compose contract | Шаблон не соответствует manifest | `deploy/bootstrap/stack-compose.yml` |
| 7 | `UPG-007` | Доступ к registry | Не выполнен login в private registry | `MYINSTALL_GITHUB_TOKEN` и права |
| 8 | `UPG-008` | Загрузка образа | `docker compose pull` завершился ошибкой | tag/digest, сеть, registry, disk |
| 9 | `UPG-009` | Запуск runtime | `docker compose up -d` завершился ошибкой | `docker compose logs`, конфигурация |
| 10 | `UPG-010` | Миграция | `migration_command` вернул ошибку | `diagnostic`, состояние БД |
| 11 | `UPG-011` | Проверка здоровья | Новый runtime не прошёл healthcheck | URL, логи, зависимости |
| 12 | `UPG-012` | Rollback | Состояние до upgrade успешно восстановлено | исправить причину и повторить |
| 13 | `UPG-013` | Rollback | Ошибка была, восстановление runtime не удалось | `docker compose ps/logs`, ручной rollback |

## Операторская диагностика

После `UPG-008`:

```bash
docker compose -f /srv/nas/stacks/utilites/mytask/docker-compose.yml pull
```

После `UPG-009`, `UPG-011` или `UPG-013`:

```bash
docker compose -f /srv/nas/stacks/utilites/mytask/docker-compose.yml ps
docker compose -f /srv/nas/stacks/utilites/mytask/docker-compose.yml logs --tail=200
```

Для native/systemd runtime дополнительно используйте:

```bash
systemctl status <unit> --no-pager -l
journalctl -u <unit> --no-pager -n 200
```
