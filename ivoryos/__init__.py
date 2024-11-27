import os
import sys
from typing import Union

from flask import Flask, redirect, url_for

from ivoryos.config import Config, get_config
from ivoryos.routes.auth.auth import auth, login_manager
from ivoryos.routes.control.control import control
from ivoryos.routes.database.database import database
from ivoryos.routes.design.design import design, socketio
from ivoryos.routes.main.main import main
from ivoryos.utils import utils
from ivoryos.utils.db_models import db
from ivoryos.utils.global_config import GlobalConfig
from ivoryos.utils.script_runner import ScriptRunner

global_config = GlobalConfig()


def create_app(config_class=None):
    url_prefix = os.getenv('URL_PREFIX', None)
    app = Flask(__name__, static_url_path=f'{url_prefix}/static', static_folder='static')
    app.config.from_object(config_class or 'config.get_config()')

    # Initialize extensions
    socketio.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    db.init_app(app)

    # Create database tables
    with app.app_context():
        db.create_all()

    # Additional setup
    utils.create_gui_dir(app.config['OUTPUT_FOLDER'])

    # logger_list = app.config["LOGGERS"]
    logger_path = os.path.join(app.config["OUTPUT_FOLDER"], app.config["LOGGERS_PATH"])
    logger = utils.start_logger(socketio, 'gui_logger', logger_path)

    @app.before_request
    def before_request():
        from flask import g
        g.logger = logger
        g.socketio = socketio

    app.register_blueprint(main, url_prefix=url_prefix)
    app.register_blueprint(auth, url_prefix=url_prefix)
    app.register_blueprint(design, url_prefix=url_prefix)
    app.register_blueprint(database, url_prefix=url_prefix)
    app.register_blueprint(control, url_prefix=url_prefix)

    @app.route('/')
    def redirect_to_prefix():
        return redirect(url_for('main.index'))  # Assuming 'index' is a route in your blueprint

    return app


def run(module=None, host="0.0.0.0", port=None, debug=None, llm_server=None, model=None,
        config: Config = None,
        logger: Union[str, list] = None,
        logger_output_name: str = None,
        ):
    app = create_app(config_class=config or get_config())  # Create app instance using factory function

    port = port or int(os.environ.get("PORT", 8000))
    debug = debug if debug is not None else app.config.get('DEBUG', True)

    app.config["LOGGERS"] = logger
    app.config["LOGGERS_PATH"] = logger_output_name or app.config["LOGGERS_PATH"] # default.log
    logger_path = os.path.join(app.config["OUTPUT_FOLDER"], app.config["LOGGERS_PATH"])

    if module:
        app.config["MODULE"] = module
        app.config["OFF_LINE"] = False
        global_config.deck = sys.modules[module]
        global_config.deck_snapshot = utils.create_deck_snapshot(global_config.deck, output_path=app.config["DUMMY_DECK"], save=True)
        # global_config.runner = ScriptRunner(globals())
    else:
        app.config["OFF_LINE"] = True
    if model:
        app.config["ENABLE_LLM"] = True
        app.config["LLM_MODEL"] = model
        app.config["LLM_SERVER"] = llm_server
        utils.install_and_import('openai')
        from ivoryos.utils.llm_agent import LlmAgent
        global_config.agent = LlmAgent(host=llm_server, model=model,
                                       output_path=app.config["OUTPUT_FOLDER"] if module is not None else None)
    else:
        app.config["ENABLE_LLM"] = False
    if logger and type(logger) is str:
        utils.start_logger(socketio, log_filename=logger_path, logger_name=logger)
    elif type(logger) is list:
        for log in logger:
            utils.start_logger(socketio, log_filename=logger_path, logger_name=log)
    socketio.run(app, host=host, port=port, debug=debug, use_reloader=False, allow_unsafe_werkzeug=True)
