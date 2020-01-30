import configparser
import errno
import logging
import os.path
import time
import types

import pandas as pd

from chagtriviabot.chat import Chat
from chagtriviabot.helpers import pluralize, try_parse_int64
from chagtriviabot.scoretracker import ScoreTracker
from chagtriviabot.triviasession import TriviaSession

CONFIG_PATH = "config.ini"
SCORES_PATH = "userscores.txt"
LOG = logging.getLogger("Trivia")

class ChagTriviaBot:
    CMDS = ["triviastart", "triviaend", "top", "score", "next", "stop",
            "loadconfig"]
    POS = ["1st", "2nd", "3rd"]

    def __init__(self):
        LOG.info("Bot starting...")
        self.name = "Chag Trivia Bot"
        self.version = "0.2.0"
        self.is_loaded = False
        self.is_running = False
        self.chat = Chat(self)
        self.scores = ScoreTracker()
        self.var = types.SimpleNamespace()

        ###############################################################
        # Trivia variables
        ###############################################################
        # Flag for when trivia is being played
        self.is_active = False
        # Flag for when a question is actively being asked
        self.question_asked = False
        self.session = TriviaSession()
        # Time when the last question was asked
        self.ask_time = 0
        # Ongoing active timer
        self.timer = 0

    ###################################################################
    # Backend
    ###################################################################
    def load_config(self):
        if not os.path.exists(CONFIG_PATH):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),
                                    CONFIG_PATH)
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH)
        self.chat.set_config(config["Bot"])
        self.set_variables(config)
        LOG.info("Config loaded.")

    def load_scores(self):
        self.scores.load(SCORES_PATH)
        LOG.info("Scores loaded.")

    def set_variables(self, config):
        try:
            self.set_trivia_variables(config["Trivia"])
            self.set_admin_variables(config["Admin"])
            self.is_loaded = True
        except (KeyError, ValueError):
            LOG.error("Config not loaded! Check config file and reboot bot.")
            self.is_loaded = False

    def set_trivia_variables(self, config):
        self.var.PREFIX = config["prefix"]
        filename = config["filename"]
        filetype = config["filetype"]
        self.var.num_qs = int(config["num_qs"])
        self.var.delay = int(config["delay"])
        self.var.hint_time_1 = int(config["hint_time_1"])
        self.var.hint_time_2 = int(config["hint_time_2"])
        self.var.skip_time = int(config["skip_time"])
        self.var.correct = config["correct"]
        self.var.wrong = config["wrong"]

        # open trivia source based on type
        if filetype == "csv":
            self.var.ts = pd.read_csv(f"{filename}.{filetype}")
        elif filetype in ("xlsx", "xls"):
            self.var.ts = pd.read_excel(f"{filename}.{filetype}")
        else:
            LOG.error("Invalid filetype.")
            raise ValueError

        # Dynamic # of rows based on triviaset
        self.var.tsrows = self.var.ts.shape[0]
        # Set columns in quizset to same as triviaset
        self.session.reset(self.var.ts.columns)

        if self.var.tsrows < self.var.num_qs:
            self.var.num_qs = self.var.tsrows
            LOG.warning("Trivia questions for session exceeds trivia set's "
                        "population. Setting session equal to max questions.")

    def set_admin_variables(self, config):
        self.var.ADMINS = config["admins"].split(",")

    def prepare(self):
        self.load_config()
        self.load_scores()
        self.is_running = (self.chat.is_ready() and self.scores.is_ready()
                           and self.is_ready())

    def stop(self):
        self.is_running = False

    def run(self):
        if self.is_running:
            try:
                self.chat.connect()
                self.chat.send_msg(f"{self.name} v{self.version} loaded!")
            except (OSError,):
                LOG.error("Connection failed. Check config file and reboot "
                          "bot.")
                self.is_running = False
        else:
            LOG.error("Bot NOT running! Check the errors and reboot bot.")

        while self.is_running:
            if self.is_active:
                self.routine_check()
            self.chat.scanloop()

    ###################################################################
    # Boolean checks
    ###################################################################
    def is_ready(self):
        return self.is_loaded

    def is_admin(self, username):
        return username in self.var.ADMINS

    def exceed_time(self, timing):
        return self.timer - self.ask_time > timing

    ###################################################################
    # Interaction code
    ###################################################################
    def process_message(self, username, message):
        clean_message = message.strip()
        if message[0] == self.var.PREFIX:
            split_message = clean_message.split(" ")
            if split_message[0][1 :] in self.CMDS:
                LOG.info("Command recognized.")
                self.execute_command(split_message, username)
                time.sleep(1)
            print(split_message)
        else:
            if self.is_active and self.session.check_answer(clean_message):
                LOG.info("Answer recognized.")
                self.answer_question(username)

    def execute_command(self, split_message, username):
        command = split_message[0][1 :]
        # ADMIN ONLY COMMANDS
        if self.is_admin(username):
            if command == "triviastart":
                if self.is_active:
                    LOG.info("Trivia already active.")
                else:
                    self.start_session()
            elif command == "triviaend" and self.is_active:
                self.end_session()
            elif command == "stop":
                self.stop()
            elif command == "loadconfig":
                self.load_config()
                self.chat.send_msg("Config reloaded.")
            elif command == "next":
                self.skip_question()

        # GLOBAL COMMANDS
        if command == "score":
            self.get_score(username)
        elif command == "top":
            n = 3
            if len(split_message) > 1:
                i = try_parse_int64(split_message[1])
                if i is not None:
                    n = i
            top = self.scores.get_overall_top(n)

            msg = "No scores yet."
            if top:
                msg = " ".join(f"{i + 1}: {score[0]} {score[1]} "
                               f"{pluralize(score[1], 'match', 'matches')} | "
                               f"{score[2]} {pluralize(score[2], 'point')}."
                               for i, score in enumerate(top))
            self.chat.send_msg(msg)

    def start_session(self):
        self.chat.send_msg("Generating trivia questions for session...")
        self.scores.clear()

        # Loop through TS and build QS until num_qs = trivia_numbers
        self.session.build_quizset(self.var.num_qs, self.var.tsrows,
                                   self.var.ts)
        self.is_active = True
        self.chat.send_msg(
            f"Trivia has begun! Question Count: {self.var.num_qs}. "
            f"Trivia will start in {self.var.delay} seconds.")
        time.sleep(self.var.delay)
        self.ask_question()

    def end_session(self):
        # Argument "1" will return the first in the list (0th position) for
        # list of top 3
        top = self.scores.get_session_top(3)
        self.scores.clear()
        msg = "No answered questions. Results are blank."
        if top:
            self.chat.send_msg("Trivia is over! Calculating scores...")
            time.sleep(2)
            self.scores.assign_winner(top[0][0])
            msg = "*** {} *** is the winner with {} points!".format(*top[0])
            for i, score in enumerate(top):
                if i > 0:
                    msg += " {} place: {} {} points.".format(self.POS[i],
                                                             *score)
        self.chat.send_msg(msg)

        self.scores.dump(SCORES_PATH)
        time.sleep(3)
        self.chat.send_msg("Thanks for playing! See you next time!")

        # reset variables for trivia
        self.is_active = False
        self.question_asked = False
        self.ask_time = 0
        self.session.reset(self.var.ts.columns)

    def ask_question(self):
        self.question_asked = True
        self.ask_time = round(time.time())

        q_no = self.session.q_no + 1
        self.chat.send_msg(f"Question {q_no}: [{self.session.category()}] "
                           f"{self.session.question()}")

        LOG.info("Question %d: %s | ANSWER: %s", q_no,
                 self.session.question(), self.session.answer())

    def prepare_next_question(self):
        self.question_asked = False
        self.ask_time = 0
        self.session.prepare_next_question()

    def answer_question(self, username):
        try:
            self.scores.user_add("session", username)
            self.scores.user_add("overall", username)
        except KeyError:
            LOG.warning("Failed to find user! Adding new")
            # sets up new user
            self.scores.create_user(username)
        # Save all current scores
        self.scores.dump(SCORES_PATH)
        self.chat.send_msg(
            f"{username} answers question #{self.session.q_no + 1} "
            f"correctly {self.var.correct} The answer is ** "
            f"{self.session.answer()} ** {username} has "
            f"{self.scores.get_session(username)} "
            f"{pluralize(self.scores.get_session(username), 'point')}!")
        time.sleep(self.var.delay)
        self.prepare_next_question()

        if self.session.is_game_over(self.var.num_qs):
            self.end_session()
        else:
            LOG.info("Next question called...")
            self.ask_question()

    def ask_hint(self, hint_type):
        hint = self.session.ask_hint(hint_type)
        if hint is not None:
            self.chat.send_msg(f"Hint #{hint_type}: {hint}")

    def skip_question(self):
        if self.is_active:
            try:
                self.chat.send_msg(
                    f"Question was not answered in time {self.var.wrong} "
                    f"Answer: {self.session.answer()}. Skipping to next "
                    "question")
            except:
                self.chat.send_msg(
                    f"Question was not answered in time {self.var.wrong} "
                    "Skipping to next question")
            self.prepare_next_question()
            time.sleep(self.var.delay)

            if self.session.is_game_over(self.var.num_qs):
                self.end_session()
            else:
                self.ask_question()

    def get_score(self, username):
        try:
            self.chat.send_msg(
                "{} has {} points for this trivia session, {} total points "
                "and {} total wins.".format(username,
                                            *self.scores.data[username]))
        except KeyError:
            self.chat.send_msg(f"{username} not found in database.")

    def routine_check(self):
        self.timer = round(time.time())

        if self.session.is_game_over(self.var.num_qs):
            self.end_session()

        if self.is_active and self.question_asked:
            if self.exceed_time(self.var.skip_time):
                self.skip_question()
            elif self.exceed_time(self.var.hint_time_2):
                self.ask_hint(2)
            elif self.exceed_time(self.var.hint_time_1):
                self.ask_hint(1)
