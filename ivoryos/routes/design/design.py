import csv
import json
import os
import pickle
import sys

from flask import Blueprint, redirect, url_for, flash, jsonify, send_file, request, render_template, session, \
    current_app, g
from flask_login import login_required
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename

from ivoryos.utils import utils
from ivoryos.utils.global_config import GlobalConfig
from ivoryos.utils.form import create_builtin_form, create_action_button, format_name, create_form_from_pseudo
from ivoryos.utils.llm_agent import LlmAgent
from ivoryos.utils.db_models import Script
from ivoryos.utils.script_runner import ScriptRunner

socketio = SocketIO()
design = Blueprint('design', __name__, template_folder='templates/design')

global_config = GlobalConfig()
runner = ScriptRunner()


@socketio.on('abort_action')
def handle_abort_action():
    runner.stop_execution()
    socketio.emit('log', {'message': "aborted pending tasks"})


@socketio.on('connect')
def handle_abort_action():
    # Fetch log messages from local file
    filename = os.path.join(current_app.config["OUTPUT_FOLDER"], current_app.config["LOGGERS_PATH"])
    with open(filename, 'r') as log_file:
        log_history = log_file.readlines()
    for message in log_history[-10:]:
        socketio.emit('log', {'message': message})


@design.route("/experiment/build/", methods=['GET', 'POST'])
@design.route("/experiment/build/<instrument>/", methods=['GET', 'POST'])
@login_required
def experiment_builder(instrument=None):
    # global deck
    deck = global_config.deck
    script = utils.get_script_file()
    if deck and script.deck is None:
        script.deck = os.path.splitext(os.path.basename(deck.__file__))[
            0] if deck.__name__ == "__main__" else deck.__name__
    script.sort_actions()

    pseudo_deck_name = session.get('pseudo_deck', '')
    pseudo_deck_path = os.path.join(current_app.config["DUMMY_DECK"], pseudo_deck_name)
    off_line = current_app.config["OFF_LINE"]
    enable_llm = current_app.config["ENABLE_LLM"]
    autofill = session.get('autofill')

    # autofill is not allowed for prep and cleanup
    autofill = autofill if script.editing_type == "script" else False
    forms = None
    pseudo_deck = utils.load_deck(pseudo_deck_path) if off_line and pseudo_deck_name else None
    if off_line and pseudo_deck is None:
        flash("Choose available deck below.")

    deck_list = utils.available_pseudo_deck(current_app.config["DUMMY_DECK"])

    functions = []
    if deck:
        deck_variables = global_config.deck_snapshot.keys()
    else:
        deck_variables = list(pseudo_deck.keys()) if pseudo_deck else []
        deck_variables.remove("deck_name") if len(deck_variables) > 0 else deck_variables
    if instrument:
        if instrument in ['if', 'while', 'variable', 'wait']:
            forms = create_builtin_form(instrument)
        else:
            if deck:
                function_metadata = global_config.deck_snapshot.get(instrument, {})
            elif pseudo_deck:
                function_metadata = pseudo_deck.get(instrument, {})
            functions = {key: data.get('signature', {}) for key, data in function_metadata.items()}
            forms = create_form_from_pseudo(pseudo=functions, autofill=autofill, script=script)
        if request.method == 'POST' and "hidden_name" in request.form:
            all_kwargs = request.form.copy()
            method_name = all_kwargs.pop("hidden_name", None)
            # if method_name is not None:
            form = forms.get(method_name)
            kwargs = {field.name: field.data for field in form if field.name != 'csrf_token'}

            if form and form.validate_on_submit():
                function_name = kwargs.pop("hidden_name")
                save_data = kwargs.pop('return', '')
                variable_kwargs = {}
                variable_kwargs_types = {}

                try:
                    variable_kwargs, variable_kwargs_types = utils.find_variable_in_script(script, kwargs)

                    for name in variable_kwargs.keys():
                        del kwargs[name]
                    primitive_arg_types = utils.get_arg_type(kwargs, functions[function_name])

                except:
                    primitive_arg_types = utils.get_arg_type(kwargs, functions[function_name])

                kwargs.update(variable_kwargs)
                arg_types = {}
                arg_types.update(variable_kwargs_types)
                arg_types.update(primitive_arg_types)
                all_kwargs.update(variable_kwargs)

                action = {"instrument": instrument, "action": function_name,
                          "args": {name: arg for (name, arg) in kwargs.items()},
                          "return": save_data,
                          'arg_types': arg_types}
                script.add_action(action=action)
            else:
                flash(form.errors)

        elif request.method == 'POST' and "builtin_name" in request.form:
            kwargs = {field.name: field.data for field in forms if field.name != 'csrf_token'}
            if forms.validate_on_submit():
                logic_type = kwargs.pop('builtin_name')
                if 'variable' in kwargs:
                    script.add_variable(**kwargs)
                else:
                    script.add_logic_action(logic_type=logic_type, **kwargs)
            else:
                flash(forms.errors)

        # toggle autofill
        elif request.method == 'POST' and "autofill" in request.form:
            autofill = not autofill
            forms = create_form_from_pseudo(functions, autofill=autofill, script=script)
            session['autofill'] = autofill
    utils.post_script_file(script)
    design_buttons = [create_action_button(i) for i in script.currently_editing_script]
    return render_template('experiment_builder.html', off_line=off_line, instrument=instrument, history=deck_list,
                           script=script, defined_variables=deck_variables,
                           local_variables=global_config.defined_variables,
                           functions=functions, forms=forms, buttons=design_buttons, format_name=format_name,
                           use_llm=enable_llm)


@design.route("/generate_code", methods=['POST'])
@login_required
def generate_code():
    agent = global_config.agent
    enable_llm = current_app.config["ENABLE_LLM"]
    instrument = request.form.get("instrument")

    if request.method == 'POST' and "clear" in request.form:
        session['prompt'][instrument] = ''
    if request.method == 'POST' and "gen" in request.form:
        prompt = request.form.get("prompt")
        session['prompt'][instrument] = prompt
        # sdl_module = utils.parse_functions(find_instrument_by_name(f'deck.{instrument}'), doc_string=True)
        sdl_module = global_config.deck_snapshot.get(instrument, {})
        empty_script = Script(author=session.get('user'))
        if enable_llm and agent is None:
            try:
                model = current_app.config["LLM_MODEL"]
                server = current_app.config["LLM_SERVER"]
                module = current_app.config["MODULE"]
                agent = LlmAgent(host=server, model=model, output_path=os.path.dirname(os.path.abspath(module)))
            except Exception as e:
                flash(e.__str__())
        action_list = agent.generate_code(sdl_module, prompt)
        for action in action_list:
            action['instrument'] = instrument
            action['return'] = ''
            if "args" not in action:
                action['args'] = {}
            if "arg_types" not in action:
                action['arg_types'] = {}
            empty_script.add_action(action)
        utils.post_script_file(empty_script)
    return redirect(url_for("design.experiment_builder", instrument=instrument, use_llm=True))


@design.route("/experiment", methods=['GET', 'POST'])
@login_required
def experiment_run():
    # global deck
    deck = global_config.deck
    script = utils.get_script_file()
    script.sort_actions()
    off_line = current_app.config["OFF_LINE"]
    deck_list = utils.import_history(os.path.join(current_app.config["OUTPUT_FOLDER"], 'deck_history.txt'))
    # if not off_line and deck is None:
    #     # print("loading deck")
    #     module = current_app.config.get('MODULE', '')
    #     deck = sys.modules[module] if module else None
    #     script.deck = os.path.splitext(os.path.basename(deck.__file__))[0]
    design_buttons = {stype: [create_action_button(i) for i in script.get_script(stype)] for stype in script.stypes}
    config_preview = []
    config_file_list = [i for i in os.listdir(current_app.config["CSV_FOLDER"]) if not i == ".gitkeep"]
    exec_string = script.compile(current_app.config['SCRIPT_FOLDER'])
    # print(exec_string)
    config_file = request.args.get("filename")
    config = []
    if config_file:
        session['config_file'] = config_file
    filename = session.get("config_file")
    if filename:
        # config_preview = list(csv.DictReader(open(os.path.join(current_app.config['CSV_FOLDER'], filename))))
        config = list(csv.DictReader(open(os.path.join(current_app.config['CSV_FOLDER'], filename))))
        config_preview = config[1:6]
        arg_type = config.pop(0)  # first entry is types
    try:
        exec(exec_string)
    except Exception:
        flash("Please check syntax!!")
        return redirect(url_for("design.experiment_builder"))
    # runner.globals_dict.update(globals())
    run_name = script.name if script.name else "untitled"

    dismiss = session.get("dismiss", None)
    script = utils.get_script_file()
    no_deck_warning = False

    _, return_list = script.config_return()
    config_list, config_type_list = script.config("script")
    # config = script.config("script")
    data_list = os.listdir(current_app.config['DATA_FOLDER'])
    data_list.remove(".gitkeep") if ".gitkeep" in data_list else data_list
    if deck is None:
        no_deck_warning = True
        flash(f"No deck is found, import {script.deck}")
    elif script.deck:
        is_deck_match = script.deck == deck.__name__ or script.deck == \
                        os.path.splitext(os.path.basename(deck.__file__))[0]
        if not is_deck_match:
            flash(f"This script is not compatible with current deck, import {script.deck}")
    if request.method == "POST":
        bo_args = None
        if "bo" in request.form:
            bo_args = request.form.to_dict()
            # ax_client = utils.ax_initiation(bo_args)
        if "online-config" in request.form:
            config = utils.web_config_entry_wrapper(request.form.to_dict(), config_list)
        repeat = request.form.get('repeat', None)

        try:
            datapath = current_app.config["DATA_FOLDER"]
            run_name = script.validate_function_name(run_name)
            runner.run_script(script=script, run_name=run_name, config=config, bo_args=bo_args,
                              logger=g.logger, socketio=g.socketio, repeat_count=repeat,
                              output_path=datapath
                              )
        except Exception as e:
            flash(e)
    return render_template('experiment_run.html', script=script.script_dict, filename=filename, dot_py=exec_string,
                           return_list=return_list, config_list=config_list, config_file_list=config_file_list,
                           config_preview=config_preview, data_list=data_list, config_type_list=config_type_list,
                           no_deck_warning=no_deck_warning, dismiss=dismiss, design_buttons=design_buttons, history=deck_list)


@design.route("/toggle_script_type/<stype>")
@login_required
def toggle_script_type(stype=None):
    script = utils.get_script_file()
    script.editing_type = stype
    utils.post_script_file(script)
    return redirect(url_for('design.experiment_builder'))


@design.route("/updateList", methods=['GET', 'POST'])
@login_required
def update_list():
    order = request.form['order']
    script = utils.get_script_file()
    script.currently_editing_order = order.split(",", len(script.currently_editing_script))
    utils.post_script_file(script)
    return jsonify('Successfully Updated')


# --------------------handle all the import/export and download/upload--------------------------
@design.route("/clear")
@login_required
def clear():
    deck = global_config.deck
    pseudo_name = session.get("pseudo_deck", "")
    if deck:
        deck_name = os.path.splitext(os.path.basename(deck.__file__))[
            0] if deck.__name__ == "__main__" else deck.__name__
    elif pseudo_name:
        deck_name = pseudo_name
    else:
        deck_name = ''
    script = Script(deck=deck_name, author=session.get('username'))
    utils.post_script_file(script)
    return redirect(url_for("design.experiment_builder"))


@design.route("/import_pseudo", methods=['GET', 'POST'])
@login_required
def import_pseudo():
    pkl_name = request.form.get('pkl_name')
    script = utils.get_script_file()
    session['pseudo_deck'] = pkl_name

    if script.deck is None or script.isEmpty():
        script.deck = pkl_name.split('.')[0]
        utils.post_script_file(script)
    elif script.deck and not script.deck == pkl_name.split('.')[0]:
        flash(f"Choose the deck with name {script.deck}")
    return redirect(url_for("design.experiment_builder"))


@design.route('/uploads', methods=['GET', 'POST'])
@login_required
def upload():
    """
    upload csv configuration file
    :return:
    """
    if request.method == "POST":
        f = request.files['file']
        if 'file' not in request.files:
            flash('No file part')
        if f.filename.split('.')[-1] == "csv":
            filename = secure_filename(f.filename)
            f.save(os.path.join(current_app.config['CSV_FOLDER'], filename))
            session['config_file'] = filename
            return redirect(url_for("design.experiment_run"))
        else:
            flash("Config file is in csv format")
            return redirect(url_for("design.experiment_run"))


@design.route('/download_results/<filename>')
@login_required
def download_results(filename):
    filepath = os.path.join(current_app.config["DATA_FOLDER"], filename)
    return send_file(os.path.abspath(filepath), as_attachment=True)


@design.route('/load_json', methods=['GET', 'POST'])
@login_required
def load_json():
    if request.method == "POST":
        f = request.files['file']
        if 'file' not in request.files:
            flash('No file part')
        if f.filename.endswith("json"):
            script_dict = json.load(f)
            utils.post_script_file(script_dict, is_dict=True)
        else:
            flash("Script file need to be JSON file")
    return redirect(url_for("design.experiment_builder"))


@design.route('/download/<filetype>')
@login_required
def download(filetype):
    script = utils.get_script_file()
    run_name = script.name if script.name else "untitled"
    if filetype == "configure":
        filepath = os.path.join(current_app.config['SCRIPT_FOLDER'], f"{run_name}_config.csv")
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            cfg, cfg_types = script.config("script")
            writer.writerow(cfg)
            writer.writerow(list(cfg_types.values()))
    elif filetype == "script":
        script.sort_actions()
        json_object = json.dumps(script.as_dict())
        filepath = os.path.join(current_app.config['SCRIPT_FOLDER'], f"{run_name}.json")
        with open(filepath, "w") as outfile:
            outfile.write(json_object)
    elif filetype == "python":
        filepath = os.path.join(current_app.config["SCRIPT_FOLDER"], f"{run_name}.py")

    return send_file(os.path.abspath(filepath), as_attachment=True)


@design.route("/edit/<uuid>", methods=['GET', 'POST'])
@login_required
def edit_action(uuid):
    script = utils.get_script_file()
    action = script.find_by_uuid(uuid)
    session['edit_action'] = action
    if request.method == "POST":
        if "back" not in request.form:
            args = request.form.to_dict()
            save_as = args.pop('return', '')
            try:
                script.update_by_uuid(uuid=uuid, args=args, output=save_as)
            except Exception as e:
                flash(e.__str__())
        session.pop('edit_action')
    return redirect(url_for('design.experiment_builder'))


@design.route("/delete/<id>", methods=['GET', 'POST'])
@login_required
def delete_action(id):
    back = request.referrer
    script = utils.get_script_file()
    script.delete_action(id)
    utils.post_script_file(script)
    return redirect(back)


@design.route("/duplicate/<id>", methods=['GET', 'POST'])
@login_required
def duplicate_action(id):
    back = request.referrer
    script = utils.get_script_file()
    script.duplicate_action(id)
    utils.post_script_file(script)
    return redirect(back)