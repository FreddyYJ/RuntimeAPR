import os
import sys
from openai import OpenAI

seed = 57


class RepairRunner:
    def __init__(self, program_file: str, exception: str):
        """
        :param program_file: file name of the buggy function
        :param exception: the exception that was raised
        """
        self.program_file = program_file
        self.exception = exception
        self.openai_client = OpenAI()

    def repair(self):
        # Generate patches with OpenAI
        with open(self.program_file, "r") as fd:
            code = fd.read()
        completion = self.openai_client.chat.completions.create(
            model='gpt-4',
            seed=seed,
            messages=[
                {
                    'role': 'system',
                    'content': 'You are a good software engineer. Fix the provided Python code to avoid exception.',
                },
                {
                    'role': 'user',
                    'content': f'''When I run this program, it throws {self.exception}. Please fix {self.exception} in this function.
```Python
{code}
```
1. Respond fixed program ONLY.''',
                },
            ],
        )
        resp = completion.choices[0].message.content
        resp = resp[resp.find('```Python\n') + 10 : resp.rfind('```')]

        return resp


if __name__ == "__main__":
    program_file = sys.argv[1]
    program_exception = sys.argv[2]
    repair = RepairRunner(program_file, program_exception)
    if len(sys.argv) >= 4:
        result = repair.repair()
        with open(sys.argv[3], "w") as fd:
            print(result, file=fd)
    else:
        print(repair.repair())
