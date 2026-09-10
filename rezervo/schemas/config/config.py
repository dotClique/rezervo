import os
from functools import lru_cache
from typing import Any
from uuid import UUID

import pydantic
from deepmerge import Merger  # type: ignore[import]
from pydantic import BaseModel

from rezervo.schemas.base import OrmBase
from rezervo.schemas.config import admin, app, user
from rezervo.schemas.config.admin import AdminConfig
from rezervo.schemas.config.app import AppConfig
from rezervo.schemas.config.user import UserPreferences


class Auth(app.Auth):
    pass


class Booking(app.Booking):
    pass


class Cron(app.Cron):
    pass


class Slack(admin.Slack, app.Slack):
    pass


class PushNotificationSubscriptionKeys(OrmBase):
    p256dh: str
    auth: str


class PushNotificationGrants(OrmBase):
    booking: bool = False
    community: bool = False
    reminder: bool = False


class PushNotificationSubscription(OrmBase):
    endpoint: str
    keys: PushNotificationSubscriptionKeys
    grants: PushNotificationGrants = pydantic.Field(
        default_factory=PushNotificationGrants
    )


class Notifications(user.Notifications, admin.Notifications, app.Notifications):
    slack: Slack | None = None
    push_notification_subscriptions: list[PushNotificationSubscription] | None = None


class ConfigValue(user.UserPreferences, admin.AdminConfig, app.AppConfig):
    auth: Auth
    booking: Booking
    cron: Cron
    notifications: Notifications | None = None


class Config(BaseModel):
    user_id: UUID
    config: ConfigValue


CONFIG_MERGER = Merger(
    # pass in a list of tuple, with the
    # strategies you are looking to apply
    # to each type.
    [
        # (list, ["append"]),
        (dict, ["merge"]),
        # (set, ["union"])
    ],
    # next, choose the fallback strategies,
    # applied to all other types:
    ["override"],
    # finally, choose the strategies in
    # the case where the types conflict:
    ["override"],
)


def config_from_stored(
    user_id: UUID,
    preferences: UserPreferences,
    push_notification_subscriptions: list[PushNotificationSubscription],
    admin_config: AdminConfig,
) -> Config:
    merged_config: dict[str, Any] = {}
    for c in [
        preferences.model_dump(),
        admin_config.model_dump(),
        read_app_config().model_dump(),
    ]:
        CONFIG_MERGER.merge(merged_config, c)
    config_value = ConfigValue(**merged_config)
    if config_value.notifications is None:
        config_value.notifications = Notifications()  # type: ignore
    if config_value.web_host is not None:
        config_value.notifications.host = config_value.web_host
    config_value.notifications.push_notification_subscriptions = (
        push_notification_subscriptions
    )
    return Config(user_id=user_id, config=config_value)


@lru_cache
def read_app_config() -> AppConfig:
    config = read_app_config_from_file()
    if config is None:
        raise Exception("Failed to load app config")

    config.database_connection_string = (
        get_or_pid1("DATABASE_CONNECTION_STRING") or config.database_connection_string
    )
    config.fusionauth.admin.username = (
        get_or_pid1("FUSIONAUTH_ADMIN_USERNAME") or config.fusionauth.admin.username
    )
    config.fusionauth.admin.password = (
        get_or_pid1("FUSIONAUTH_ADMIN_PASSWORD") or config.fusionauth.admin.password
    )
    config.fusionauth.application_id = (
        UUID(v)
        if (v := get_or_pid1("FUSIONAUTH_APPLICATION_ID"))
        else config.fusionauth.application_id
    )
    config.fusionauth.email.username = (
        get_or_pid1("FUSIONAUTH_EMAIL_USERNAME") or config.fusionauth.email.username
    )
    config.fusionauth.email.password = (
        get_or_pid1("FUSIONAUTH_EMAIL_PASSWORD") or config.fusionauth.email.password
    )
    config.fusionauth.oauth.clientSecret = (
        get_or_pid1("FUSIONAUTH_OAUTH_CLIENTSECRET")
        or config.fusionauth.oauth.clientSecret
    )

    if config.notifications is not None and config.notifications.slack is not None:
        config.notifications.slack.bot_token = (
            get_or_pid1("NOTIFICATIONS_SLACK_BOT_TOKEN")
            or config.notifications.slack.bot_token
        )
        config.notifications.slack.signing_secret = (
            get_or_pid1("NOTIFICATIONS_SLACK_SIGNING_SECRET")
            or config.notifications.slack.signing_secret
        )

    if config.notifications is not None and config.notifications.web_push is not None:
        config.notifications.web_push.public_key = (
            get_or_pid1("NOTIFICATIONS_WEB_PUSH_PUBLIC_KEY")
            or config.notifications.web_push.public_key
        )
        config.notifications.web_push.private_key = (
            get_or_pid1("NOTIFICATIONS_WEB_PUSH_PRIVATE_KEY")
            or config.notifications.web_push.private_key
        )

    return config


def read_app_config_from_file() -> AppConfig:
    with open(app.CONFIG_FILE) as f:
        return pydantic.TypeAdapter(app.AppConfig).validate_json(f.read())


@lru_cache(maxsize=1)
def pid1_environ() -> dict[str, str]:
    """PID 1's environment, or {} if unavailable (no /proc, no permission, not a container, ...)."""
    try:
        with open("/proc/1/environ", "rb") as f:
            raw = f.read()
    except FileNotFoundError, ProcessLookupError, PermissionError, OSError:
        return {}
    env = {}
    for kv in raw.split(b"\0"):
        if b"=" in kv:
            k, v = kv.split(b"=", 1)
            env[k.decode()] = v.decode()
    return env


def get_or_pid1(name: str) -> str | None:
    """Get env var from current or pid 1 environment (pid 1 required for cron-jobs)"""
    return os.environ.get(name) or pid1_environ().get(name)
