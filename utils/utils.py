import inspect
import importlib.util
import pickle
import datetime
import traceback
import logging
from flask import flash
from flask_socketio import SocketIO

stypes = ['prep', 'script', 'cleanup']


def save_to_history(filepath):
    connections = []
    try:
        with open("deck_history.txt", 'r') as file:
            lines = file.read()
            connections = lines.split('\n')
    except FileNotFoundError:
        pass
    if filepath not in connections:
        with open("deck_history.txt", 'a') as file:
            file.writelines(f"{filepath}\n")


def import_history():
    connections = []
    try:
        with open("deck_history.txt", 'r') as file:
            lines = file.read()
            connections = lines.split('\n')
    except FileNotFoundError:
        pass
    connections = [i for i in connections if not i == '']
    return connections


def available_pseudo_deck():
    import os
    return os.listdir('./static/pseudo_deck')


def new_script(deck_name):
    """
    script dictionary structure
    :param deck:
    :return:
    """
    # .strftime("%Y-%m-%d %H:%M:%S")
    current_time = datetime.datetime.now()
    script_dict = {'name': '',
                   'deck': deck_name,
                   'status': 'editing',
                   'prep': [],
                   'script': [],
                   'cleanup': [],
                   # 'time_created': current_time,
                   # 'time_modified': current_time,
                   # 'author': '',
                   }
    order = {'prep': [],
             'script': [],
             'cleanup': [],
             }
    return script_dict, order


def parse_functions(class_object=None, call=True):
    functions = {}
    for function in dir(class_object):
        if not function.startswith("_") and not function.isupper():
            # if call:
            try:
                att = getattr(class_object, function)

                # handle getter setters
                if callable(att):
                    if is_compatible(att):
                        functions[function] = inspect.signature(att)
                else:
                    att = getattr(class_object.__class__, function)
                    if isinstance(att, property) and att.fset is not None:
                        setter = att.fset.__annotations__
                        setter.pop('return', None)
                        if setter:
                            functions[function] = setter
            except Exception:
                pass
        # else:
        #     functions[function] = function
    return functions


def is_compatible(att):
    try:
        obj = inspect.signature(att)
        try:
            pickle.dumps(obj)
        except Exception:
            return False
    except ValueError:
        return False
    return True


def config(script_dict):
    """
    take the global script_dict
    :return: list of variable that require input
    """
    configure = []
    for action in script_dict['script']:
        args = action['args']
        if args is not None:
            if type(args) is not dict:
                if type(args) is str and args.startswith("#") and not args[1:] in configure:
                    configure.append(args[1:])
            else:
                for arg in args:
                    if type(args[arg]) is str \
                            and args[arg].startswith("#") \
                            and not args[arg][1:] in configure:
                        configure.append(args[arg][1:])
    return configure


def config_return(script_dict):
    """
    take the global script_dict
    :return: list of variable that require input
    """
    return_list = [action['return'] for action in script_dict if not action['return'] == '']
    output_str = "return {"
    for i in return_list:
        output_str += "'" + i + "':" + i + ","
    output_str += "}"
    return output_str, return_list


def _get_type_from_parameters(arg, parameters):
    arg_type = ''
    if type(parameters) is inspect.Signature:
        p = parameters.parameters
        if p[arg].annotation is not inspect._empty:
            # print(p[arg].annotation)
            if p[arg].annotation.__module__ == 'typing':
                arg_type = p[arg].annotation.__args__
            else:
                arg_type = p[arg].annotation.__name__
            # print(arg_type)
    elif type(parameters) is dict:
        if parameters[arg]:

            if parameters[arg].__module__ == 'typing':
                arg_type = [i.__name__ for i in parameters[arg].__args__]
            else:
                arg_type = parameters[arg].__name__
    return arg_type


def convert_type(args, parameters):
    bool_dict = {"True": True, "False": False}
    arg_types = {}
    if args:
        for arg in args:
            if args[arg] == '' or args[arg] == "None":
                args[arg] = None
                arg_types[arg] = _get_type_from_parameters(arg, parameters)
            elif args[arg] == "True" or args[arg] == "False":
                args[arg] = bool_dict[args[arg]]
                arg_types[arg] = 'bool'
            elif args[arg].startswith("#"):
                args[arg] = args[arg]
                arg_types[arg] = _get_type_from_parameters(arg, parameters)
            elif type(parameters) is inspect.Signature:
                p = parameters.parameters
                if p[arg].annotation is not inspect._empty:
                    if p[arg].annotation.__module__ == 'typing':
                        arg_types[arg] = p[arg].annotation.__args__
                        for i in p[arg].annotation.__args__:
                            try:
                                args[arg] = i(args[arg])
                                break
                            except Exception:
                                pass

                    else:
                        args[arg] = p[arg].annotation(args[arg])
                        arg_types[arg] = p[arg].annotation.__name__
                else:
                    try:
                        args[arg] = eval(args[arg])
                        arg_types[arg] = ''
                    except Exception:
                        pass
            elif type(parameters) is dict:
                if parameters[arg]:
                    if parameters[arg].__module__ == 'typing':
                        # arg_types[arg] = parameters[arg].__args__
                        for i in parameters[arg].__args__:
                            # print(i)
                            try:
                                args[arg] = i(args[arg])
                                arg_types[arg] = i.__name__
                                break
                            except Exception:
                                pass
                    else:
                        args[arg] = parameters[arg](args[arg])
                        arg_types[arg] = parameters[arg].__name__
    return args, arg_types


def _convert_by_str(args, arg_types):
    # print(arg_types)
    if type(arg_types) is not list:
        arg_types = [arg_types]
    for i in arg_types:
        if i == "any":
            try:
                args = eval(args)
            except Exception:
                pass
            return args
        try:
            args = eval(i + "('" + args + "')")
            return args
        except Exception:
            pass
    raise TypeError(f"Input type error: cannot convert '{args}' to {i}.")


def _convert_by_class(args, arg_types):
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
    #     return args


def convert_config_type(args, arg_types, is_class: bool = False):
    bool_dict = {"True": True, "False": False}
    print(args, arg_types)
    # print(globals())
    if args:
        for arg in args:
            if args[arg] == '' or args[arg] == "None":
                args[arg] = None
            elif args[arg] == "True" or args[arg] == "False":
                args[arg] = bool_dict[args[arg]]
            else:
                arg_type = arg_types[arg]
                if is_class:
                    args[arg] = _convert_by_class(args[arg], arg_type)
                else:
                    args[arg] = _convert_by_str(args[arg], arg_type)
    return args


def sort_actions(script_dict, order, script_type=None):
    """
    sort all three types if script_type is None, otherwise sort the specified script type
    :return:
    """
    if script_type:
        sort(script_dict, order, script_type)
    else:
        for i in stypes:
            sort(script_dict, order, i)


def sort(script_dict, order, script_type):
    if len(order[script_type]) > 0:
        for action in script_dict[script_type]:
            for i in range(len(order[script_type])):
                if action['id'] == int(order[script_type][i]):
                    # print(i+1)
                    action['id'] = i + 1
                    break
        order[script_type].sort()
        if not int(order[script_type][-1]) == len(script_dict[script_type]):
            new_order = list(range(1, len(script_dict[script_type]) + 1))
            order[script_type] = [str(i) for i in new_order]
        script_dict[script_type].sort(key=lambda x: x['id'])


def logic_dict(key: str, current_len, args, var_name=None):
    """

    :param key:
    :param current_len:
    :param args:
    :param var_name:
    :return:
    """
    logic_dict = {
        "if":
            [
                {"id": current_len + 1, "instrument": 'if', "action": 'if', "args": args, "return": ''},
                {"id": current_len + 2, "instrument": 'if', "action": 'else', "args": '', "return": ''},
                {"id": current_len + 3, "instrument": 'if', "action": 'endif', "args": '', "return": ''},
            ],
        "while":
            [
                {"id": current_len + 1, "instrument": 'while', "action": 'while', "args": args, "return": ''},
                {"id": current_len + 2, "instrument": 'while', "action": 'endwhile', "args": '', "return": ''},
            ],
        "variable":
            [
                {"id": current_len + 1, "instrument": 'variable', "action": var_name, "args": args, "return": ''},
            ]
    }
    return logic_dict[key]


# def make_grid(row:int=1,col:int=1):
#     """
#     return the tray index str list by defining the size
#     :param row: 1 to 26
#     :param col:
#     :return: return the tray index
#     """
#     letter_list = [chr(i) for i in range(65, 90)]
#     return [i + str(j + 1) for i in letter_list[:col] for j in range(row)]


def make_grid(row: int = 1, col: int = 1):
    """
    return the tray index str list by defining the size
    :param row: 1 to 26
    :param col: 1 to 26
    :return: return the tray index
    """
    letter_list = [chr(i) for i in range(65, 90)]
    return [[i + str(j + 1) for j in range(col)] for i in letter_list[:row]]


tray_size_dict = {
    "metal_4_6": {"row": 4, "col": 6},
    "metal_4_6_landscape": {"row": 6, "col": 4},
    "noah_hplc_tray": {"row": 4, "col": 7},
    "solvent_tray": {"row": 5, "col": 2},
}


def import_module_by_filepath(filepath: str, name: str):
    spec = importlib.util.spec_from_file_location(name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def if_deck_valid(module):
    count = 0
    for var in set(dir(module)):
        if not var.startswith("_") and not var[0].isupper() and not var.startswith("repackage") \
                and not type(eval("module." + var)).__module__ == 'builtins':
            count += 1
    return False if count == 0 else True


class SocketIOHandler(logging.Handler):
    def __init__(self, socketio: SocketIO):
        super().__init__()
        self.formatter = logging.Formatter('%(asctime)s - %(message)s')
        self.socketio = socketio

    def emit(self, record):
        message = self.format(record)
        # session["last_log"] = message
        self.socketio.emit('log', {'message': message})


def start_logger(socketio: SocketIO):
    # logging.basicConfig( format='%(asctime)s - %(message)s')
    formatter = logging.Formatter(fmt='%(asctime)s - %(message)s')
    logger = logging.getLogger('gui_loggoer')
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(filename='example.log', )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    # console_logger = logging.StreamHandler()  # stream to console
    # logger.addHandler(console_logger)
    socketio_handler = SocketIOHandler(socketio)
    logger.addHandler(socketio_handler)
    return logger
