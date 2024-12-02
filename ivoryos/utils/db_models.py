import json
import keyword
import re
import uuid
from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy_utils import JSONType

db = SQLAlchemy()


class User(db.Model, UserMixin):
    __tablename__ = 'user'
    # id = db.Column(db.Integer)
    username = db.Column(db.String(50), primary_key=True, unique=True, nullable=False)
    # email = db.Column(db.String)
    hashPassword = db.Column(db.String(255))

    # password = db.Column()
    def __init__(self, username, password):
        # self.id = id
        self.username = username
        # self.email = email
        self.hashPassword = password

    def get_id(self):
        return self.username


class Script(db.Model):
    __tablename__ = 'script'
    # id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), primary_key=True, unique=True)
    deck = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(50), nullable=True)
    script_dict = db.Column(JSONType, nullable=True)
    time_created = db.Column(db.String(50), nullable=True)
    last_modified = db.Column(db.String(50), nullable=True)
    id_order = db.Column(JSONType, nullable=True)
    editing_type = db.Column(db.String(50), nullable=True)
    author = db.Column(db.String(50), nullable=False)

    def __init__(self, name=None, deck=None, status=None, script_dict: dict = None, id_order: dict = None,
                 time_created=None, last_modified=None, editing_type=None, author: str = None):
        if script_dict is None:
            script_dict = {"prep": [], "script": [], "cleanup": []}
        elif type(script_dict) is not dict:
            script_dict = json.loads(script_dict)
        if id_order is None:
            id_order = {"prep": [], "script": [], "cleanup": []}
        elif type(id_order) is not dict:
            id_order = json.loads(id_order)
        if status is None:
            status = 'editing'
        if time_created is None:
            time_created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if last_modified is None:
            last_modified = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if editing_type is None:
            editing_type = "script"

        self.name = name
        self.deck = deck
        self.status = status
        self.script_dict = script_dict
        self.time_created = time_created
        self.last_modified = last_modified
        self.id_order = id_order
        self.editing_type = editing_type
        self.author = author

    def as_dict(self):
        dict = self.__dict__
        dict.pop('_sa_instance_state', None)
        return dict

    def get(self):
        workflows = db.session.query(Script).all()
        # result = script_schema.dump(workflows)
        return workflows

    def find_by_uuid(self, uuid):
        for stype in self.script_dict:
            for action in self.script_dict[stype]:

                if action['uuid'] == int(uuid):
                    return action

    def _convert_type(self, args, arg_types):
        if type(arg_types) is not list:
            arg_types = [arg_types]
        for arg_type in arg_types:
            try:
                args = eval(f"{arg_type}('{args}')")
                return
            except Exception:
                pass
        raise TypeError(f"Input type error: cannot convert '{args}' to {arg_type}.")

    def update_by_uuid(self, uuid, args, output):
        bool_dict = {"True": True, "False": False}
        action = self.find_by_uuid(uuid)
        if type(action['args']) is dict:
            for arg in action['args']:
                if not args[arg].startswith("#"):

                    if args[arg] in bool_dict.keys():
                        args[arg] = bool_dict[args[arg]]
                    elif args[arg] == "None" or args[arg] == "":
                        args[arg] = None
                    else:
                        if arg in action['arg_types']:
                            arg_types = action['arg_types'][arg]
                            self._convert_type(args[arg], arg_types)
                        else:
                            try:
                                args[arg] = eval(args[arg])
                            except Exception:
                                pass
        else:
            args = list(args.values())[0]
            if not args.startswith("#"):
                if args in bool_dict.keys():
                    args = bool_dict[args]

                else:
                    if 'arg_types' in action:
                        arg_types = action['arg_types']
                        self._convert_type(args, arg_types)

                    # print(args)
        action['args'] = args
        # print(action)
        action['return'] = output

    @property
    def stypes(self):
        return list(self.script_dict.keys())

    @property
    def currently_editing_script(self):
        return self.script_dict[self.editing_type]

    @currently_editing_script.setter
    def currently_editing_script(self, script):
        self.script_dict[self.editing_type] = script

    @property
    def currently_editing_order(self):
        return self.id_order[self.editing_type]

    @currently_editing_order.setter
    def currently_editing_order(self, script):
        self.id_order[self.editing_type] = script

    # @property
    # def editing_type(self):
    #     return self.editing_type

    # @editing_type.setter
    # def editing_type(self, change_type):
    #     self.editing_type = change_type

    def update_time_stamp(self):
        self.last_modified = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_script(self, stype: str):
        return self.script_dict[stype]

    def isEmpty(self) -> bool:
        if not (self.script_dict['script'] or self.script_dict['prep'] or self.script_dict['cleanup']):
            return True
        return False

    def _sort(self, script_type):
        if len(self.id_order[script_type]) > 0:
            for action in self.script_dict[script_type]:
                for i in range(len(self.id_order[script_type])):
                    if action['id'] == int(self.id_order[script_type][i]):
                        # print(i+1)
                        action['id'] = i + 1
                        break
            self.id_order[script_type].sort()
            if not int(self.id_order[script_type][-1]) == len(self.script_dict[script_type]):
                new_order = list(range(1, len(self.script_dict[script_type]) + 1))
                self.id_order[script_type] = [str(i) for i in new_order]
            self.script_dict[script_type].sort(key=lambda x: x['id'])

    def sort_actions(self, script_type=None):
        if script_type:
            self._sort(script_type)
        else:
            for i in self.stypes:
                self._sort(i)

    def add_action(self, action: dict):
        current_len = len(self.currently_editing_script)
        action_to_add = action.copy()
        action_to_add['id'] = current_len + 1
        action_to_add['uuid'] = uuid.uuid4().fields[-1]
        self.currently_editing_script.append(action_to_add)
        self.currently_editing_order.append(str(current_len + 1))
        self.update_time_stamp()

    def add_variable(self, statement, variable):
        current_len = len(self.currently_editing_script)
        uid = uuid.uuid4().fields[-1]
        action_list = [{"id": current_len + 1, "instrument": 'variable', "action": variable,
                        "args": 'None' if statement == '' else statement, "return": '', "uuid": uid, "arg_types": ''}]
        self.currently_editing_script.extend(action_list)
        self.currently_editing_order.extend([str(current_len + i + 1) for i in range(len(action_list))])
        self.update_time_stamp()

    def add_logic_action(self, logic_type: str, statement):
        current_len = len(self.currently_editing_script)
        uid = uuid.uuid4().fields[-1]
        logic_dict = {
            "if":
                [
                    {"id": current_len + 1, "instrument": 'if', "action": 'if',
                     "args": 'True' if statement == '' else statement,
                     "return": '', "uuid": uid, "arg_types": ''},
                    {"id": current_len + 2, "instrument": 'if', "action": 'else', "args": '', "return": '',
                     "uuid": uid},
                    {"id": current_len + 3, "instrument": 'if', "action": 'endif', "args": '', "return": '',
                     "uuid": uid},
                ],
            "while":
                [
                    {"id": current_len + 1, "instrument": 'while', "action": 'while',
                     "args": 'False' if statement == '' else statement, "return": '', "uuid": uid, "arg_types": ''},
                    {"id": current_len + 2, "instrument": 'while', "action": 'endwhile', "args": '', "return": '',
                     "uuid": uid},
                ],

            "wait":
                [
                    {"id": current_len + 1, "instrument": 'wait', "action": "wait",
                     "args": '0' if statement == '' else statement,
                     "return": '', "uuid": uid, "arg_types": "float"},
                ],
        }
        action_list = logic_dict[logic_type]
        self.currently_editing_script.extend(action_list)
        self.currently_editing_order.extend([str(current_len + i + 1) for i in range(len(action_list))])
        self.update_time_stamp()

    def delete_action(self, id: int):

        uid = next((action['uuid'] for action in self.currently_editing_script if action['id'] == int(id)), None)
        id_to_be_removed = [action['id'] for action in self.currently_editing_script if action['uuid'] == uid]
        order = self.currently_editing_order
        script = self.currently_editing_script
        self.currently_editing_order = [i for i in order if int(i) not in id_to_be_removed]
        self.currently_editing_script = [action for action in script if action['id'] not in id_to_be_removed]
        self.sort_actions()
        self.update_time_stamp()

    def duplicate_action(self, id: int):
        action_to_duplicate = next((action for action in self.currently_editing_script if action['id'] == int(id)), None)
        insert_id = action_to_duplicate.get("id")
        self.add_action(action_to_duplicate)
        # print(self.currently_editing_script)
        if action_to_duplicate is not None:
            # Update IDs for all subsequent actions
            for action in self.currently_editing_script:
                if action['id'] > insert_id:
                    action['id'] += 1
            self.currently_editing_script[-1]['id'] = insert_id + 1
            # Sort actions if necessary and update the time stamp
            self.sort_actions()
            self.update_time_stamp()
        else:
            raise ValueError("Action not found: Unable to duplicate the action with ID", id)

    def config(self, stype):
        """
        take the global script_dict
        :return: list of variable that require input
        """
        configure = []
        config_type_dict = {}
        for action in self.script_dict[stype]:
            args = action['args']
            if args is not None:
                if type(args) is not dict:
                    if type(args) is str and args.startswith("#") and not args[1:] in configure:
                        configure.append(args[1:])
                        config_type_dict[args[1:]] = action['arg_types']

                else:
                    for arg in args:
                        if type(args[arg]) is str \
                                and args[arg].startswith("#") \
                                and not args[arg][1:] in configure:
                            configure.append(args[arg][1:])
                            if arg in action['arg_types']:
                                if action['arg_types'][arg] == '':
                                    config_type_dict[args[arg][1:]] = "any"
                                else:
                                    config_type_dict[args[arg][1:]] = action['arg_types'][arg]
                            else:
                                config_type_dict[args[arg][1:]] = "any"
        # todo
        return configure, config_type_dict

    def config_return(self):
        """
        take the global script_dict
        :return: list of variable that require input
        """

        return_list = [action['return'] for action in self.script_dict['script'] if not action['return'] == '']
        output_str = "return {"
        for i in return_list:
            output_str += "'" + i + "':" + i + ","
        output_str += "}"
        return output_str, return_list

    def finalize(self):
        self.status = "finalized"
        self.update_time_stamp()

    def save_as(self, name):
        self.name = name
        self.status = "editing"
        self.update_time_stamp()

    def indent(self, unit=0):
        string = "\n"
        for _ in range(unit):
            string += "\t"
        return string

    def compile(self, script_path=None):
        """
        Compile the current script to a Python file.
        :return: String to write to a Python file.
        """
        self.sort_actions()
        run_name = self.name if self.name else "untitled"
        run_name = self.validate_function_name(run_name)
        exec_string = ''

        for i in self.stypes:
            exec_string += self._generate_function_header(run_name, i)
            exec_string += self._generate_function_body(i)

        if script_path:
            self._write_to_file(script_path, run_name, exec_string)

        return exec_string

    @staticmethod
    def validate_function_name(name):
        """Replace invalid characters with underscores"""
        name = re.sub(r'\W|^(?=\d)', '_', name)
        # Check if it's a Python keyword and adjust if necessary
        if keyword.iskeyword(name):
            name += '_'
        return name

    def _generate_function_header(self, run_name, stype):
        """
        Generate the function header.
        """
        configure, _ = self.config(stype)
        function_header = f"\n\ndef {run_name}_{stype}("

        if stype == "script":
            function_header += ",".join(configure)

        function_header += "):"
        function_header += self.indent(1) + f"global {run_name}_{stype}"
        return function_header

    def _generate_function_body(self, stype):
        """
        Generate the function body for each type in stypes.
        """
        body = ''
        indent_unit = 1

        for index, action in enumerate(self.script_dict[stype]):
            text, indent_unit = self._process_action(indent_unit, action, index, stype)
            body += text
        return_str, return_list = self.config_return()
        if return_list and stype == "script":
            body += self.indent(indent_unit) + return_str

        return body

    def _process_action(self, indent_unit, action, index, stype):
        """
        Process each action within the script dictionary.
        """
        instrument = action['instrument']
        args = self._process_args(action['args'])
        save_data = action['return']
        action_name = action['action']
        next_action = self._get_next_action(stype, index)
        if instrument == 'if':
            return self._process_if(indent_unit, action_name, args, next_action)
        elif instrument == 'while':
            return self._process_while(indent_unit, action_name, args, next_action)
        elif instrument == 'variable':
            return self.indent(indent_unit) + f"{action_name} = {args}", indent_unit
        elif instrument == 'wait':
            return f"{self.indent(indent_unit)}time.sleep({args})", indent_unit
        else:
            return self._process_instrument_action(indent_unit, instrument, action_name, args, save_data)

    def _process_args(self, args):
        """
        Process arguments, handling any specific formatting needs.
        """
        if isinstance(args, str) and args.startswith("#"):
            return args[1:]
        return args

    def _process_if(self, indent_unit, action, args, next_action):
        """
        Process 'if' and 'else' actions.
        """
        exec_string = ""
        if action == 'if':
            exec_string += self.indent(indent_unit) + f"if {args}:"
            indent_unit += 1
            if next_action and next_action['instrument'] == 'if' and next_action['action'] == 'else':
                exec_string += self.indent(indent_unit) + "pass"
            # else:

        elif action == 'else':
            indent_unit -= 1
            exec_string += self.indent(indent_unit) + "else:"
            indent_unit += 1
            if next_action and next_action['instrument'] == 'if' and next_action['action'] == 'endif':
                exec_string += self.indent(indent_unit) + "pass"
        else:
            indent_unit -= 1
        return exec_string, indent_unit

    def _process_while(self, indent_unit, action, args, next_action):
        """
        Process 'while' and 'endwhile' actions.
        """
        exec_string = ""
        if action == 'while':
            exec_string += self.indent(indent_unit) + f"while {args}:"
            indent_unit += 1
            if next_action and next_action['instrument'] == 'while':
                exec_string += self.indent(indent_unit) + "pass"
        elif action == 'endwhile':
            indent_unit -= 1
        return exec_string, indent_unit

    def _process_instrument_action(self, indent_unit, instrument, action, args, save_data):
        """
        Process actions related to instruments.
        """
        if isinstance(args, dict):
            args_str = self._process_dict_args(args)
            single_line = f"{instrument}.{action}(**{args_str})"
        elif isinstance(args, str):
            single_line = f"{instrument}.{action} = {args}"
        else:
            single_line = f"{instrument}.{action}()"

        if save_data:
            save_data += " = "

        return self.indent(indent_unit) + save_data + single_line, indent_unit

    def _process_dict_args(self, args):
        """
        Process dictionary arguments, handling special cases like variables.
        """
        args_str = args.__str__()
        for arg in args:
            if isinstance(args[arg], str) and args[arg].startswith("#"):
                args_str = args_str.replace(f"'#{args[arg][1:]}'", args[arg][1:])
            elif self._is_variable(arg):
                args_str = args_str.replace(f"'{args[arg]}'", args[arg])
        return args_str

    def _get_next_action(self, stype, index):
        """
        Get the next action in the sequence if it exists.
        """
        if index < (len(self.script_dict[stype]) - 1):
            return self.script_dict[stype][index + 1]
        return None

    def _is_variable(self, arg):
        """
        Check if the argument is of type 'variable'.
        """
        return arg in self.script_dict and self.script_dict[arg].get("arg_types") == "variable"

    def _write_to_file(self, script_path, run_name, exec_string):
        """
        Write the compiled script to a file.
        """
        with open(script_path + run_name + ".py", "w") as s:
            if self.deck:
                s.write(f"import {self.deck} as deck")
            else:
                s.write("deck = None")
            s.write("\nimport time")
            s.write(exec_string)


if __name__ == "__main__":
    a = Script()

    print("")
