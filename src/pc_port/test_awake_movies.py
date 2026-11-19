import struct
import unittest

import awake_movies
import omake_assets
from build_mod import MOD_FILES
from port_scripts import PS2_MOVIE_MAP


def instruction(data, ip):
    op = struct.unpack_from("<I", data, ip)[0]
    args = struct.unpack_from(f"<{(op & 255) - 1}I", data, ip + 4)
    return op, args, ip + (op & 255) * 4


class AwakeMovieTests(unittest.TestCase):
    def setUp(self):
        self.scenario = bytearray(0x42F900)
        struct.pack_into("<I", self.scenario, 0x42F354, 0x0102010A)
        struct.pack_into("<I", self.scenario, 0x42F390, 0x0102010A)
        struct.pack_into("<I", self.scenario, 0x42F8E4, 0x42F8F8)
        self.names = []

        def ensure(name):
            if name not in self.names:
                self.names.append(name)
            return self.names.index(name) + 1

        def patch(offset, expected, value, description):
            self.assertEqual(struct.unpack_from("<I", self.scenario, offset)[0], expected)
            struct.pack_into("<I", self.scenario, offset, value)

        def emit(ops):
            start = len(self.scenario)
            for op, args in ops:
                self.assertEqual(op & 255, len(args) + 1)
                self.scenario.extend(struct.pack(f"<{len(args) + 1}I", op, *args))
            return start

        self.original = bytes(self.scenario)
        omake_assets.patch_movie_theater(self.scenario, ensure, patch, emit)

    def play_choice(self, choice):
        ip = struct.unpack_from("<I", self.scenario, 0x42F8E4)[0]
        registers = {0x30000000: choice}
        movies = []
        for _ in range(30):
            if ip == 0x42F8F8:
                return movies
            op, args, next_ip = instruction(self.scenario, ip)
            if op == 0x02000103:
                registers[args[0]] = args[1]
            elif op == 0x02010003:
                registers[args[0]] = int(registers[args[0]] == registers[args[1]])
            elif op == 0x01000703:
                if not registers[args[0]]:
                    next_ip = args[1]
            elif op == 0x05030002:
                movies.append(self.names[args[0] - 1])
            elif op == 0x01000202:
                next_ip = args[0]
            else:
                self.fail(f"Unexpected movie dispatch opcode {op:#x}")
            ip = next_ip
        self.fail("Movie dispatch did not return")

    def test_replay_choices_select_the_correct_movie_and_return(self):
        for choice, expected in ((20, "POP22.DAT"), (21, "POP23.DAT"), (22, "POP24.DAT")):
            with self.subTest(choice=choice):
                self.assertEqual(self.play_choice(choice), [expected])
        self.assertEqual(self.play_choice(999), [])

    def test_original_movie_dispatch_is_unchanged(self):
        self.assertEqual(self.scenario[0x42F510:0x42F8DC], self.original[0x42F510:0x42F8DC])

    def test_new_buttons_share_the_existing_footer_cleanup(self):
        ip = struct.unpack_from("<I", self.scenario, 0x42F394)[0]
        buttons = []
        while True:
            op, args, ip = instruction(self.scenario, ip)
            if op == 0x01000202:
                self.assertEqual(args[0], 0x42F3B8)
                break
            self.assertEqual(op, 0x0102010A)
            buttons.append(args)
        self.assertEqual([(a[0], a[1]) for a in buttons], [(5, 1), (5, 2), (5, 3)])
        for args, movie in zip(buttons[1:], awake_movies.OPENINGS):
            self.assertEqual(self.names[args[7] - 1], movie[3])
            self.assertGreaterEqual(args[3], 497)
            self.assertLessEqual(args[5], 564)
            op, callback_args, _ = instruction(self.scenario, args[8])
            self.assertEqual((op, callback_args), (0x02000103, (0x30000000, movie[2])))

    def test_startup_preserves_logo_wait_and_resumes_title(self):
        scenario = bytearray(0x200)
        struct.pack_into("<2I", scenario, 0x1C8, 0x01000502, 1000)
        awake_movies.patch_startup_movie(scenario, 42)
        op, args, _ = instruction(scenario, 0x1C8)
        self.assertEqual(op, 0x01000202)
        ip = args[0]
        expected = [(0x01000502, (1000,)),
                    (0x02000103, (0x30000000, 0)),
                    (0x02000103, (awake_movies.TITLE_NEXT_DEMO_VAR, 0x30000000)),
                    (0x05000102, (0,)),
                    (0x05030002, (42,)), (0x01000202, (0x1D0,))]
        for expected_op, expected_args in expected:
            op, args, ip = instruction(scenario, ip)
            self.assertEqual((op, args), (expected_op, expected_args))

    def test_openings_use_mod_only_filenames_in_scripts_and_installer(self):
        self.assertEqual(awake_movies.TITLE_IDLE_MOVIES,
                         ("POP24.DAT", "POP00.DAT", "POP07.DAT", "POP23.DAT"))
        for index, filename, _, _, _ in awake_movies.OPENINGS:
            self.assertEqual(PS2_MOVIE_MAP[index, 0], filename)
            self.assertIn(filename, awake_movies.MOD_MOVIES)
            self.assertTrue(any(path.replace("\\", "/") == f"exp/{filename}" for path in MOD_FILES))
            self.assertGreater(int(filename[3:5]), 20)


class TitleIdleMovieTests(unittest.TestCase):
    def setUp(self):
        self.scenario = bytearray(0x2000)
        struct.pack_into("<2I", self.scenario, 0x1C8, 0x01000502, 1000)
        struct.pack_into("<2I", self.scenario, 0x4EC, 0x01020002, 3)
        struct.pack_into("<4I", self.scenario, 0x758, 0x80010004, 0, 1000, 0)
        struct.pack_into("<2I", self.scenario, 0x768, 0x02020102, 3)
        struct.pack_into("<2I", self.scenario, 0x770, 0x01000202, 0x714)
        struct.pack_into("<I", self.scenario, 0x74C, 0x778)
        awake_movies.patch_startup_movie(self.scenario, 41)
        awake_movies.patch_title_idle_movies(self.scenario, (43, 42, 44, 41))
        self.state = {}
        self.movies = []
        self.cleanup_calls = 0
        self.elapsed_ms = 0

    def run_script(self, ip):
        def value(arg):
            return self.state.get(arg, 0) if arg >= 0x10000000 else arg

        for _ in range(100):
            if ip in (0x1D0, 0x4F4, 0x714, 0x4B8, 0x778):
                return ip
            op, args, next_ip = instruction(self.scenario, ip)
            if op == 0x02000103:
                self.state[args[0]] = value(args[1])
            elif op == 0x02000203:
                self.state[args[0]] += value(args[1])
            elif op == 0x02010003:
                self.state[args[0]] = int(value(args[0]) == value(args[1]))
            elif op == 0x01000703:
                if not value(args[0]):
                    next_ip = args[1]
            elif op == 0x01000202:
                next_ip = args[0]
            elif op == 0x05030002:
                self.movies.append(args[0])
            elif op == 0x01000302:
                self.assertEqual(args[0], 0x101C)
                self.cleanup_calls += 1
            elif op == 0x01000502:
                if not self.state.get(0x20000226, 0):
                    self.elapsed_ms += args[0]
            elif op == 0x80010004:
                # Native state 8 with target 0 only yields to rendering; it
                # does not set a timeGetTime deadline from args[1].
                self.elapsed_ms += 33 if args[0] == 0 else args[1]
            elif op not in (0x01020002, 0x02020102, 0x05000102, 0x80010102):
                self.fail(f"Unexpected title opcode {op:#x}")
            ip = next_ip
        self.fail("Title script failed to yield or return")

    def test_title_poll_uses_a_real_one_second_wait(self):
        op, args, ip = instruction(self.scenario, 0x758)
        self.assertEqual((op, args), (0x01000502, (1000,)))
        self.assertEqual(instruction(self.scenario, ip)[:2],
                         (0x01000202, (0x768,)))

    def test_elapsed_time_includes_every_title_wait_before_opening(self):
        for expected_movie in (43, 42, 44, 41, 43):
            self.run_script(0x4EC)
            started = self.elapsed_ms
            previous_count = len(self.movies)
            for seconds in range(1, 30):
                self.run_script(0x758)
                self.assertEqual(self.elapsed_ms - started, seconds * 1000)
                self.assertEqual(len(self.movies), previous_count)
            self.assertEqual(self.run_script(0x758), 0x4B8)
            self.assertGreaterEqual(self.elapsed_ms - started, 30000)
            self.assertEqual(self.movies[-1], expected_movie)

    def test_menu_click_interrupts_timed_wait_without_starting_demo(self):
        self.run_script(0x4EC)
        self.state[awake_movies.TITLE_IDLE_VAR] = 29
        self.state[0x20000226] = 1
        self.assertEqual(self.run_script(0x758), 0x714)
        self.assertEqual(self.elapsed_ms, 0)
        self.assertEqual(self.movies, [])
        menu_ip = struct.unpack_from("<I", self.scenario, 0x74C)[0]
        self.assertEqual(self.run_script(menu_ip), 0x778)
        self.assertEqual(self.state[awake_movies.TITLE_IDLE_VAR], 0)

    def test_startup_plays_awake_op1_and_resets_demo_order(self):
        self.state[awake_movies.TITLE_NEXT_DEMO_VAR] = 1
        self.assertEqual(self.run_script(0x1C8), 0x1D0)
        self.assertEqual(self.movies, [41])
        self.assertEqual(self.state[awake_movies.TITLE_NEXT_DEMO_VAR], 0)

    def test_title_waits_then_rotates_all_four_openings(self):
        for expected_movie in (43, 42, 44, 41, 43):
            self.run_script(0x4EC)
            previous_count = len(self.movies)
            for _ in range(awake_movies.TITLE_IDLE_SECONDS - 1):
                self.assertEqual(self.run_script(0x770), 0x714)
            self.assertEqual(len(self.movies), previous_count)
            self.assertEqual(self.run_script(0x770), 0x4B8)
            self.assertEqual(self.movies[-1], expected_movie)
        self.assertEqual(self.cleanup_calls, 5)

    def test_menu_click_takes_priority_at_demo_deadline(self):
        self.run_script(0x4EC)
        self.state[awake_movies.TITLE_IDLE_VAR] = awake_movies.TITLE_IDLE_SECONDS - 1
        self.state[0x20000226] = 1
        self.assertEqual(self.run_script(0x770), 0x714)
        self.assertEqual(self.movies, [])
        self.assertEqual(self.cleanup_calls, 0)
        # The title's menu branch must reset the counter even if an exit
        # confirmation is cancelled without recreating the title buttons.
        menu_ip = struct.unpack_from("<I", self.scenario, 0x74C)[0]
        self.assertEqual(self.run_script(menu_ip), 0x778)
        self.assertEqual(self.state[awake_movies.TITLE_IDLE_VAR], 0)

    def test_returning_from_menu_resets_timer_without_resetting_sequence(self):
        self.state[awake_movies.TITLE_IDLE_VAR] = 29
        self.state[awake_movies.TITLE_NEXT_DEMO_VAR] = 1
        self.assertEqual(self.run_script(0x4EC), 0x4F4)
        self.assertEqual(self.state[awake_movies.TITLE_IDLE_VAR], 0)
        self.assertEqual(self.state[awake_movies.TITLE_NEXT_DEMO_VAR], 1)


if __name__ == "__main__":
    unittest.main()
