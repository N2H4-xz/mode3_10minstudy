import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import web_app
from web_app import (
    COLLECTION_CHAT_SYSTEM,
    COLLECTION_PRESET_TOPIC_QUESTIONS,
    INITIAL_COLLECTION_QUESTION,
    DialogueRequest,
    ManualDialogueRequest,
    ManualStyleForm,
    ScoreRequest,
    UserRequest,
    apply_collection_identity_to_prompt,
    build_collection_messages,
    build_learned_style_messages,
    build_session_learned_prompt,
    build_manual_style_messages,
    build_manual_style_prompt,
    collection_finished,
    new_session,
    next_preset_topic_question,
    normalize_profile_payload,
    normalize_user_id,
    save_collection_identity_for_user,
    save_manual_style_form_for_user,
    save_profile_for_user,
)


class WebAppHelperTests(unittest.TestCase):
    def sample_profile(self):
        return {
            "characteristics": {
                "lexical_complexity": {
                    "key": "lexical_complexity",
                    "label": "词汇复杂度",
                    "value": "用词日常，偶尔有口语词。",
                    "examples": ["还可以吧"],
                    "evidence": "样本中日常词较多。",
                    "confidence": 0.8,
                }
            },
            "raw_stats": {
                "total_messages": 1,
                "avg_chars_per_message": 4,
                "total_chars": 4,
            },
            "source_length_chars": 4,
            "analysis_version": 1,
        }

    def test_collection_finishes_after_400_chars(self):
        self.assertTrue(collection_finished(["a" * 401]))

    def test_collection_soft_limit_requires_turns_and_chars(self):
        self.assertFalse(collection_finished(["a"] * 16))
        self.assertTrue(collection_finished(["a" * 13] * 16))

    def test_initial_collection_question_is_fixed(self):
        self.assertEqual(INITIAL_COLLECTION_QUESTION, "最近有哪些值得分享的事？")
        self.assertEqual(
            COLLECTION_PRESET_TOPIC_QUESTIONS,
            [
                "最近有哪些值得分享的事？",
                "五一怎么过的？",
                "平时喜欢吃什么？",
                "你觉得身边哪一个人最有特点或者最有趣？",
            ],
        )

    def test_collection_chat_uses_friend_perspective(self):
        self.assertIn("好朋友", COLLECTION_CHAT_SYSTEM)
        self.assertIn("不要过度深入", COLLECTION_CHAT_SYSTEM)

    def test_collection_guidance_is_not_added_as_user_sample(self):
        messages = build_collection_messages(
            [
                {"role": "assistant", "content": INITIAL_COLLECTION_QUESTION},
                {"role": "user", "content": "今天有件事挺开心。"},
            ],
            "switch_topic",
        )
        self.assertIn("五一怎么过的？", messages[-1]["content"])
        self.assertEqual(messages[-1]["role"], "user")

    def test_switch_topic_prefers_unused_preset_questions(self):
        dialogue = [
            {"role": "assistant", "content": INITIAL_COLLECTION_QUESTION},
            {"role": "assistant", "content": "五一怎么过的？"},
        ]
        self.assertEqual(next_preset_topic_question(dialogue), "平时喜欢吃什么？")

    def test_manual_prompt_contains_structured_fields_and_limits(self):
        prompt = build_manual_style_prompt(
            ManualStyleForm(
                identity="研一学生",
                language_style="偏犹豫",
                constraints="每次回复不超过 300 字",
            )
        )
        self.assertIn("身份：研一学生", prompt)
        self.assertIn("你觉得自己说话方式是怎样的：偏犹豫", prompt)
        self.assertNotIn("学校/学院/年级/状态", prompt)
        self.assertNotIn("处境：", prompt)
        self.assertNotIn("目标：", prompt)
        self.assertNotIn("开场白：", prompt)
        self.assertIn("每次回复不超过 300 字", prompt)

    def test_user_id_is_sanitized_for_local_file_storage(self):
        self.assertEqual(normalize_user_id("../张三:*?"), "_张三___")

    def test_imported_profile_can_be_attached_to_new_user_session(self):
        with TemporaryDirectory() as tmp:
            old_dir = web_app.USER_DATA_DIR
            old_sessions = web_app.SESSIONS
            web_app.USER_DATA_DIR = Path(tmp)
            web_app.SESSIONS = {}
            try:
                profile = normalize_profile_payload(self.sample_profile())
                record = save_profile_for_user("yao", profile, "yao 风格", "imported")
                session = new_session("yao")
                self.assertEqual(session["stage"], "manual_style")
                self.assertEqual(session["user_id"], "yao")
                self.assertEqual(session["user_profile_id"], record["profile_id"])
                self.assertIsNotNone(session["learned_style_prompt"])
            finally:
                web_app.USER_DATA_DIR = old_dir
                web_app.SESSIONS = old_sessions

    def test_manual_style_form_is_saved_on_user_and_loaded_in_new_session(self):
        with TemporaryDirectory() as tmp:
            old_dir = web_app.USER_DATA_DIR
            old_sessions = web_app.SESSIONS
            web_app.USER_DATA_DIR = Path(tmp)
            web_app.SESSIONS = {}
            try:
                form = ManualStyleForm(
                    identity="学生",
                    language_style="简短直接",
                    constraints="不超过 80 字",
                )
                user = save_manual_style_form_for_user("st", form)
                self.assertEqual(user["manual_style_form"]["language_style"], "简短直接")

                session = new_session("st", force_collect=True)
                self.assertEqual(session["manual_style_form"]["identity"], "学生")
                self.assertEqual(session["manual_style_form"]["constraints"], "不超过 80 字")
            finally:
                web_app.USER_DATA_DIR = old_dir
                web_app.SESSIONS = old_sessions

    def test_collection_identity_is_saved_on_user_and_loaded_in_new_session(self):
        with TemporaryDirectory() as tmp:
            old_dir = web_app.USER_DATA_DIR
            old_sessions = web_app.SESSIONS
            web_app.USER_DATA_DIR = Path(tmp)
            web_app.SESSIONS = {}
            try:
                user = save_collection_identity_for_user("st", "大二学生")
                self.assertEqual(user["collection_identity"], "大二学生")

                session = new_session("st", force_collect=True)
                self.assertEqual(session["collection_identity"], "大二学生")
            finally:
                web_app.USER_DATA_DIR = old_dir
                web_app.SESSIONS = old_sessions

    def test_collection_identity_is_added_to_learned_style_prompt(self):
        base_prompt = "base style prompt"
        prompt = apply_collection_identity_to_prompt(base_prompt, "大二学生")
        self.assertIn("大二学生", prompt)
        self.assertIn(base_prompt, prompt)

        learned_prompt = build_session_learned_prompt(self.sample_profile(), "研一学生")
        self.assertIn("研一学生", learned_prompt)

    def test_raw_user_api_returns_full_saved_user_json(self):
        with TemporaryDirectory() as tmp:
            old_dir = web_app.USER_DATA_DIR
            web_app.USER_DATA_DIR = Path(tmp)
            try:
                save_collection_identity_for_user("st", "大二学生")
                response = web_app.api_user_raw(UserRequest(user_id="st"))
                self.assertEqual(response["user_id"], "st")
                self.assertTrue(response["path"].endswith("st.json"))
                self.assertEqual(response["user_json"]["collection_identity"], "大二学生")
            finally:
                web_app.USER_DATA_DIR = old_dir

    def test_learned_style_messages_include_existing_context(self):
        messages = build_learned_style_messages(
            "system prompt",
            [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "今天挺好"},
                {"role": "tool", "content": "ignored"},
            ],
            "为什么呢",
        )
        self.assertEqual(
            messages,
            [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "今天挺好"},
                {"role": "user", "content": "为什么呢"},
            ],
        )

    def test_manual_style_messages_include_existing_context(self):
        messages = build_manual_style_messages(
            "manual prompt",
            [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "今天挺好"},
                {"role": "system", "content": "ignored"},
            ],
            "为什么呢",
        )
        self.assertEqual(
            messages,
            [
                {"role": "system", "content": "manual prompt"},
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "今天挺好"},
                {"role": "user", "content": "为什么呢"},
            ],
        )

    def test_manual_style_dialogue_appends_multiple_turns_with_context(self):
        old_sessions = web_app.SESSIONS
        old_chat_with_messages = web_app.chat_with_messages
        old_save_manual_style_form_for_user = web_app.save_manual_style_form_for_user
        web_app.SESSIONS = {}
        try:
            session = {
                "session_id": "s1",
                "user_id": "st",
                "manual_style_form": None,
                "manual_style_dialogue": [],
                "learned_style_dialogue": [],
                "score": None,
                "stage": "learned_style",
            }
            web_app.SESSIONS["s1"] = session
            seen_messages = []

            def fake_chat_with_messages(messages):
                seen_messages.append(messages)
                return f"回复：{messages[-1]['content']}"

            web_app.chat_with_messages = fake_chat_with_messages
            web_app.save_manual_style_form_for_user = lambda user_id, form: {"user_id": user_id}
            form = ManualStyleForm(identity="学生", language_style="简短直接", constraints="")

            web_app.api_manual_dialogue(ManualDialogueRequest(session_id="s1", message="第一句", form=form))
            web_app.api_manual_dialogue(ManualDialogueRequest(session_id="s1", message="第二句", form=form))

            self.assertEqual(len(session["manual_style_dialogue"]), 4)
            self.assertEqual(session["stage"], "learned_style")
            self.assertEqual(seen_messages[1][-3:], [
                {"role": "user", "content": "第一句"},
                {"role": "assistant", "content": "回复：第一句"},
                {"role": "user", "content": "第二句"},
            ])
        finally:
            web_app.SESSIONS = old_sessions
            web_app.chat_with_messages = old_chat_with_messages
            web_app.save_manual_style_form_for_user = old_save_manual_style_form_for_user

    def test_learned_style_dialogue_appends_multiple_turns_and_scores_only_learned_style(self):
        old_sessions = web_app.SESSIONS
        old_chat_with_messages = web_app.chat_with_messages
        old_save_session_report = web_app.save_session_report
        web_app.SESSIONS = {}
        try:
            session = {
                "session_id": "s1",
                "user_id": "st",
                "style_profile": self.sample_profile(),
                "learned_style_prompt": "prompt",
                "learned_style_dialogue": [],
                "manual_style_dialogue": [],
                "score": None,
                "stage": "learned_style",
            }
            web_app.SESSIONS["s1"] = session
            seen_messages = []

            def fake_chat_with_messages(messages):
                seen_messages.append(messages)
                return f"回复：{messages[-1]['content']}"

            web_app.chat_with_messages = fake_chat_with_messages
            web_app.save_session_report = lambda _session: {
                "markdown_path": "x.md",
                "json_path": "x.json",
            }

            web_app.api_learned_dialogue(DialogueRequest(session_id="s1", message="第一句"))
            web_app.api_learned_dialogue(DialogueRequest(session_id="s1", message="第二句"))
            self.assertEqual(len(session["learned_style_dialogue"]), 4)
            self.assertEqual(session["stage"], "learned_style")
            self.assertEqual(
                seen_messages[1],
                [
                    {"role": "system", "content": "prompt"},
                    {"role": "user", "content": "第一句"},
                    {"role": "assistant", "content": "回复：第一句"},
                    {"role": "user", "content": "第二句"},
                ],
            )

            web_app.api_score(ScoreRequest(session_id="s1", learned_style_score_0_to_10=8))
            self.assertEqual(session["score"]["learned_style_score_0_to_10"], 8)
            self.assertNotIn("winner", session["score"])
            self.assertNotIn("manual_style_score_0_to_10", session["score"])
        finally:
            web_app.SESSIONS = old_sessions
            web_app.chat_with_messages = old_chat_with_messages
            web_app.save_session_report = old_save_session_report

    def test_score_only_records_dialogue_sides_that_exist(self):
        old_sessions = web_app.SESSIONS
        old_save_session_report = web_app.save_session_report
        web_app.SESSIONS = {}
        try:
            manual_only = {
                "session_id": "manual",
                "user_id": "st",
                "manual_style_dialogue": [
                    {"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "你好呀"},
                ],
                "learned_style_dialogue": [],
                "score": None,
                "stage": "score",
            }
            both = {
                "session_id": "both",
                "user_id": "st",
                "manual_style_dialogue": [
                    {"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "你好呀"},
                ],
                "learned_style_dialogue": [
                    {"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "今天挺好"},
                ],
                "score": None,
                "stage": "score",
            }
            web_app.SESSIONS["manual"] = manual_only
            web_app.SESSIONS["both"] = both
            web_app.save_session_report = lambda _session: {
                "markdown_path": "x.md",
                "json_path": "x.json",
            }

            web_app.api_score(ScoreRequest(session_id="manual", manual_style_score_0_to_10=7))
            self.assertEqual(manual_only["score"]["manual_style_score_0_to_10"], 7)
            self.assertNotIn("learned_style_score_0_to_10", manual_only["score"])
            self.assertNotIn("winner", manual_only["score"])

            web_app.api_score(ScoreRequest(
                session_id="both",
                manual_style_score_0_to_10=6,
                learned_style_score_0_to_10=8,
            ))
            self.assertEqual(both["score"]["manual_style_score_0_to_10"], 6)
            self.assertEqual(both["score"]["learned_style_score_0_to_10"], 8)
            self.assertEqual(both["score"]["winner"], "learned_style")
        finally:
            web_app.SESSIONS = old_sessions
            web_app.save_session_report = old_save_session_report


if __name__ == "__main__":
    unittest.main()
