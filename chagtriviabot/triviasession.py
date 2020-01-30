import logging
import random

import pandas as pd

from chagtriviabot.editdistance import DistanceAlgorithm, EditDistance

LOG = logging.getLogger("Session")

class TriviaSession:
    def __init__(self):
        self.data = None
        self.comparer = None
        self.q_no = 0
        # 0 = not requested, 1 = first hint requested, 2 = second hint
        # requested
        self.hint_req = 0
        # Time when the last question was asked (used for relative time
        # length for hints/skip)
        self.ask_time = 0

    def reset(self, columns):
        self.data = pd.DataFrame(columns=columns)
        self.comparer = EditDistance(DistanceAlgorithm.DAMERUAUOSA)
        self.q_no = 0
        self.hint_req = 0
        self.ask_time = 0

    def fuzzy_match(self, message):
        tol = 0.4 - 0.15 * self.hint_req
        ans = self.answer()
        dist = self.comparer.compare(ans.lower(), message.lower(), 2 ** 31 - 1)
        closeness = dist / len(ans)
        LOG.info("Distance: %d | Difference: %f | Tolerance %f", dist,
                 closeness, tol)
        return closeness < tol

    def build_quizset(self, num_qs, tsrows, ts):
        # Create a list of all indices
        row_list = list(range(tsrows))
        n = 0
        while n < num_qs:
            row_idx = random.choice(row_list)
            row_list.remove(row_idx)
            try:
                # Check for duplicates with last argument, skip if so
                self.data = self.data.append(ts.loc[row_idx],
                                             verify_integrity=True)
                n += 1
            except:
                # pass on duplicates and re-roll
                LOG.warning("Duplicate index. This should not happen, "
                            "dropping row from table. Please check "
                            "config.txt's questions are <= total # of "
                            "questions in trivia set.")
                ts.drop(ts.index[[row_idx]])
        LOG.info("Quizset built.")

    def ask_hint(self, hint_type):
        if hint_type <= self.hint_req:
            return None
        self.hint_req += 1
        prehint = self.answer()
        n = len(prehint)
        idx = random.sample(range(n), k=self.hint_req * n // 3)
        return "".join(c if i in idx or not c.isalnum() else "_"
                       for i, c in enumerate(prehint))

    def category(self):
        return self.data.iloc[self.q_no, 0]

    def question(self):
        return self.data.iloc[self.q_no, 1]

    def answer(self):
        return self.data.iloc[self.q_no, 2]

    def check_answer(self, message):
        return self.fuzzy_match(message)

    def set_ask_time(self, ask_time):
        self.ask_time = ask_time

    def prepare_next_question(self):
        self.q_no += 1
        self.hint_req = 0
        self.ask_time = 0

    def is_game_over(self, num_qs):
        return num_qs == self.q_no
