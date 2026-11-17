import unittest

import greet


class GreetTests(unittest.TestCase):
    def test_greet(self):
        self.assertEqual(greet.greet("Ada"), "Hello, Ada.")


if __name__ == "__main__":
    unittest.main()
