from __future__ import annotations

from typing import Any


# Используется: cli.py для единообразных ошибок install/upgrade.
# Контракт: код и номер стабильны для операторов, title/stage/message/hint — для UI.
UPGRADE_ERRORS: dict[str, dict[str, Any]] = {
    "UPG-001": {
        "number": 1,
        "stage": "Проверка запроса",
        "title": "Не указан релиз",
        "message": "Для этого runtime нужно указать версию релиза.",
        "hint": "Передайте --version vMAJOR.MINOR.PATCH.",
        "reason": "MissingRelease",
        "retryable": False,
    },
    "UPG-002": {
        "number": 2,
        "stage": "Проверка запроса",
        "title": "Передан неподходящий образ",
        "message": "Параметр --image нельзя использовать для native/systemd/launchd runtime.",
        "hint": "Используйте --version или выберите Docker/mixed runtime.",
        "reason": "InvalidReleaseInput",
        "retryable": False,
    },
    "UPG-003": {
        "number": 3,
        "stage": "Проверка запроса",
        "title": "Не указан образ или версия",
        "message": "Для Docker/mixed runtime не задан ни образ, ни версия релиза.",
        "hint": "Передайте --image IMAGE@sha256:... или --version vMAJOR.MINOR.PATCH.",
        "reason": "MissingImageOrRelease",
        "retryable": False,
    },
    "UPG-004": {
        "number": 4,
        "stage": "Проверка запроса",
        "title": "Образ не является immutable",
        "message": "Docker upgrade принимает только semver-тег vX.Y.Z или digest.",
        "hint": "Не используйте mutable-теги вроде latest.",
        "reason": "MutableImageReference",
        "retryable": False,
    },
    "UPG-005": {
        "number": 5,
        "stage": "Подготовка релиза/Compose",
        "title": "Не удалось получить данные для upgrade",
        "message": "Release metadata или application Compose template недоступны.",
        "hint": "Проверьте release_source, compose_source/compose_source_url и доступ к GitHub.",
        "reason": "ComposeSourceUnavailable",
        "retryable": True,
    },
    "UPG-006": {
        "number": 6,
        "stage": "Проверка Compose contract",
        "title": "Compose contract нарушен",
        "message": "Сгенерированный Compose не соответствует manifest contract.",
        "hint": "Исправьте deploy/bootstrap/stack-compose.yml и повторите upgrade.",
        "reason": "InvalidComposeContract",
        "retryable": False,
    },
    "UPG-007": {
        "number": 7,
        "stage": "Доступ к registry",
        "title": "Не удалось войти в registry",
        "message": "Авторизация в private image registry завершилась ошибкой.",
        "hint": "Проверьте MYINSTALL_GITHUB_TOKEN и права Contents: Read-only.",
        "reason": "RegistryAuthenticationFailed",
        "retryable": False,
    },
    "UPG-008": {
        "number": 8,
        "stage": "Загрузка образа",
        "title": "Не удалось загрузить образ",
        "message": "Docker Compose не смог скачать новый immutable image.",
        "hint": "Проверьте image tag/digest, сеть, registry и свободное место.",
        "reason": "ImagePullFailed",
        "retryable": True,
    },
    "UPG-009": {
        "number": 9,
        "stage": "Запуск runtime",
        "title": "Не удалось запустить новый runtime",
        "message": "Docker Compose не смог запустить приложение с новым образом.",
        "hint": "Проверьте docker compose logs и конфигурацию контейнера.",
        "reason": "RuntimeStartFailed",
        "retryable": False,
    },
    "UPG-010": {
        "number": 10,
        "stage": "Миграция",
        "title": "Миграция приложения завершилась ошибкой",
        "message": "migration_command вернул ошибку.",
        "hint": "Проверьте diagnostic и состояние базы данных перед повтором.",
        "reason": "MigrationFailed",
        "retryable": False,
    },
    "UPG-011": {
        "number": 11,
        "stage": "Проверка здоровья",
        "title": "Новый runtime не прошёл healthcheck",
        "message": "Приложение запустилось, но healthcheck не подтвердил готовность.",
        "hint": "Проверьте healthcheck.url, логи приложения и зависимости.",
        "reason": "HealthcheckFailed",
        "retryable": False,
    },
    "UPG-012": {
        "number": 12,
        "stage": "Rollback",
        "title": "Новая версия отклонена, старая конфигурация восстановлена",
        "message": "Upgrade не прошёл проверку; предыдущий Compose возвращён.",
        "hint": "Проверьте diagnostic предыдущего этапа и повторите upgrade после исправления.",
        "reason": "UpgradeRolledBack",
        "retryable": False,
    },
    "UPG-013": {
        "number": 13,
        "stage": "Rollback",
        "title": "Ошибка восстановления предыдущей версии",
        "message": "Upgrade не прошёл, и автоматическое восстановление Compose завершилось ошибкой.",
        "hint": "Не повторяйте upgrade вслепую: проверьте docker compose ps/logs и выполните rollback.",
        "reason": "RollbackFailed",
        "retryable": False,
    },
}


def upgrade_failure(
    code: str,
    *,
    details: Any = None,
    diagnostic: str | None = None,
    rollback: str | None = None,
    rollback_code: str | None = None,
) -> dict[str, Any]:
    """Build a stable, human-readable upgrade error while retaining legacy ``error``."""
    spec = UPGRADE_ERRORS[code]
    result: dict[str, Any] = {
        "ok": False,
        "error": spec["title"],
        "error_code": code,
        "error_number": spec["number"],
        "stage": spec["stage"],
        "reason": spec["reason"],
        "message": spec["message"],
        "hint": spec["hint"],
        "retryable": spec["retryable"],
    }
    if details is not None:
        result["details"] = details
    if diagnostic:
        result["diagnostic"] = diagnostic
    if rollback:
        result["rollback"] = rollback
    if rollback_code:
        result["rollback_code"] = rollback_code
    return result
