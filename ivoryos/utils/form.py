from wtforms.fields.core import Field
from wtforms.validators import InputRequired
from wtforms.widgets.core import TextInput

from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, HiddenField, BooleanField, IntegerField
import inspect


def find_variable(data, script):
    # TODO: needs to check for valid order of variables, important when editting
    added_variables: list[dict[str, str]] = [action for action in script.currently_editing_script if
                                             action["instrument"] == "variable"
                                             # or action["return"] # TODO find returns
                                             ]
    for added_variable in added_variables:
        if added_variable["action"] == data:
            return data, added_variable["args"]
        # if added_variable["return"] == data:
        #     return data, None
    return None, None


class VariableOrStringField(Field):
    widget = TextInput()

    def __init__(self, label='', validators=None, script=None, **kwargs):
        super(VariableOrStringField, self).__init__(label, validators, **kwargs)
        self.script = script

    def process_formdata(self, valuelist):
        if valuelist:
            if not self.script.editing_type == "script" and valuelist[0].startswith("#"):
                raise ValueError(self.gettext("Variable is not supported in prep/cleanup"))
            self.data = valuelist[0]

    def _value(self):
        if self.script:
            variable, value = find_variable(self.data, self.script)
            if variable:
                return variable

        return str(self.data) if self.data is not None else ""


class VariableOrFloatField(Field):
    widget = TextInput()

    def __init__(self, label='', validators=None, script=None, **kwargs):
        super(VariableOrFloatField, self).__init__(label, validators, **kwargs)
        self.script = script

    def _value(self):
        if self.script:
            variable, value = find_variable(self.data, self.script)
            if variable:
                return variable

        if self.raw_data:
            return self.raw_data[0]
        if self.data is not None:
            return str(self.data)
        return ""

    def process_formdata(self, valuelist):
        if not valuelist:
            return
        elif valuelist[0].startswith("#"):
            if not self.script.editing_type == "script":
                raise ValueError(self.gettext("Variable is not supported in prep/cleanup"))
            self.data = valuelist[0]
            return
        try:
            if self.script:
                try:
                    variable, value = find_variable(valuelist[0], self.script)
                    if variable:
                        float(value)
                        self.data = str(variable)
                        return
                except ValueError:
                    pass

            self.data = float(valuelist[0])
        except ValueError as exc:
            self.data = None
            raise ValueError(self.gettext("Not a valid float value.")) from exc


# unset_value = UnsetValue()


class VariableOrIntField(Field):
    widget = TextInput()

    def __init__(self, label='', validators=None, script=None, **kwargs):
        super(VariableOrIntField, self).__init__(label, validators, **kwargs)
        self.script = script

    def _value(self):
        if self.script:
            variable, value = find_variable(self.data, self.script)
            if variable:
                return variable

        if self.raw_data:
            return self.raw_data[0]
        if self.data is not None:
            return str(self.data)
        return ""

    # def process_data(self, value):
    #
    #     if self.script:
    #         variable, var_value = find_variable(value, self.script)
    #         if variable:
    #             try:
    #                 int(var_value)
    #                 self.data = str(variable)
    #                 return
    #             except ValueError:
    #                 pass
    #     if value is None or value is unset_value:
    #         self.data = None
    #         return
    #     try:
    #         self.data = int(value)
    #     except (ValueError, TypeError) as exc:
    #         self.data = None
    #         raise ValueError(self.gettext("Not a valid integer value.")) from exc

    def process_formdata(self, valuelist):
        if not valuelist:
            return
        if self.script:
            variable, var_value = find_variable(valuelist[0], self.script)
            if variable:
                try:
                    int(var_value)
                    self.data = str(variable)
                    return
                except ValueError:
                    pass
        if valuelist[0].startswith("#"):
            if not self.script.editing_type == "script":
                raise ValueError(self.gettext("Variable is not supported in prep/cleanup"))
            self.data = valuelist[0]
            return
        try:
            self.data = int(valuelist[0])
        except ValueError as exc:
            self.data = None
            raise ValueError(self.gettext("Not a valid integer value.")) from exc


class VariableOrBoolField(BooleanField):
    widget = TextInput()

    def __init__(self, label='', validators=None, script=None, **kwargs):
        super(VariableOrBoolField, self).__init__(label, validators, **kwargs)
        self.script = script

    def process_data(self, value):

        if self.script:
            variable, var_value = find_variable(value, self.script)
            if variable:
                try:
                    bool(var_value)
                    return variable
                except ValueError:
                    return

        self.data = bool(value)

    def process_formdata(self, valuelist):
        if not valuelist or type(valuelist) is list and valuelist[0] == '':
            self.data = False
        elif valuelist and valuelist[0].startswith("#"):
            if not self.script.editing_type == "script":
                raise ValueError(self.gettext("Variable is not supported in prep/cleanup"))
            self.data = valuelist[0]
        else:
            self.data = True

    def _value(self):

        if self.script:
            variable, value = find_variable(self.raw_data, self.script)
            if variable:
                return variable

        if self.raw_data:
            return str(self.raw_data[0])
        return "y"


def format_name(name):
    """Converts 'example_name' to 'Example Name'."""
    name = name.split(".")[-1]
    text = ' '.join(word for word in name.split('_'))
    return text.capitalize()


def create_form_for_method(method, method_name, autofill, script=None, design=True):
    class DynamicForm(FlaskForm):
        pass

    annotation_mapping = {
        int: (VariableOrIntField if design else IntegerField, 'Enter integer value'),
        float: (VariableOrFloatField if design else FloatField, 'Enter numeric value'),
        str: (VariableOrStringField if design else StringField, 'Enter text'),
        bool: (VariableOrBoolField if design else BooleanField, 'Empty for false')
    }
    sig = method if type(method) is inspect.Signature else inspect.signature(method)

    for param in sig.parameters.values():
        if param.name == 'self':
            continue
        formatted_param_name = format_name(param.name)
        field_kwargs = {
            "label": formatted_param_name,
            "default": f'#{param.name}' if autofill else (param.default if param.default is not param.empty else ""),
            **({"script": script} if (autofill or design) else {})
        }
        field_class, placeholder_text = annotation_mapping.get(
            param.annotation,
            (VariableOrStringField if design else StringField, f'Enter {param.annotation} value')
        )
        render_kwargs = {"placeholder": placeholder_text}

        # Create the field with additional rendering kwargs for placeholder text
        field = field_class(**field_kwargs, render_kw=render_kwargs)
        setattr(DynamicForm, param.name, field)

    # setattr(DynamicForm, f'add', fname)
    return DynamicForm


# Create forms for each method in DummySDLDeck
def create_add_form(attr, attr_name, autofill, script=None, design=True):
    dynamic_form = create_form_for_method(attr, attr_name, autofill, script, design)
    if design:
        return_value = StringField(label='Save value as', render_kw={"placeholder": "Optional"})
        setattr(dynamic_form, 'return', return_value)
    hidden_method_name = HiddenField(name=f'hidden_name', render_kw={"value": f'{attr_name}'})
    setattr(dynamic_form, 'hidden_name', hidden_method_name)
    return dynamic_form


def create_form_from_module(sdl_module, autofill: bool, script=None, design=True):
    # sdl_deck = DummySDLDeck(DummyPump("COM1"), DummyBalance("COM2"))
    method_forms = {}
    for attr_name in dir(sdl_module):
        attr = getattr(sdl_module, attr_name)
        if inspect.ismethod(attr) and not attr_name.startswith('_'):
            form_class = create_add_form(attr, attr_name, autofill, script, design)
            method_forms[format_name(attr_name)] = form_class()
    return method_forms


def create_form_from_pseudo(pseudo: dict, autofill: bool, script=None, design=True):
    '''{'dose_liquid': < Signature(amount_in_ml: float, rate_ml_per_minute: float) >}'''
    method_forms = {}
    for attr_name, signature in pseudo.items():
        form_class = create_add_form(signature, attr_name, autofill, script, design)
        method_forms[attr_name] = form_class()
    return method_forms


def create_builtin_form(logic_type):
    class BuiltinFunctionForm(FlaskForm):
        pass

    placeholder_text = f'Enter numbers' if logic_type == 'wait' else f'Enter statement'
    description_text = f'Your variable can be numbers, boolean (True or False) or text ("text")' if logic_type == 'variable' else ''
    field_class = FloatField if logic_type == 'wait' else StringField  # Default to StringField as a fallback
    field_kwargs = {
        "label": f'statement',
        "validators": [InputRequired()] if logic_type in ['wait', "variable"] else [],
        "description": description_text,
    }
    render_kwargs = {"placeholder": placeholder_text}
    field = field_class(**field_kwargs, render_kw=render_kwargs)
    setattr(BuiltinFunctionForm, "statement", field)
    if logic_type == 'variable':
        variable_field = StringField(label=f'variable', validators=[InputRequired()],
                                     description="Your variable name cannot include space",
                                     render_kw=render_kwargs)
        setattr(BuiltinFunctionForm, "variable", variable_field)
    hidden_field = HiddenField(name=f'builtin_name', render_kw={"value": f'{logic_type}'})
    setattr(BuiltinFunctionForm, "builtin_name", hidden_field)
    return BuiltinFunctionForm()


def create_action_button(s: dict):
    style = ""
    if s['instrument'] in ['if', 'while']:
        text = f"{s['action']} {s['args']}"
        style = "background-color: tomato"
    elif s['instrument'] == 'variable':
        text = f"{s['action']} = {s['args']}"
    else:
        # regular action button
        prefix = f"{s['return']} = " if s['return'] else ""
        action_text = f"{s['instrument'].split('.')[-1] if s['instrument'].startswith('deck') else s['instrument']}.{s['action']}"
        arg_string = ""
        if s['args']:
            if type(s['args']) is dict:
                arg_string = "(" + ", ".join([f"{k} = {v}" for k, v in s['args'].items()]) + ")"
            else:
                arg_string = f"= {s['args']}"

        text = f"{prefix}{action_text}  {arg_string}"
    return dict(label=text, style=style, uuid=s["uuid"], id=s["id"])
