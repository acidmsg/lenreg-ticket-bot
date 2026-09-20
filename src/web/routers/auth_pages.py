"""
Роутер аутентификации и настроек безопасности дашборда.

Эндпоинты:
- GET  /login          — страница входа (HTML)
- POST /api/login      — проверка логина/пароля, установка cookie (JSON)
- POST /api/logout     — удаление сессионного cookie (JSON)
- POST /api/settings/change-password — смена пароля (JSON)

Страница настроек (``/settings``) живёт в ``routers/pages.py``: это HTML-экран
с вкладками «Аккаунт» и «Параметры».
"""

import re
from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from loguru import logger

from src.services.audit import actor_from_request, log_action
from src.web.auth_session import (
    COOKIE_NAME,
    SESSION_TTL,
    get_session_middleware,
    hash_password,
)
from src.web.login_ratelimit import client_address, login_limiter

router = APIRouter()


def _sanitize_username(raw: str) -> str:
    """
    Remove characters unsafe for cookie values.
    Strips newlines, semicolons, and the pipe delimiter used in session format.
    """
    return re.sub(r"[\r\n;|]", "", raw).strip()[:128]


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> Response:
    """
    Страница входа в дашборд.

    Принимает ?next= для редиректа после успешного входа.
    Если пользователь уже аутентифицирован — сразу редиректит на ?next= или /.
    """
    mw = get_session_middleware()
    if mw and mw.enabled:
        session = request.cookies.get(COOKIE_NAME)
        if session:
            from src.web.auth_session import _verify_session

            username = _verify_session(session, mw.secret)
            if username is not None:
                next_url = request.query_params.get("next", "/")
                return RedirectResponse(url=next_url, status_code=302)

    templates = cast(Jinja2Templates, request.app.state.templates)
    next_url = request.query_params.get("next", "")
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next": next_url},
    )


@router.post("/api/login")
async def api_login(request: Request) -> JSONResponse:
    """
    Проверяет логин/пароль и устанавливает сессионный cookie.

    Возвращает JSON: {"success": true} при успехе,
    {"detail": "..."} при ошибке.
    """
    mw = get_session_middleware()
    if not mw or not mw.enabled:
        return JSONResponse(
            status_code=400,
            content={"detail": "Аутентификация отключена"},
        )

    # Ограничение перебора (DASH-10): блокировка считается по адресу клиента.
    client = client_address(request)
    locked = login_limiter.lockout_left(client)
    if locked:
        await log_action(
            request.app.state.db,
            actor="system",
            action="login_blocked",
            target=f"{client} retry={locked}s",
        )
        return JSONResponse(
            status_code=429,
            content={
                "detail": (
                    f"Слишком много неудачных попыток. Повторите через {locked} с."
                )
            },
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"detail": "Неверный формат запроса"},
        )

    username = body.get("username", "")
    password = body.get("password", "")

    if not username or not password:
        return JSONResponse(
            status_code=400,
            content={"detail": "Логин и пароль обязательны"},
        )

    if not mw.validate_credentials(username, password):
        logger.warning("Неудачная попытка входа в дашборд: {}", username)
        lock_seconds = login_limiter.record_failure(client)
        await log_action(
            request.app.state.db,
            actor=str(username)[:128],
            action="login_failed",
            target=f"{client} lock={lock_seconds}s",
        )
        if lock_seconds:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        "Слишком много неудачных попыток. "
                        f"Вход заблокирован на {lock_seconds} с."
                    )
                },
            )
        return JSONResponse(
            status_code=401,
            content={"detail": "Неверный логин или пароль"},
        )

    # NOTE: CodeQL false positive (py/cookie-injection).
    # username санитизирован _sanitize_username():
    # удалены \r\n, ;, |, обрезано до 128 символов.
    sanitized_username = _sanitize_username(username)
    session_value = mw.make_session_cookie(sanitized_username)
    response = JSONResponse(content={"success": True})
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_value,
        max_age=SESSION_TTL,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    login_limiter.reset(client)
    logger.info("Успешный вход в дашборд: {}", username)
    await log_action(request.app.state.db, actor=sanitized_username, action="login")
    return response


@router.post("/api/logout")
async def api_logout(request: Request) -> JSONResponse:
    """Удаляет сессионный cookie (выход из дашборда)."""
    await log_action(
        request.app.state.db, actor=actor_from_request(request), action="logout"
    )
    response = JSONResponse(content={"success": True})
    response.delete_cookie(COOKIE_NAME)
    return response


@router.post("/api/settings/change-password")
async def change_password(request: Request) -> JSONResponse:
    """
    Меняет пароль администратора дашборда.

    Требует старый пароль, новый логин (опционально) и новый пароль.
    После смены обновляет сессионный cookie с новым логином.
    """
    mw = get_session_middleware()
    if not mw or not mw.enabled:
        return JSONResponse(
            status_code=400,
            content={"detail": "Аутентификация отключена"},
        )

    current_username = getattr(request.state, "dashboard_user", None)
    if not current_username:
        return JSONResponse(
            status_code=401,
            content={"detail": "Требуется аутентификация"},
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"detail": "Неверный формат запроса"},
        )

    old_password = body.get("old_password", "")
    new_username = body.get("new_username", "")
    new_password = body.get("new_password", "")

    if not old_password:
        return JSONResponse(
            status_code=400,
            content={"detail": "Текущий пароль обязателен"},
        )

    if not mw.validate_credentials(current_username, old_password):
        return JSONResponse(
            status_code=401,
            content={"detail": "Неверный текущий пароль"},
        )

    if not new_password:
        return JSONResponse(
            status_code=400,
            content={"detail": "Новый пароль не может быть пустым"},
        )

    final_username = new_username or current_username
    new_hash = hash_password(new_password)
    mw.update_credentials(final_username, new_hash)

    # NOTE: CodeQL false positive (py/cookie-injection).
    # username санитизирован _sanitize_username():
    # удалены \r\n, ;, |, обрезано до 128 символов.
    sanitized_username = _sanitize_username(final_username)
    await log_action(
        request.app.state.db,
        actor=current_username,
        action="password_change",
        target=sanitized_username,
        username_changed=final_username != current_username,
    )
    session_value = mw.make_session_cookie(sanitized_username)
    response = JSONResponse(content={"success": True})
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_value,
        max_age=SESSION_TTL,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    logger.info("Пароль дашборда изменён, новый пользователь: {}", final_username)
    return response
