from __future__ import annotations

import logging
import sys
import threading
import urllib
import webbrowser
from functools import partial
from queue import Queue
from secrets import token_hex

import click
from flask import Flask, abort, request
from pangea import PangeaConfig
from pangea.services import AuthN
from pangea.services.authn.models import ClientTokenCheckResult


def prompt_authn(
    *, authn_client_token: str, authn_hosted_login: str, pangea_domain: str = "aws.us.pangea.cloud"
) -> ClientTokenCheckResult:
    authn = AuthN(token=authn_client_token, config=PangeaConfig(domain=pangea_domain))

    # This queue will be used to pass data between the CLI and server threads.
    queue: Queue[str] = Queue()

    # Web server to handle the authentication flow callback.
    app = Flask(__name__)
    app.logger.disabled = True
    logger = logging.getLogger("werkzeug")
    logger.setLevel(logging.ERROR)
    logger.disabled = True
    sys.modules["flask.cli"].show_server_banner = lambda *x: None  # type: ignore[attr-defined]

    state = token_hex(32)

    @app.route("/callback")
    def callback():
        # Verify that the state param matches the original.
        if request.args.get("state") != state:
            return abort(401)

        auth_code = request.args.get("code")
        if auth_code is None:
            return abort(401)

        # Exchange the authorization code for the user's tokens and info.
        response = authn.client.userinfo(code=auth_code)
        if not response.success or response.result is None or response.result.active_token is None:
            return abort(401)

        queue.put(response.result.active_token.token)
        queue.task_done()

        return "Done, you can close this tab."

    # Spawn the server thread.
    func = partial(app.run, port=3000, debug=False)
    app_thread = threading.Thread(target=func, daemon=True)
    app_thread.start()

    # Open a new browser tab to authenticate.
    url_parameters = {"redirect_uri": "http://localhost:3000/callback", "response_type": "code", "state": state}
    url = f"{authn_hosted_login}?{urllib.parse.urlencode(url_parameters)}"
    click.echo("Opening browser to authenticate...")
    click.echo(f"URL: <{url}>")
    webbrowser.open_new_tab(url)

    # Wait for the server to receive the auth code.
    token = queue.get(block=True)
    check_result = authn.client.token_endpoints.check(token).result
    assert check_result
    return check_result
