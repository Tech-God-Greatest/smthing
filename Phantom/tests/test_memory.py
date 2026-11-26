import unittest
import json
from tools.memory_tools import remember, forget, update_memory, search_memory, _memory


class TestMemoryTools(unittest.TestCase):
    """Unit test suite for memory tools."""

    def setUp(self):
        # Save state and clean test entries
        self.category = "test_category"
        self.key = "test_key"
        self.val = "test_value"
        if self.category in _memory:
            del _memory[self.category]

    def tearDown(self):
        if self.category in _memory:
            del _memory[self.category]

    def test_remember_and_search(self):
        res = remember(self.category, self.key, self.val)
        self.assertIn("Remembered", res)
        mem_str = search_memory()
        mem_data = json.loads(mem_str)
        self.assertIn(self.category, mem_data)
        self.assertEqual(mem_data[self.category].get(self.key), self.val)

    def test_update_memory(self):
        remember(self.category, self.key, self.val)
        new_val = "updated_value"
        res = update_memory(self.category, self.key, new_val)
        self.assertIn("Updated", res)
        mem_data = json.loads(search_memory())
        self.assertEqual(mem_data[self.category].get(self.key), new_val)

    def test_forget_memory(self):
        remember(self.category, self.key, self.val)
        res = forget(self.category, self.key)
        self.assertIn("Forgot", res)
        mem_data = json.loads(search_memory())
        self.assertNotIn(self.category, mem_data)


if __name__ == "__main__":
    unittest.main()

