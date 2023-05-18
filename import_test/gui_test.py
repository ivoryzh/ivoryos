import time

import repackage
repackage.up()
from import_test.test_inner import TestInner


class MyTest:

    def __init__(self, arg1: TestInner, arg2: int = 0):
        self.inner = arg1
        self.a = arg2

    def test1(self):
        time.sleep(3)
        print("Test1: no arg ", self.inner.a)

    def test2_return_test(self, arg1: int = 2, arg2: str = "4"):
        print("Test2: Testing for None default", arg1)
        return arg2
    def test3_arg_required(self, arg1: int):
        print("Test3: Testing required arg", arg1)

    def test4(self, arg1: int = None):
        print("Test4: Testing for None default", arg1)

    def test5(self, arg1:bool= False):
        print("Test5: Testing for boolean input\nValue:", arg1, "   Type: ", type(arg1))

    def test6_another_bool(self, arg_542398:bool):
        print("Test5: Testing for boolean input\nValue:", arg_542398, "   Type: ", type(arg_542398))
