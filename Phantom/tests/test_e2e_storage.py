import pytest
import os
import sys
import threading

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from storage import storage

class TestE2EStorage:

    def test_01_create_and_save_messages(self, fresh_chat):
        storage.save_message(fresh_chat, "user", "Hello Phantom")
        storage.save_message(fresh_chat, "assistant", "Hello User")
        
        msgs = storage.get_recent_messages(fresh_chat)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Hello Phantom"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "Hello User"

    def test_02_save_100_messages(self, fresh_chat):
        for i in range(100):
            storage.save_message(fresh_chat, "user", f"Msg {i}")
        
        msgs = storage.get_recent_messages(fresh_chat, limit=50)
        assert len(msgs) == 50
        # The oldest in the 50 should be Msg 50, newest Msg 99
        assert msgs[0]["content"] == "Msg 50"
        assert msgs[-1]["content"] == "Msg 99"

    def test_03_update_chat_title(self, fresh_chat):
        storage.update_chat_title(fresh_chat, "Updated Title")
        chats = storage.list_chats(show_archived=True)
        my_chat = next(c for c in chats if c["id"] == fresh_chat)
        assert my_chat["title"] == "Updated Title"

    def test_04_update_chat_summary(self, fresh_chat):
        storage.update_chat_summary(fresh_chat, "This is a summary")
        summary = storage.get_chat_summary(fresh_chat)
        assert summary == "This is a summary"

    def test_05_archive_chat(self, fresh_chat):
        storage.archive_chat(fresh_chat, True)
        chats_not_archived = storage.list_chats(show_archived=False)
        assert not any(c["id"] == fresh_chat for c in chats_not_archived)
        
        chats_archived = storage.list_chats(show_archived=True)
        my_chat = next(c for c in chats_archived if c["id"] == fresh_chat)
        assert my_chat["is_archived"] == 1

    def test_06_delete_chat(self, fresh_chat):
        # We need a chat we can safely delete without messing up fresh_chat teardown, 
        # so let's create a temporary one.
        chat_id = storage.create_chat("To Delete")
        storage.save_message(chat_id, "user", "Delete me")
        
        storage.delete_chat(chat_id)
        
        chats = storage.list_chats(show_archived=True)
        assert not any(c["id"] == chat_id for c in chats)
        
        msgs = storage.get_recent_messages(chat_id)
        assert len(msgs) == 0

    def test_07_export_chat_json(self, fresh_chat):
        storage.update_chat_title(fresh_chat, "JSON Export Chat")
        storage.update_chat_summary(fresh_chat, "Summary json")
        storage.save_message(fresh_chat, "user", "Hello JSON")
        
        export_str = storage.export_chat(fresh_chat, "json")
        assert '"title": "JSON Export Chat"' in export_str
        assert '"summary": "Summary json"' in export_str
        assert '"content": "Hello JSON"' in export_str

    def test_08_export_chat_md(self, fresh_chat):
        storage.update_chat_title(fresh_chat, "MD Export Chat")
        storage.save_message(fresh_chat, "user", "Hello MD")
        
        export_str = storage.export_chat(fresh_chat, "md")
        assert "# MD Export Chat" in export_str
        assert "### User" in export_str
        assert "Hello MD" in export_str

    def test_09_export_chat_txt(self, fresh_chat):
        storage.update_chat_title(fresh_chat, "TXT Export Chat")
        storage.save_message(fresh_chat, "user", "Hello TXT")
        
        export_str = storage.export_chat(fresh_chat, "txt")
        assert "=== TXT Export Chat ===" in export_str
        assert "] You:" in export_str
        assert "Hello TXT" in export_str

    def test_10_search_chats_by_title(self, fresh_chat):
        storage.update_chat_title(fresh_chat, "Unique Searchable Title 123")
        chats = storage.list_chats(search_query="Unique Searchable", show_archived=True)
        assert any(c["id"] == fresh_chat for c in chats)

    def test_11_search_chats_by_content(self, fresh_chat):
        storage.save_message(fresh_chat, "user", "Unique secret message content 456")
        chats = storage.list_chats(search_query="secret message content", show_archived=True)
        assert any(c["id"] == fresh_chat for c in chats)

    def test_12_concurrent_saves(self, fresh_chat):
        def save_worker(thread_id):
            for i in range(20):
                storage.save_message(fresh_chat, "user", f"Msg {thread_id}-{i}")
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=save_worker, args=(i,))
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        msgs = storage.get_recent_messages(fresh_chat, limit=200)
        assert len(msgs) >= 100  # might be more if other tests ran in same chat, but we used fresh_chat
