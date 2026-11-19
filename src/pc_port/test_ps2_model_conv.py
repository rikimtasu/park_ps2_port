import re
import struct
import unittest

import ps2_model_conv


def pc_def_tokens(data: bytes) -> list[bytes]:
    # P_ARK201.exe's line reader (0x48FEC0) stops only at CRLF. Its
    # tokenizer (0x490000) discards the rest of that physical line at //.
    lines = [line.split(b"//", 1)[0] for line in data.split(b"\r\n")]
    return re.findall(rb"[^ ,\t\n{}()\[\]&=<>!]+|[{}()\[\]&=<>!]", b"\n".join(lines))


class RuahDefTests(unittest.TestCase):
    def setUp(self):
        bones = [{"name": f"b{i:02d}"} for i in range(49)]
        # One PS2-only team motion exercises the appended-block path too.
        ps2_def = struct.pack("<4s3I", b"DEF\0", 1, 16, 0)
        ps2_def += struct.pack("<32sHH3I", b"LUAH_TA_01", 0, 61, 0, 0, 0)
        template = (
            "motion BASE {\r\n"
            "    DMO_motion BASE\r\n"
            "    category 1\r\n"
            "    jump VOID 49 0\r\n"
            "}\r\n"
            "motion FEL_GUARD {\r\n"
            "    DMO_motion DEFENCE\r\n"
            "}\r\n"
            "motion DAMAGE_FALCON_ATTACK1 {\r\n"
            "    DMO_motion DAMAGE\r\n"
            "    event VOID 1 1 EVENT_RANDOM_SOUND:1:01003:127\r\n"
            "    event VOID 60 60 EVENT_END\r\n"
            "    jump VOID 60 0 motion(BASE)\r\n"
            "}\r\n"
        )
        self.data = ps2_model_conv.build_ruah_def(
            bones, ps2_def, ["ATTACK1.mtn"],
            {"BASE": 41, "ATTACK1": 131, "DAMAGE": 117}, template,
        )

    def test_all_lines_use_pc_line_endings(self):
        remaining = self.data.replace(b"\r\n", b"")
        self.assertEqual(remaining.count(b"\n"), 0, "DEF contains bare LF line endings")
        self.assertEqual(remaining.count(b"\r"), 0, "DEF contains bare CR line endings")

    def test_pc_reader_sees_action_completion_and_return_to_base(self):
        for name in (
            "LUAH_AK_01", "LUAH_SP_01", "LUAH_SP_02", "FEL_MAGICAL_HAMMER",
            "BOUGYO", "FEL_GUARD", "JOUKYU_BOUGYO", "FEL_JOUKYU_GUARD",
            "LUAH_TA_01", "DAMAGE_FALCON_ATTACK1",
        ):
            with self.subTest(motion=name):
                match = re.search(
                    rb"motion\s+" + name.encode("ascii") + rb"\s*\{(.*?)\n\}",
                    self.data, re.S,
                )
                self.assertIsNotNone(match)
                tokens = pc_def_tokens(match.group(1))
                self.assertIn(b"EVENT_END", tokens)
                self.assertIn(b"jump", tokens)
                self.assertIn(b"BASE", tokens)

    def test_pc_reader_catches_lf_body_hidden_by_comment(self):
        malformed = (
            b"DMO_motion SA_ATTACK\n// voice\n"
            b"event VOID 300 300 EVENT_END\njump VOID 300 0 motion(BASE)\r\n"
        )
        self.assertNotIn(b"EVENT_END", pc_def_tokens(malformed))
        fixed = malformed.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        self.assertIn(b"EVENT_END", pc_def_tokens(fixed))

    def test_template_motion_and_voice_remapping_are_preserved(self):
        self.assertIn(b"jump VOID 49 0\r\n", self.data)
        self.assertIn(b"EVENT_RANDOM_SOUND:1:01009:127", self.data)


if __name__ == "__main__":
    unittest.main()
