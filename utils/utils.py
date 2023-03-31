import inspect
import importlib.util

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


def new_script(deck):
    """
    script dictionary structure
    :param deck:
    :return:
    """
    script_dict = {'name': '',
                   'deck': deck.__name__ if deck else '',
                   'status': 'editing',
                   'prep': [],
                   'script': [],
                   'cleanup': [],
                   }
    order = {'prep': [],
             'script': [],
             'cleanup': [],
             }
    return script_dict, order


def indent(unit=0):
    string = "\n"
    for _ in range(unit):
        string += "\t"
    return string


def parse_functions(class_object=None, call=True):
    functions = {}
    for function in dir(class_object):
        if not function.startswith("_") and not function.isupper():
            # if call:
            att = getattr(class_object, function)

            # handle getter setters
            if callable(att):
                functions[function] = inspect.signature(att)
            else:
                try:
                    att = getattr(class_object.__class__, function)
                    if isinstance(att, property) and att.fset is not None:
                        functions[function] = att.fset.__annotations__
                except AttributeError:
                    pass
        # else:
        #     functions[function] = function
    return functions


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

def convert_type(args, parameters, configure=[]):
    bool_dict = {"True": True, "False": False}

    if not len(args) == 0:
        for arg in args:
            if args[arg] == '' or args[arg] == "None":
                args[arg] = None
            elif args[arg] == "True" or args[arg] == "False":
                args[arg] = bool_dict[args[arg]]
            # configure parameter
            elif args[arg].startswith("#"):
                # configure_variables.append(args[arg][1:])
                # exec(args[arg][1:]+"=None")
                configure.append(args[arg][1:])
                # args[arg] = args[arg][1:]
            elif type(parameters) is inspect.Signature:
                p = parameters.parameters
                if p[arg].annotation is not inspect._empty:
                    if not type(args[arg]) == p[arg].annotation:
                        args[arg] = p[arg].annotation(args[arg])
            elif type(parameters) is dict:
                if parameters[arg] is not None:
                    if not type(args[arg]) == parameters[arg]:
                        args[arg] = parameters[arg](args[arg])
        return args


def sort_actions(script_dict, order, script_type=None):
    """
    sort all three types if script_type is None
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
