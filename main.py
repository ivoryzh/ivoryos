# import inspect
import json
import os
import csv
import pickle
import sqlite3
import sys

from flask import Flask, redirect, url_for, flash, jsonify, send_file, request, render_template
from werkzeug.utils import secure_filename

from utils.utils import *

# import sample_deck as deck
deck = None
pseudo_deck = None
# import ur_deck as deck

app = Flask(__name__)
app.config['CSV_FOLDER'] = 'config_csv/'
app.config['SCRIPT_FOLDER'] = 'scripts/'
app.secret_key = "key"

sqlite3.register_adapter(list, json.dumps)
sqlite3.register_adapter(dict, json.dumps)
con = sqlite3.connect("webapp.db", check_same_thread=False)
cursor = con.cursor()
cursor.row_factory = sqlite3.Row
cursor.execute("""create table IF NOT EXISTS workflow (name TEXT PRIMARY KEY NOT NULL, 
                    deck TEXT NOT NULL, status TEXT NOT NULL, script NOT NULL, prep NOT NULL, cleanup NOT NULL)""")

# def get_db_connection():
#     connect = sqlite3.connect("webapp.db")
#     connect.row_factory = sqlite3.Row
#     return connect


script_type = 'script'  # set default type to be 'script'
# stypes = ['prep', 'script', 'cleanup']
script_dict, order = new_script(deck)
dismiss = None
libs = set(dir())

# ---------API imports------------
# from test import Test
# from test_inner import TestInner

api = set(dir())
api_variables = api - libs - set(["libs"])

import_variables = set(dir())

# -----initialize functions here------
# ran = Test(TestInner('test'))

user_variables = set(dir())
defined_variables = user_variables - import_variables - set(["import_variables"])


@app.route("/")
def index():
    return render_template('home.html')


@app.route("/help")
def help_info():
    return render_template('help.html')


@app.route("/controllers")
def controllers_home():
    return render_template('controllers_home.html', defined_variables=defined_variables, deck='')


@app.route("/experiment/build/", methods=['GET', 'POST'])
@app.route("/experiment/build/<instrument>/", methods=['GET', 'POST'])
# @app.route("/experiment/build/<instrument>/<action>", methods=['GET', 'POST'])
def experiment_builder(instrument=None):
    global script_dict, order, script_type, pseudo_deck

    deck_list = available_pseudo_deck()
    sort_actions(script_dict, order, script_type)
    deck_variables = list(pseudo_deck.keys()) if pseudo_deck else []
    functions = []
    if pseudo_deck is None:
        flash("Choose available deck below.")
        # flash(f"Make sure to import {script_dict['deck'] if script_dict['deck'] else 'deck'} for this script")
    if instrument:
        # inst_object = find_instrument_by_name(instrument)
        if instrument not in ['if', 'while', 'variable']:
            functions = pseudo_deck[instrument]
        current_len = len(script_dict[script_type])
        if request.method == 'POST' and "add" in request.form:

            args = request.form.to_dict()
            function_name = args.pop('add')
            script_type = args.pop('script_type')
            save_data = args.pop('return') if 'return' in request.form else ''
            try:
                args = convert_type(args, functions[function_name])
            except ValueError as e:
                flash(e.__str__())
                return redirect(url_for("experiment_builder", instrument=instrument))
            if type(functions[function_name]) is dict:
                args = list(args.values())[0]
            action_dict = {"id": current_len + 1, "instrument": instrument, "action": function_name,
                           "args": args, "return": save_data}
            order[script_type].append(str(current_len + 1))
            script_dict[script_type].append(action_dict)
        elif request.method == 'POST':
            # handle while, if and define variables
            script_type = request.form.get('script_type')
            statement = request.form.get('statement')
            if "if" in request.form:
                args = 'True' if statement == '' else statement
                action_list = [
                    {"id": current_len + 1, "instrument": 'if', "action": 'if', "args": args, "return": ''},
                    {"id": current_len + 2, "instrument": 'if', "action": 'else', "args": '', "return": ''},
                    {"id": current_len + 3, "instrument": 'if', "action": 'endif', "args": '', "return": ''},
                ]
            if "while" in request.form:
                args = 'False' if statement == '' else statement
                action_list = [
                    {"id": current_len + 1, "instrument": 'while', "action": 'while', "args": args, "return": ''},
                    {"id": current_len + 2, "instrument": 'while', "action": 'endwhile', "args": '', "return": ''},
                ]
            if "variable" in request.form:
                var_name = request.form.get('variable')
                args = 'None' if statement == '' else statement
                action_list = [
                    {"id": current_len + 1, "instrument": 'variable', "action": var_name, "args": args, "return": ''},
                ]
            order[script_type].extend([str(current_len + i + 1) for i in range(len(action_list))])
            script_dict[script_type].extend(action_list)
    return render_template('experiment_builder.html', instrument=instrument, script_type=script_type, history=deck_list,
                           script=script_dict, defined_variables=deck_variables, local_variables=defined_variables,
                           functions=functions, config=config(script_dict),
                           return_list=config_return(script_dict['script'])[1])


@app.route("/experiment", methods=['GET', 'POST'])
@app.route("/experiment/<path:filename>", methods=['GET', 'POST'])
def experiment_run(filename=None):
    # current_variables = set(dir())
    global order, script_dict
    prompt = False
    run_name = script_dict['name'] if script_dict['name'] else "untitled"
    file = open("scripts/" + run_name + ".py", "r")
    script_py = file.read()
    file.close()
    _, return_list = config_return(script_dict['script'])
    sort_actions(script_dict, order)
    if deck is None:
        prompt = True
    elif not script_dict['deck'] == '' and not script_dict['deck'] == deck.__name__:
        flash("This script is not compatible with current deck, import ", script_dict['deck'])
    if request.method == "POST":
        repeat = request.form.get('repeat')
        output_list = []
        try:
            # flash("Running!")
            exec(run_name + "_prep()")
            if filename is not None and not filename == 'None':
                df = csv.DictReader(open(os.path.join(app.config['CSV_FOLDER'], filename)))
                for i in df:
                    # todo
                    # arg = convert_type(i,)
                    output = eval(run_name + "_script(**" + str(i) + ")")
                    output_list.append(output)
            if not repeat == '' and repeat is not None:
                for i in range(int(repeat)):
                    output = eval(run_name + "_script()")
                    output_list.append(output)
            exec(run_name + "_cleanup()")
            if len(return_list) > 0:
                with open("results/" + run_name + "_data.csv", "w", newline='') as file:
                    writer = csv.DictWriter(file, fieldnames=return_list)
                    writer.writeheader()
                    writer.writerows(output_list)
            flash("Run finished")
        except Exception as e:
            flash(e)
    return render_template('experiment_run.html', script=script_dict, filename=filename, dot_py=script_py,
                           # return_list=return_list,
                           history=import_history(), prompt=prompt, dismiss=dismiss)


@app.route("/my_deck")
def deck_controllers():
    global deck
    deck_variables = parse_deck(deck)
    return render_template('controllers_home.html', defined_variables=deck_variables, deck="Deck",
                           history=import_history())


@app.route("/new_controller/")
@app.route("/new_controller/<instrument>", methods=['GET', 'POST'])
def new_controller(instrument=None):
    device = None
    args = None
    if instrument:
        device = find_instrument_by_name(instrument)
        # print(inst_object)
        args = inspect.signature(device.__init__)

        if request.method == 'POST':
            device_name = request.form["name"]
            if device_name == '' or device_name in globals():
                flash("Device name is NOT valid")
                return render_template('create_controller.html', instrument=instrument, api_variables=api_variables,
                                       device=device, args=args, defined_variables=defined_variables)
            kwargs = request.form.to_dict()
            kwargs.pop("name")
            for arg in device.__init__.__annotations__:
                if not device.__init__.__annotations__[arg].__module__ == "builtins":
                    kwargs[arg] = globals()[kwargs[arg]]
            try:
                globals()[device_name] = device(**kwargs)
                defined_variables.add(device_name)
                return redirect(url_for('controllers_home'))
            except Exception as e:
                flash(e)
    return render_template('create_controller.html', instrument=instrument, api_variables=api_variables,
                           device=device, args=args, defined_variables=defined_variables)


@app.route("/controllers/<instrument>", methods=['GET', 'POST'])
def controllers(instrument):
    inst_object = find_instrument_by_name(instrument)
    functions = parse_functions(inst_object)

    if request.method == 'POST':
        args = request.form.to_dict()
        function_name = args.pop('action')
        function_executable = getattr(inst_object, function_name)
        args = convert_type(args, functions[function_name])
        # try:
        #     args = convert_type(args, functions[function_name])
        # except Exception as e:
        #     flash(e)
        # return render_template('controllers.html', instrument=instrument, functions=functions, inst=inst_object)
        if type(functions[function_name]) is dict:
            args = list(args.values())[0]
        try:

            if callable(function_executable):
                if args is not None:
                    # print(args)
                    function_executable(**args)
                else:
                    function_executable()
            else:  # for setter
                function_executable = args
            flash("Run Success!")
        except Exception as e:
            flash(e)
    return render_template('controllers.html', instrument=instrument, functions=functions, inst=inst_object)


# -----------------------handle action editing--------------------------------------------
@app.route("/delete/<id>")
def delete_action(id):
    back = request.referrer
    for action in script_dict[script_type]:
        if action['id'] == int(id):
            script_dict[script_type].remove(action)
    for i in order[script_type]:
        if int(i) == int(id):
            order[script_type].remove(i)
    return redirect(back)


# TODO
@app.route("/edit/<id>")
def edit_action(id):
    for action in script_dict['script']:
        if action['id'] == int(id):
            return ""
            # return redirect(url_for('experiment_builder', edit_action=action))


@app.route("/edit_workflow/<workflow_name>")
def edit_workflow(workflow_name):
    global script_dict
    global order
    row = cursor.execute(f"SELECT * FROM workflow WHERE name = '{workflow_name}'").fetchone()
    script_dict = dict(zip(row.keys(), row))
    for i in stypes:
        script_dict[i] = json.loads(script_dict[i])
        order[i] = [str(i + 1) for i in range(len(script_dict[i]))]
    return redirect(url_for('experiment_builder'))


@app.route("/delete_workflow/<workflow_name>")
def delete_workflow(workflow_name):
    global script_dict
    cursor.execute(f"Delete FROM workflow WHERE name = '{workflow_name}'")
    con.commit()
    return redirect(url_for('load_from_database'))


@app.route("/publish")
def publish():
    # cursor = con.cursor()
    global script_dict
    row = cursor.execute(f"SELECT * FROM workflow WHERE name = '{script_dict['name']}'").fetchone()
    if row is not None and row["status"] == "finalized":
        flash("This is a finalized script, edit name to create a new entry")
        return redirect(url_for('experiment_builder'))
    else:
        cursor.execute("""INSERT OR REPLACE INTO workflow(name, deck, status, script, prep, cleanup)
                                    VALUES (:name,:deck, :status,:script, :prep, :cleanup);""", script_dict)
        con.commit()
    return redirect(url_for('load_from_database'))


@app.route("/finalize")
def finalize():
    # cursor = con.cursor()
    global script_dict
    script_dict['status'] = "finalized"
    return redirect(url_for('experiment_builder'))


@app.route("/database", methods=['GET', 'POST'])
@app.route("/database/<deck_name>", methods=['GET', 'POST'])
def load_from_database(deck_name=None):
    # cursor = con.cursor()]
    # deck_list = []
    if deck_name is None:
        workflows = cursor.execute("""SELECT * FROM workflow""").fetchall()
        temp = cursor.execute("""SELECT DISTINCT deck FROM workflow""")
        deck_list = [i['deck'] for i in temp]
    else:
        workflows = cursor.execute(f"""SELECT * FROM workflow WHERE deck = '{deck_name}'""").fetchall()
        deck_list = ["ALL"]
    # con.commit()
    return render_template("experiment_database.html", workflows=workflows, deck_list=deck_list)


@app.route("/edit_run_name", methods=['GET', 'POST'])
def edit_run_name():
    if request.method == "POST":
        run_name = request.form.get("run_name")
        exist_script = cursor.execute(f"""SELECT * FROM workflow WHERE name ='{run_name}'""").fetchall()
        if len(exist_script) == 0:
            script_dict['name'] = run_name
            script_dict['status'] = 'editing'
        else:
            flash("Script name is already exist in database")
        return redirect(url_for("experiment_builder"))


@app.route("/save_as", methods=['GET', 'POST'])
def save_as():
    if request.method == "POST":
        run_name = request.form.get("run_name")
        exist_script = cursor.execute(f"""SELECT * FROM workflow WHERE name ='{run_name}'""").fetchall()
        if len(exist_script) == 0:
            script_dict['name'] = run_name
            script_dict['status'] = 'editing'
            publish()
        else:
            flash("Script name is already exist in database")
        return redirect(url_for("experiment_builder"))


@app.route("/toggle_script_type/<stype>")
def toggle_script_type(stype=None):
    global script_type
    script_type = stype
    return redirect(url_for('experiment_builder'))


@app.route("/updateList", methods=['GET', 'POST'])
def update_list():
    getorder = request.form['order']
    global order
    order[script_type] = getorder.split(",", len(script_dict[script_type]))
    return jsonify('Successfully Updated')


@app.route("/configure", methods=['GET', 'POST'])
def build_run_block():
    """

    :param run_name:
    :return:
    """
    global script_dict
    global order
    sort_actions(script_dict, order)
    run_name = script_dict['name'] if script_dict['name'] else "untitled"

    # flash("Define deck first")
    # return redirect(url_for("experiment_builder"))
    with open("scripts/" + run_name + ".py", "w") as s:
        if not script_dict['deck'] == '':
            s.write("import " + script_dict['deck'] + " as deck")
        else:
            s.write("deck = None")
        for i in stypes:
            indent_unit = 1
            exec_string = "\n\ndef " + run_name + "_" + i + "("
            configure = config(script_dict)
            if i == "script":
                for j in configure:
                    exec_string = exec_string + j + ","
            exec_string = exec_string + "):"
            exec_string = exec_string + indent(indent_unit) + "global " + run_name + "_" + i

            for index, action in enumerate(script_dict[i]):
                instrument = action['instrument']
                args = action['args']
                save_data = action['return']
                action = action['action']
                next_ = None
                if instrument == 'if':

                    if index < (len(script_dict[i]) - 1):
                        next_ = script_dict[i][index + 1]
                    if action == 'if':
                        exec_string = exec_string + indent(indent_unit) + "if " + args + ":"
                        indent_unit += 1
                        if next_ and next_['instrument'] == 'if':
                            exec_string = exec_string + indent(indent_unit) + "pass"
                    elif action == 'else':
                        exec_string = exec_string + indent(indent_unit - 1) + "else:"
                        if next_['instrument'] == 'if' and next_['action'] == 'endif':
                            exec_string = exec_string + indent(indent_unit) + "pass"
                    else:
                        indent_unit -= 1
                elif instrument == 'while':

                    if index < (len(script_dict[i]) - 1):
                        next_ = script_dict[i][index + 1]
                    if action == 'while':
                        exec_string = exec_string + indent(indent_unit) + "while " + args + ":"
                        indent_unit += 1
                        if next_ and next_['instrument'] == 'while':
                            exec_string = exec_string + indent(indent_unit) + "pass"
                        # else:
                        #     indent = "\t"
                    elif action == 'endwhile':
                        indent_unit -= 1
                elif instrument == 'variable':
                    # args = "False" if args == '' else args
                    exec_string = exec_string + indent(indent_unit) + action + " = " + args
                else:
                    if args is not None:
                        if type(args) is dict:
                            temp = args.__str__()
                            for arg in args:
                                if type(args[arg]) is str and args[arg].startswith("#"):
                                    temp = temp.replace("'#" + args[arg][1:] + "'", args[arg][1:])
                            single_line = instrument + "." + action + "(**" + temp + ")"
                        else:
                            if type(args) is str and args.startswith("#"):
                                args = args.replace("'#" + args[1:] + "'", args[1:])
                            single_line = instrument + "." + action + " = " + str(args)
                    else:
                        single_line = instrument + "." + action + "()"
                    if save_data == '':
                        exec_string = exec_string + indent(indent_unit) + single_line
                    else:
                        exec_string = exec_string + indent(indent_unit) + save_data + " = " + single_line
            return_str, return_list = config_return(script_dict[i])
            if len(return_list) > 0:
                exec_string += indent(indent_unit) + return_str
            try:
                exec(exec_string)
            except Exception as e:
                # flash(e.__str__())
                flash("Please check syntax!!")
                return redirect(url_for("experiment_builder"))
            s.write(exec_string)
    # create config_csv file
    with open("empty_configure.csv", 'w') as f:
        writer = csv.writer(f)
        writer.writerow(configure)

    return redirect(url_for("experiment_run"))


# --------------------handle all the import/export and download/upload--------------------------
@app.route("/clear")
def clear():
    global script_dict, order
    script_dict, order = new_script(deck)
    return redirect(url_for("experiment_builder"))


@app.route("/import_api", methods=['GET', 'POST'])
def import_api():
    filepath = request.form.get('filepath')
    # filepath.replace('\\', '/')
    name = os.path.split(filepath)[-1].split('.')[0]
    try:
        spec = importlib.util.spec_from_file_location(name, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        classes = inspect.getmembers(module, inspect.isclass)
        if len(classes) == 0:
            flash("Invalid import: no class found in the path")
            return redirect(url_for("controllers_home"))
        for i in classes:
            globals()[i[0]] = i[1]
            api_variables.add(i[0])
    # should handle path error and file type error
    except Exception as e:
        flash(e.__str__())
    return redirect(url_for("new_controller"))


@app.route("/import_deck", methods=['POST'])
def import_deck():
    global script_dict, deck, dismiss, pseudo_deck
    filepath = request.form.get('filepath')
    dismiss = request.form.get('dismiss')
    update = request.form.get('update')
    back = request.referrer
    if dismiss:
        return redirect(back)
    name = os.path.split(filepath)[-1].split('.')[0]
    try:
        # if deck is not None:
        #     deck = None
        spec = importlib.util.spec_from_file_location(name, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # deck format checking
        count = 0
        for var in set(dir(module)):
            if not var.startswith("_") and not var[0].isupper() and not var.startswith("repackage") \
                    and not type(eval("module." + var)).__module__ == 'builtins':
                count += 1
        if count == 0:
            flash("Invalid Deck import")
            return redirect(url_for("deck_controllers"))
        globals()["deck"] = module
        save_to_history(filepath)
        parse_deck(deck, save=update)
        if script_dict['deck'] == "" or script_dict['deck'] is None:
            script_dict['deck'] = module.__name__
    # file path error exception
    except Exception as e:
        flash(e.__str__())
    # return redirect(url_for("experiment_builder"))
    return redirect(back)


@app.route("/import_pseudo", methods=['POST'])
def import_pseudo():
    global script_dict
    global pseudo_deck
    pkl_name = request.form.get('pkl_name')
    try:
        with open('static/pseudo_deck/' + pkl_name, 'rb') as f:
            pseudo_deck = pickle.load(f)
        if script_dict['deck'] == "" or script_dict['deck'] is None:
            script_dict['deck'] = pkl_name.split('.')[0]
        elif not script_dict['deck'] == "" and not script_dict['deck'] == pkl_name.split('.')[0]:
            flash(f"Choose the deck with name {pkl_name.split('.')[0]}")
    # file path error exception
    except Exception as e:
        flash(e.__str__())
    return redirect(url_for("experiment_builder"))


@app.route('/uploads', methods=['GET', 'POST'])
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
            f.save(os.path.join(app.config['CSV_FOLDER'], filename))
            return redirect(url_for("experiment_run", filename=filename))
        else:
            flash("Config file is in csv format")
            return redirect(url_for("experiment_run"))
    # return send_from_directory(directory=uploads, filename=filename)


@app.route('/load_json', methods=['GET', 'POST'])
def load_json():
    if request.method == "POST":
        f = request.files['file']
        if 'file' not in request.files:
            flash('No file part')
        if f.filename.split('.')[-1] == "json":
            global script_dict
            script_dict = json.load(f)
        else:
            flash("Script file need to be JSON file")
    return redirect(url_for("experiment_builder"))


@app.route('/download/<filetype>')
def download(filetype):
    run_name = script_dict['name'] if script_dict['name'] else "untitled"
    if filetype == "configure":
        return send_file("empty_configure.csv", as_attachment=True)
    elif filetype == "script":
        sort_actions(script_dict, order)
        json_object = json.dumps(script_dict)
        with open(run_name + ".json", "w") as outfile:
            outfile.write(json_object)
        return send_file(run_name + ".json", as_attachment=True)
    elif filetype == "python":
        return send_file("scripts/" + run_name + ".py", as_attachment=True)
    elif filetype == "data":
        return send_file("results/" + run_name + "_data.csv", as_attachment=True)


def find_instrument_by_name(name: str):
    if name.startswith("deck"):
        return eval(name)
    elif name in globals():
        return globals()[name]


def parse_deck(deck, save=None):
    global pseudo_deck
    parse_dict = {}
    if "gui_functions" in set(dir(deck)):
        deck_variables = ["deck." + var for var in deck.gui_functions]
    else:
        deck_variables = ["deck." + var for var in set(dir(deck))
                          if not (var.startswith("_") or var[0].isupper() or var.startswith("repackage"))
                          and not type(eval("deck." + var)).__module__ == 'builtins']
    for var in deck_variables:
        instrument = eval(var)
        functions = parse_functions(instrument)
        parse_dict[var] = functions
    if deck is not None and save:
        # pseudo_deck = parse_dict
        with open("static/pseudo_deck/" + deck.__name__ + ".pkl", 'wb') as file:
            pickle.dump(parse_dict, file)

    return deck_variables


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=False)
