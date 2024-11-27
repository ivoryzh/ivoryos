import inspect
import json
import os
import re

from openai import OpenAI


# from dotenv import load_dotenv
# load_dotenv()

# host = "137.82.65.246"
# model = "llama3"

# structured output,
# class Action(BaseModel):
#     action: str
#     args: dict
#     arg_types: dict
#
#
# class ActionPlan(BaseModel):
#     actions: list[Action]
#     # final_answer: str


class LlmAgent:
    def __init__(self, model="llama3", output_path=os.curdir, host=None):
        self.host = host
        self.base_url = f"http://{self.host}:11434/v1/" if host is not None else ""
        self.model = model
        self.output_path = os.path.join(output_path, "llm_output") if output_path is not None else None
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if host is None else OpenAI(api_key="ollama",
                                                                                              base_url=self.base_url)
        if self.output_path is not None:
            os.makedirs(self.output_path, exist_ok=True)

    @staticmethod
    def extract_annotations_docstrings(module_sigs):
        class_str = ""

        for name, value in module_sigs.items():
            signature = value.get("signature")
            docstring = value.get("docstring")
            class_str += f'\tdef {name}{signature}:\n'
            class_str += f'\t\t"""\n\t\t{docstring}\n\t\t"""' + '\n' if docstring else ''
        class_str = class_str.replace('self, ', '')
        class_str = class_str.replace('self', '')
        name_list = list(module_sigs.keys())
        # print(class_str)
        # with open(os.path.join(self.output_path, "docstring_manual.txt"), "w") as f:
        #     f.write(class_str)
        return class_str, name_list

    @staticmethod
    def parse_code_from_msg(msg):
        msg = msg.strip()
        # print(msg)
        # code_blocks = re.findall(r'```(?:json\s)?(.*?)```', msg, re.DOTALL)
        code_blocks = re.findall(r'\[\s*\{.*?\}\s*\]', msg, re.DOTALL)

        json_blocks = []
        for block in code_blocks:
            if not block.startswith('['):
                start_index = block.find('[')
                block = block[start_index:]
            block = re.sub(r'//.*', '', block)
            block = block.replace('True', 'true').replace('False', 'false')
            try:
                # Try to parse the block as JSON
                json_data = json.loads(block.strip())
                if isinstance(json_data, list):
                    json_blocks = json_data
            except json.JSONDecodeError:
                continue
        return json_blocks

    def _generate(self, robot_sigs, prompt):
        # deck_info, name_list = self.extract_annotations_docstrings(type(robot))
        deck_info, name_list = self.extract_annotations_docstrings(robot_sigs)
        full_prompt = '''I have some python functions, for example when calling them I want to write them using JSON, 
it is necessary to include all args
for example
def dose_solid(amount_in_mg:float, bring_in:bool=True): def analyze():
dose_solid(3)
analyze()
I would want to write to
[
{
    "action": "dose_solid",
    "arg_types": {
        "amount_in_mg": "float",
        "bring_in": "bool"
    },
    "args": {
        "amount_in_mg": 3,
        "bring_in": true
    }
},
{
    "action": "analyze",
    "arg_types": {},
    "args": {}
}
]
''' + f'''
Now these are my callable functions,
{deck_info}
and I want you to find the most appropriate function if I want to do these tasks
"""{prompt}"""
,and write a list of dictionary in json accordingly. Please only use these action names {name_list}, 
can you also help find the default value you can't find the info from my request.
'''
        if self.output_path is not None:
            with open(os.path.join(self.output_path, "prompt.txt"), "w") as f:
                f.write(full_prompt)
        messages = [{"role": "user",
                     "content": full_prompt}, ]
        # if self.host == "openai":
        output = self.client.chat.completions.create(
            messages=messages,
            model=self.model,
            # response_format={"type": "json_object"},
        )
        msg = output.choices[0].message.content
        # msg = output.choices[0].message.parsed

        code = self.parse_code_from_msg(msg)
        code = [action for action in code if action.get('action', '') in name_list]
        # print('\033[91m', code, '\033[0m')
        return code

    def generate_code(self, robot_signature, prompt, attempt_allowance: int = 3):
        attempt = 0

        while attempt < attempt_allowance:
            _code = self._generate(robot_signature, prompt)
            attempt += 1
            if _code:
                break

        return self.fill_blanks(_code, robot_signature)
        # return code

    @staticmethod
    def fill_blanks(actions, robot_signature):
        for action in actions:
            action_name = action['action']
            action_signature = robot_signature.get(action_name).get('signature', {})
            args = action.get("args", {})
            arg_types = action.get("arg_types", {})
            for param in action_signature.parameters.values():
                if param.name == 'self':
                    continue
                if param.name not in args:
                    args[param.name] = param.default if param.default is not param.empty else ''
                    arg_types[param.name] = param.annotation.__name__
            action['args'] = args
            action['arg_types'] = arg_types
        return actions


if __name__ == "__main__":
    from pprint import pprint
    from example.sdl_example.abstract_sdl import deck

    from utils import parse_functions

    deck_sig = parse_functions(deck, doc_string=True)
    # llm_agent = LlmAgent(host="openai", model="gpt-3.5-turbo")
    llm_agent = LlmAgent(host="localhost", model="llama3.1")
    # robot = IrohDeck()
    # extract_annotations_docstrings(DummySDLDeck)
    prompt = '''I want to start with dosing 10 mg of current sample, and add 1 mL of toluene 
    and equilibrate for 10 minute at 40 degrees, then sample 20 ul of sample to analyze with hplc, and save result'''
    code = llm_agent.generate_code(deck_sig, prompt)
    pprint(code)

"""
I want to dose 10mg, 6mg, 4mg, 3mg, 2mg, 1mg to 6 vials
I want to add 10 mg to vial a3, and 10 ml of liquid, then shake them for 3 minutes

"""
