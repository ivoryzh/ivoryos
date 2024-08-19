import os
import pickle
import sys

from flask import Blueprint, redirect, url_for, flash, request, render_template, session, current_app
from flask_login import login_required

from ivoryos.utils.global_config import GlobalConfig
from ivoryos.utils import utils
from ivoryos.utils.form import create_form_from_module

global_config = GlobalConfig()

control = Blueprint('control', __name__)

global deck
deck = None


@control.route("/my_deck")
@login_required
def deck_controllers():
    global deck
    if deck is None:
        # print("loading deck")
        module = current_app.config.get('MODULE', '')
        deck = sys.modules[module] if module else None
        # global_config.deck = deck
    deck_variables = parse_deck(deck)
    # deck_variables = session.get("deck_variables")
    return render_template('controllers_home.html', defined_variables=deck_variables, deck=True)


@control.route("/new_controller/")
@control.route("/new_controller/<instrument>", methods=['GET', 'POST'])
@login_required
def new_controller(instrument=None):
    device = None
    args = None
    if instrument:

        device = find_instrument_by_name(instrument)
        args = utils.inspect.signature(device.__init__)

        if request.method == 'POST':
            device_name = request.form.get("device_name", "")
            if device_name and device_name in globals():
                flash("Device name is defined. Try another name, or leave it as blank to auto-configure")
                return render_template('controllers_new.html', instrument=instrument,
                                       api_variables=global_config.api_variables,
                                       device=device, args=args, defined_variables=global_config.defined_variables)
            if device_name == "":
                device_name = device.__name__.lower() + "_"
                num = 1
                while device_name + str(num) in global_config.defined_variables:
                    num += 1
                device_name = device_name + str(num)
            kwargs = request.form.to_dict()
            kwargs.pop("device_name")
            for i in kwargs:
                if kwargs[i] in globals():
                    kwargs[i] = globals()[kwargs[i]]
            try:
                utils.convert_config_type(kwargs, device.__init__.__annotations__, is_class=True)
            except Exception as e:
                flash(e)
            try:
                global_config.defined_variables[device_name] = device(**kwargs)
                # global_config.defined_variables.add(device_name)
                return redirect(url_for('control.controllers_home'))
            except Exception as e:
                flash(e)
    return render_template('controllers_new.html', instrument=instrument, api_variables=global_config.api_variables,
                           device=device, args=args, defined_variables=global_config.defined_variables)


@control.route("/controllers")
@login_required
def controllers_home():
    # defined_variables = parse_deck(deck)
    return render_template('controllers_home.html', defined_variables=global_config.defined_variables)


@control.route("/controllers/<instrument>", methods=['GET', 'POST'])
@login_required
def controllers(instrument):
    global deck
    if instrument.startswith("deck") and deck is None:
        module = current_app.config.get('MODULE', '')
        deck = sys.modules[module] if module else None
    inst_object = find_instrument_by_name(instrument)
    _forms = create_form_from_module(sdl_module=find_instrument_by_name(instrument), autofill=False, design=False)
    card_order = session.get('card_order')
    order = card_order.get(instrument, _forms.keys())
    if instrument not in card_order:
        card_order[instrument] = list(order)
        session['card_order'] = card_order
        # print(session['card_order'])
    forms = {name: _forms[name] for name in order if name in _forms}
    if request.method == 'POST':
        all_kwargs = request.form.copy()
        method_name = all_kwargs.pop("hidden_name", None)
        # if method_name is not None:
        form = forms.get(method_name)
        kwargs = {field.name: field.data for field in form if field.name != 'csrf_token'}
        function_executable = getattr(inst_object, method_name)
        if form and form.validate_on_submit():
            try:
                kwargs.pop("hidden_name")
                output = function_executable(**kwargs)
                flash(f"\nRun Success! Output value: {output}.")
            except Exception as e:
                flash(e.__str__())
        else:
            flash(form.errors)
    return render_template('controllers.html', instrument=instrument, inst=inst_object, forms=forms)


@control.route("/import_api", methods=['GET', 'POST'])
def import_api():
    filepath = request.form.get('filepath')
    # filepath.replace('\\', '/')
    name = os.path.split(filepath)[-1].split('.')[0]
    try:
        spec = utils.importlib.util.spec_from_file_location(name, filepath)
        module = utils.importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        classes = utils.inspect.getmembers(module, utils.inspect.isclass)
        if len(classes) == 0:
            flash("Invalid import: no class found in the path")
            return redirect(url_for("control.controllers_home"))
        for i in classes:
            globals()[i[0]] = i[1]
            global_config.api_variables.add(i[0])
    # should handle path error and file type error
    except Exception as e:
        flash(e.__str__())
    return redirect(url_for("control.new_controller"))


@control.route("/disconnect", methods=["GET"])
@control.route("/disconnect/<device_name>", methods=["GET"])
def disconnect(device_name=None):
    """TODO handle disconnect device"""
    if device_name:
        try:
            exec(device_name + ".disconnect()")
        except Exception:
            pass
        global_config.defined_variables.remove(device_name)
        globals().pop(device_name)
        return redirect(url_for('control.controllers_home'))

    deck_variables = ["deck." + var for var in set(dir(deck))
                      if not (var.startswith("_") or var[0].isupper() or var.startswith("repackage"))
                      and not type(eval("deck." + var)).__module__ == 'builtins']
    for i in deck_variables:
        try:
            exec(i + ".disconnect()")
        except Exception:
            pass
    globals()["deck"] = None
    return redirect(url_for('control.deck_controllers'))


@control.route("/import_deck", methods=['POST'])
def import_deck():
    global deck
    script = utils.get_script_file()
    filepath = request.form.get('filepath')
    session['dismiss'] = request.form.get('dismiss')
    update = request.form.get('update')
    back = request.referrer
    if session['dismiss']:
        return redirect(back)
    # if filepath == "manage history":

    name = os.path.split(filepath)[-1].split('.')[0]
    try:
        module = utils.import_module_by_filepath(filepath=filepath, name=name)
        # deck format checking
        if not utils.if_deck_valid(module):
            flash("Invalid Deck import")
            return redirect(url_for("control.deck_controllers"))
        globals()["deck"] = module
        utils.save_to_history(filepath, current_app.config["DECK_HISTORY"])
        parse_deck(deck, save=update)

        if script.deck is None:
            script.deck = module.__name__
    # file path error exception
    except Exception as e:
        flash(e.__str__())
    return redirect(back)


@control.route('/save-order/<instrument>', methods=['POST'])
def save_order(instrument):
    # Save the new order for the specified group to session
    data = request.json
    card_order = session.get("card_order", {})
    card_order[instrument] = data['order']
    session['card_order'] = card_order
    return '', 204


@control.route('/hide_function/<instrument>/<function>')
def hide_function(instrument, function):
    back = request.referrer
    hidden_functions = session.get("hidden_functions")
    functions = hidden_functions.get(instrument, [])
    card_order = session.get("card_order")
    order = card_order.get(instrument)
    if function not in functions:
        functions.append(function)
        order.remove(function)
    hidden_functions[instrument] = functions
    card_order[instrument] = order
    session['hidden_functions'] = hidden_functions
    session['card_order'] = card_order
    return redirect(back)


@control.route('/remove_hidden/<instrument>/<function>')
def remove_hidden(instrument, function):
    back = request.referrer
    hidden_functions = session.get("hidden_functions")
    functions = hidden_functions.get(instrument, [])
    card_order = session.get("card_order")
    order = card_order.get(instrument)
    if function in functions:
        functions.remove(function)
        order.append(function)
    hidden_functions[instrument] = functions
    card_order[instrument] = order
    session['hidden_functions'] = hidden_functions
    session['card_order'] = card_order
    return redirect(back)


def parse_deck(deck, save=None):
    parse_dict = {}
    # TODO
    deck_variables = ["deck." + var for var in set(dir(deck))
                      if not (var.startswith("_") or var[0].isupper() or var.startswith("repackage"))
                      and not type(eval("deck." + var)).__module__ == 'builtins'
                      ]
    session["deck_variables"] = deck_variables
    for var in deck_variables:
        instrument = eval(var)
        functions = utils.parse_functions(instrument)
        parse_dict[var] = functions
    if deck is not None and save:
        # pseudo_deck = parse_dict
        parse_dict["deck_name"] = os.path.splitext(os.path.basename(deck.__file__))[
            0] if deck.__name__ == "__main__" else deck.__name__
        with open(os.path.join(current_app.config["DUMMY_DECK"], f"{parse_dict['deck_name']}.pkl"), 'wb') as file:
            pickle.dump(parse_dict, file)
    return deck_variables


def find_instrument_by_name(name: str):
    if name.startswith("deck"):
        return eval(name)
    elif name in global_config.defined_variables:
        return global_config.defined_variables[name]
    elif name in globals():
        return globals()[name]
