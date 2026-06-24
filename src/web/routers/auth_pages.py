"""
Роутер аутентификации и настроек безопасности дашборда.

Эндпоинты:
- GET  /login          — страница входа (HTML)
- POST /api/login      — проверка логина/пароля, установка cookie (JSON)
- POST /api/logout     — удаление сессионного cookie (JSON)
- GET  /settings       — страница настроек безопасности (HTML, только для auth)
- POST /api/settings/change-password — смена пароля (JSON)
"""

import re
from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from loguru import logger

from src.web.auth_session import (
    COOKIE_NAME,
    SESSION_TTL,
    get_session_middleware,
    hash_password,
)

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
    logger.info("Успешный вход в дашборд: {}", username)
    return response


@router.post("/api/logout")
async def api_logout() -> JSONResponse:
    """Удаляет сессионный cookie (выход из дашборда)."""
    response = JSONResponse(content={"success": True})
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """
    Страница настроек безопасности дашборда.

    Доступна только аутентифицированным пользователям
    (проверка — в SessionAuthMiddleware).
    """
    username = getattr(request.state, "dashboard_user", None)
    templates = cast(Jinja2Templates, request.app.state.templates)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"username": username},
    )


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
