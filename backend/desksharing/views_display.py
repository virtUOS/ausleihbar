# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Device API of the door displays (token auth only, no session / CSRF)."""
import json

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from . import displays, door_render, door_session
from .models import Display

UNPAIRED_WAKE = 30


def _plain(response):
    response["Cache-Control"] = "no-store"
    return response


def _error(status: int, code: str) -> HttpResponse:
    return _plain(JsonResponse({"detail": code}, status=status))


def _etag_value(header: str) -> str:
    return header.strip().removeprefix("W/").strip('"')


def _frame_response(request, display, screen, *, now, wake, timeout):
    """200 with the stamped frame or 304; the ETag ignores the clock stamp."""
    panel = display.panel
    if screen is None:  # pairing frame
        image = door_render.render_pairing(display.pairing_code, panel)
        etag = door_render.frame_etag(door_render.to_frame(image))
        stamped = image
    else:
        plain = door_render.render(screen, panel, stamp=False)
        etag = door_render.frame_etag(door_render.to_frame(plain))
        stamped = None
    if display.last_etag != etag:
        Display.objects.filter(pk=display.pk).update(last_etag=etag)
        display.last_etag = etag
    if _etag_value(request.headers.get("If-None-Match", "")) == etag:
        response = HttpResponse(status=304)
    else:
        if stamped is None:
            stamped = door_render.render(screen, panel, stamp=True)
        response = HttpResponse(
            door_render.to_frame(stamped), content_type="application/octet-stream"
        )
    response["ETag"] = f'"{etag}"'
    response["X-Next-Wake"] = str(wake)
    response["X-Session-Timeout"] = str(timeout)
    return _plain(response)


def _respond(request, display, now, screen_fn):
    if display.is_paired:
        screen = screen_fn(display, now)
        return _frame_response(
            request, display, screen, now=now,
            wake=max(1, int(screen.view.next_wake)), timeout=screen.session_timeout,
        )
    displays.ensure_code(display, now)
    return _frame_response(
        request, display, None, now=now, wake=UNPAIRED_WAKE, timeout=0
    )


class DeviceView(APIView):
    authentication_classes: list = []  # secret auth only; also means no CSRF
    permission_classes = [AllowAny]


class FrameView(DeviceView):
    def get(self, request):
        panel = request.headers.get("X-Panel", "")
        if panel not in displays.PANELS:
            return _error(400, "invalid_panel")
        secret = displays.bearer_secret(request)
        if not secret:
            return _error(401, "unauthorized")
        if not displays.valid_secret(secret):
            return _error(400, "invalid_secret")
        now = timezone.now()
        display = displays.authenticate(request)
        if display is None:
            display = displays.ensure_pending(secret, panel, now)
            if display is None:
                return _error(429, "too_many_pending")
        if not display.is_paired and display.panel != panel:
            Display.objects.filter(pk=display.pk).update(panel=panel)
            display.panel = panel
        return _respond(request, display, now, door_session.current_screen)


class EventView(DeviceView):
    def post(self, request):
        display = displays.authenticate(request)
        if display is None or not display.is_paired:
            return _error(401, "unauthorized")
        now = timezone.now()
        if not displays.allow_event(display, now):
            return _error(429, "rate_limited")
        try:
            body = json.loads(request.body or b"{}")
        except ValueError:
            return _error(400, "invalid_json")
        button = body.get("button") if isinstance(body, dict) else None
        if button not in door_session.BUTTONS:
            return _error(400, "invalid_button")

        def run(display, now):
            return door_session.press(display, button, now)

        return _respond(request, display, now, run)
