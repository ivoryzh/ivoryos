import ast
import importlib
import inspect
import logging
import os
import pickle
import subprocess
import sys
from typing import Optional, Dict, Tuple

from flask import session
from flask_socketio import SocketIO

from ivoryos.utils.db_models import Script


def get_script_file():
    """Get script from Flask session and returns the script"""
    session_script = session.get("scripts")
    if session_script:
        s = Script()
        s.__dict__.update(**session_script)
        return s
    else:
        return Script(author=session.get('user'))


def post_script_file(script, is_dict=False):
    """
    Post script to Flask. Script will be converted to a dict if it is a Script object
    :param script: Script to post
    :param is_dict: if the script is a dictionary,
    """
    if is_dict:
        session['scripts'] = script
    else:
        session['scripts'] = script.as_dict()


def create_gui_dir(parent_path):
    """
    Creates folders for ivoryos data
    """
    os.makedirs(parent_path, exist_ok=True)
    for path in ["config_csv", "scripts", "results", "pseudo_deck"]:
        os.makedirs(os.path.join(parent_path, path), exist_ok=True)


def save_to_history(filepath, history_path):
    """
    For manual deck connection only
    save deck file path that successfully connected to ivoryos to a history file
    """
    connections = []
    try:
        with open(history_path, 'r') as file:
            lines = file.read()
            connections = lines.split('\n')
    except FileNotFoundError:
        pass
    if filepath not in connections:
        with open(history_path, 'a') as file:
            file.writelines(f"{filepath}\n")


def import_history(history_path):
    """
    For manual deck connection only
    load deck connection history from history file
    """
    connections = []
    try:
        with open(history_path, 'r') as file:
            lines = file.read()
            connections = lines.split('\n')
    except FileNotFoundError:
        pass
    connections = [i for i in connections if not i == '']
    return connections


def available_pseudo_deck(path):
    """
    load pseudo deck (snapshot) from connection history
    """
    import os
    return os.listdir(path)


def _inspect_class(class_object=None, debug=False):
    """
    inspect class object: inspect function signature if not name.startswith("_")
    :param class_object: class object
    :param debug: debug mode will inspect function.startswith("_")
    :return: function: Dict[str, Dict[str, Union[Signature, str, None]]]
    """
    functions = {}
    under_score = "_"
    if debug:
        under_score = "__"
    for function, method in inspect.getmembers(type(class_object), predicate=inspect.isfunction):
        if not function.startswith(under_score) and not function.isupper():
            try:
                annotation = inspect.signature(method)
                # if doc_string:
                docstring = inspect.getdoc(method)
                functions[function] = dict(signature=annotation, docstring=docstring)

                # handle getter setters todo
                # if callable(att):
                #     functions[function] = inspect.signature(att)
                # else:
                #     att = getattr(class_object.__class__, function)
                #     if isinstance(att, property) and att.fset is not None:
                #         setter = att.fset.__annotations__
                #         setter.pop('return', None)
                #         if setter:
                #             functions[function] = setter
            except Exception:
                pass
    return functions


def _get_type_from_parameters(arg, parameters):
    """get argument types from inspection"""
    arg_type = ''
    if type(parameters) is inspect.Signature:
        annotation = parameters.parameters[arg].annotation
    elif type(parameters) is dict:
        annotation = parameters[arg]
    if annotation is not inspect._empty:
        # print(p[arg].annotation)
        if annotation.__module__ == 'typing':
            if hasattr(annotation, '_name') and annotation._name in ["Optional", "Union"]:
                # print(p[arg].annotation.__args__)
                arg_type = [i.__name__ for i in annotation.__args__]
            elif hasattr(annotation, '__origin__'):
                arg_type = annotation.__origin__.__name__
            else:
                # TODO
                pass
        else:
            arg_type = annotation.__name__
    return arg_type


def find_variable_in_script(script: Script, args: Dict[str, str]) -> Optional[Tuple[Dict[str, str], Dict[str, str]]]:
    # TODO: need to search for if the variable exists
    added_variables: list[Dict[str, str]] = [action for action in script.currently_editing_script if
                                             action["instrument"] == "variable"]

    possible_variable_arguments = {}
    possible_variable_types = {}

    for arg_name, arg_val in args.items():
        for added_variable in added_variables:
            if added_variable["action"] == arg_val:
                possible_variable_arguments[arg_name] = added_variable["action"]
                possible_variable_types[arg_name] = "variable"

    return possible_variable_arguments, possible_variable_types


def _convert_by_str(args, arg_types):
    """
    Converts a value to type through eval(f'{type}("{args}")')
    """
    if type(arg_types) is not list:
        arg_types = [arg_types]
    for arg_type in arg_types:
        if not arg_type == "any":
            try:
                args = eval(f'{arg_type}("{args}")') if type(args) is str else eval(f'{arg_type}({args})')
                return args
            except Exception:
                raise TypeError(f"Input type error: cannot convert '{args}' to {arg_type}.")


def _convert_by_class(args, arg_types):
    """
    Converts a value to type through type(arg)
    """
    if arg_types.__module__ == 'builtins':
        args = arg_types(args)
        return args
    elif arg_types.__module__ == "typing":
        for i in arg_types.__args__:  # for typing.Union
            try:
                args = i(args)
                return args
            except Exception:
                pass
        raise TypeError("Input type error.")
    # else:
    #     args = globals()[args]
    return args


def convert_config_type(args, arg_types, is_class: bool = False):
    """
    Converts an argument from str to an arg type
    """
    bool_dict = {"True": True, "False": False}
    # print(args, arg_types)
    # print(globals())
    if args:
        for arg in args:
            if arg not in arg_types.keys():
                raise ValueError("config file format not supported.")
            if args[arg] == '' or args[arg] == "None":
                args[arg] = None
            # elif args[arg] == "True" or args[arg] == "False":
            #     args[arg] = bool_dict[args[arg]]
            else:
                arg_type = arg_types[arg]
                try:
                    args[arg] = ast.literal_eval(args[arg])
                except ValueError:
                    pass
                if type(args[arg]) is not arg_type and not type(args[arg]).__name__ == arg_type:
                    if is_class:
                        # if arg_type.__module__ == 'builtins':
                        args[arg] = _convert_by_class(args[arg], arg_type)
                    else:
                        args[arg] = _convert_by_str(args[arg], arg_type)
    return args


def import_module_by_filepath(filepath: str, name: str):
    """
    Import module by file path
    :param filepath: full path of module
    :param name: module's name
    """
    spec = importlib.util.spec_from_file_location(name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SocketIOHandler(logging.Handler):
    def __init__(self, socketio: SocketIO):
        super().__init__()
        self.formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.socketio = socketio

    def emit(self, record):
        message = self.format(record)
        # session["last_log"] = message
        self.socketio.emit('log', {'message': message})


def start_logger(socketio: SocketIO, logger_name: str, log_filename: str = None):
    """
    stream logger to web through web socketIO
    """
    # logging.basicConfig( format='%(asctime)s - %(message)s')
    formatter = logging.Formatter(fmt='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(filename=log_filename, )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    # console_logger = logging.StreamHandler()  # stream to console
    # logger.addHandler(console_logger)
    socketio_handler = SocketIOHandler(socketio)
    logger.addHandler(socketio_handler)
    return logger


def ax_wrapper(data: dict):
    """
    Ax platform wrapper function for creating optimization campaign parameters and objective from the web form input
    :param data: e.g.,
    {
        "param_1_type": "range", "param_1_value": [1,2],
        "param_2_type": "range", "param_2_value": [1,2],
        "obj_1_min": True,
        "obj_2_min": True
    }
    :return: the optimization campaign parameters
    parameter=[
        {"name": "param_1", "type": "range", "bounds": [1,2]},
        {"name": "param_1", "type": "range", "bounds": [1,2]}
    ]
    objectives=[
        {"name": "obj_1", "min": True, "threshold": None},
        {"name": "obj_2", "min": True, "threshold": None},
    ]
    """
    from ax.service.utils.instantiation import ObjectiveProperties
    parameter = []
    objectives = {}
    # Iterate through the webui_data dictionary
    for key, value in data.items():
        # Check if the key corresponds to a parameter type
        if "_type" in key:
            param_name = key.split("_type")[0]
            param_type = value
            param_value = data[f"{param_name}_value"].split(",")
            try:
                values = [float(v) for v in param_value]
            except Exception:
                values = param_value
            if param_type == "range":
                parameter.append({"name": param_name, "type": param_type, "bounds": values})
            if param_type == "choice":
                parameter.append({"name": param_name, "type": param_type, "values": values})
            if param_type == "fixed":
                parameter.append({"name": param_name, "type": param_type, "value": values[0]})
        elif key.endswith("_min"):
            if not value == 'none':
                obj_name = key.split("_min")[0]
                is_min = True if value == "minimize" else False

                threshold = None if f"{obj_name}_threshold" not in data else data[f"{obj_name}_threshold"]
                properties = ObjectiveProperties(minimize=is_min, threshold=threshold)
                objectives[obj_name] = properties
    return parameter, objectives


def ax_initiation(data):
    """
    create Ax campaign from the web form input
    :param data:
    """
    install_and_import("ax", "ax-platform")
    parameter, objectives = ax_wrapper(data)
    from ax.service.ax_client import AxClient
    ax_client = AxClient()
    ax_client.create_experiment(parameter, objectives)
    return ax_client


def get_arg_type(args, parameters):
    arg_types = {}
    # print(args, parameters)
    if args:
        for arg in args:
            arg_types[arg] = _get_type_from_parameters(arg, parameters)
    return arg_types


def install_and_import(package, package_name=None):
    """
    Install the package and import it
    :param package: package to import and install
    :param package_name: pip install package name if different from package
    """
    try:
        # Check if the package is already installed
        importlib.import_module(package)
        # print(f"{package} is already installed.")
    except ImportError:
        # If not installed, install it
        # print(f"{package} is not installed. Installing now...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name or package])
        # print(f"{package} has been installed successfully.")


def web_config_entry_wrapper(data: dict, config_type: list):
    """
    Wrap the data dictionary from web config entries during execution configuration
    :param data: data dictionary
    :param config_type: data entry types ["str", "int", "float", "bool"]
    """
    rows = {}  # Dictionary to hold webui_data organized by rows

    # Organize webui_data by rows
    for key, value in data.items():
        if value:  # Only process non-empty values
            # Extract the field name and row index
            field_name, row_index = key.split('[')
            row_index = int(row_index.rstrip(']'))

            # If row not in rows, create a new dictionary for that row
            if row_index not in rows:
                rows[row_index] = {}

            # Add or update the field value in the specific row's dictionary
            rows[row_index][field_name] = value

    # Filter out any empty rows and create a list of dictionaries
    filtered_rows = [row for row in rows.values() if len(row) == len(config_type)]

    return filtered_rows


def create_deck_snapshot(deck, save: bool = False, output_path: str = ''):
    """
    Create a deck snapshot of the given script
    :param deck: python module name to create the deck snapshot from e.g. __main__
    :param save: save the deck snapshot into pickle file
    :param output_path: path to save the pickle file
    """
    deck_snapshot = {f"deck.{name}": _inspect_class(val) for name, val in vars(deck).items()
                     if not type(val).__module__ == 'builtins'
                     and not name[0].isupper()
                     and not name.startswith("_")}
    if deck_snapshot and save:
        # pseudo_deck = parse_dict
        parse_dict = deck_snapshot.copy()
        parse_dict["deck_name"] = os.path.splitext(os.path.basename(deck.__file__))[
            0] if deck.__name__ == "__main__" else deck.__name__
        with open(os.path.join(output_path, f"{parse_dict['deck_name']}.pkl"), 'wb') as file:
            pickle.dump(parse_dict, file)
    return deck_snapshot


def load_deck(pkl_name: str):
    """
    Loads a pickled deck snapshot from disk on offline mode
    :param pkl_name: name of the pickle file
    """
    if not pkl_name:
        return None
    try:
        with open(pkl_name, 'rb') as f:
            pseudo_deck = pickle.load(f)
        return pseudo_deck
    except FileNotFoundError:
        return None
