import inspect
import json
import os
import re

# import ollama
from dotenv import load_dotenv
from openai import OpenAI
load_dotenv()

# host = "137.82.65.246"
# model = "llama3"


class LlmAgent:
    def __init__(self, model="llama3", output_path=os.curdir, host=None):
        self.host = host
        self.base_url = f"http://{self.host}:11434/v1/" if host is not None else ""
        self.model = model
        self.output_path = os.path.join(output_path, "llm_output")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if host is None else OpenAI(api_key="ollama", base_url=self.base_url)
        os.makedirs(self.output_path, exist_ok=True)



    def extract_annotations_docstrings(self, cls):
        extracted_methods = []
        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if not name.startswith('_'):
                annotation = inspect.signature(method).return_annotation
                docstring = inspect.getdoc(method)
                extracted_methods.append((name, annotation, docstring))
        method_name = [t[0] for t in extracted_methods]
        variables = [(key, value) for key, value in vars(cls).items() if
                     not key.startswith("_") and not key in method_name]
        class_str = ""
        # class_str = f"class {cls.__name__}:\n"
        # class_str += f'\t"""{inspect.getdoc(cls)}"""\n\n'
        for key, value in variables:
            class_str += f'\t{key}={value}\n'
        for name, annotation, docstring in extracted_methods:
            class_str += f'\tdef {name}{inspect.signature(getattr(cls, name))}:\n'
            class_str += f'\t\t"""\n{docstring}\n"""' + '\n\n' if docstring else ''
        class_str = class_str.replace('self, ', '')
        class_str = class_str.replace('self', '')
        name_list = [name for name, _, _ in extracted_methods]
        # print(class_str)
        current_path = os.path.curdir
        with open(os.path.join(self.output_path, "docstring_manual.txt"), "w") as f:
            f.write(class_str)

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

    def _generate(self, robot, prompt):
        deck_info, name_list = self.extract_annotations_docstrings(type(robot))
        full_prompt = '''
                                I have some python functions, for example when calling them I want to write them using JSON, 
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

        with open(os.path.join(self.output_path, "prompt.txt"), "w") as f:
            f.write(full_prompt)
        messages = [{"role": "user",
                     "content": full_prompt}]
        # if self.host == "openai":
        output = self.client.chat.completions.create(
            messages=messages,
            model=self.model,
        )
        msg = output.choices[0].message.content

        # else:
        #     output = self.client.chat(
        #         model=self.model,
        #         messages=messages,
        #         # stream=False,
        #     )
        #     msg = output['message']['content']
        # print(msg)

        code = self.parse_code_from_msg(msg)
        code = [action for action in code if action['action'] in name_list]
        # print('\033[91m', code, '\033[0m')
        return code

    def generate_code(self, robot, prompt, attempt_allowance:int=3):
        attempt = 0
        while attempt < attempt_allowance:
            code = self._generate(robot, prompt)
            attempt += 1
            if code:
                break

        print(attempt)
        return code






if __name__ == "__main__":
    from example.dummy_ur.dummy_deck import deck
    # llm_agent = LlmAgent(host="openai", model="gpt-3.5-turbo")
    llm_agent = LlmAgent(host="localhost", model="llama3.1")
    # robot = IrohDeck()
    # extract_annotations_docstrings(DummySDLDeck)
    prompt = '''I want to start with dosing 10 mg of current sample, and add 1 mL of toluene 
    and equilibrate for 10 minute at 40 degrees, then sample 20 ul of sample to analyze with hplc, and save result'''
    code = llm_agent.generate_code(deck, prompt)
    print(code)
"""
I want to dose 10mg, 6mg, 4mg, 3mg, 2mg, 1mg to 6 vials
I want to add 10 mg to vial a3, and 10 ml of liquid, then shake them for 3 minutes

"""
