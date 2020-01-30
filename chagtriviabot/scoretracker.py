import collections
import json
import logging
import os.path

LOG = logging.getLogger("Score")

class ScoreTracker:
    def __init__(self):
        self.data = None
        self.is_loaded = False

    def is_ready(self):
        return self.is_loaded

    def load(self, score_path):
        if os.path.exists(score_path):
            with open(score_path, "r") as scores:
                self.data = json.load(scores)
                self.is_loaded = True
                LOG.info("Loaded from score list.")
        else:
            self.data = {}
            self.is_loaded = True
            self.dump(score_path)
            LOG.warning("No score list found, creating...")

    def dump(self, score_path):
        try:
            with open(score_path, "w") as scores:
                json.dump(self.data, scores)
        except (TypeError, OverflowError, ValueError) as e:
            LOG.error("Scores NOT saved! Reason: %s", e)
            self.is_loaded = False

    def clear(self):
        for i in self.data:
            self.data[i][0] = 0

    def user_add(self, score_type, username):
        if score_type == "session":
            self.data[username][0] += 1
        elif score_type == "overall":
            self.data[username][1] += 1
        elif score_type == "match":
            self.data[username][2] += 1

    def create_user(self, username):
        self.data[username] = [1, 1, 0]

    def assign_winner(self, username):
        self.user_add("match", username)

    def get_session(self, username):
        return self.data[username][0]

    def get_overall(self, username):
        return self.data[username][1]

    def get_match(self, username):
        return self.data[username][2]

    def get_session_top(self, number):
        # temp dictionary just for keys & sessionscore
        scores = {i: self.get_session(i)
                  for i in self.data if self.get_session(i) > 0}
        score_counter = collections.Counter(scores)

        top_scores = [[k, v] for k, v in score_counter.most_common(number)]
        return top_scores

    def get_overall_top(self, n):
        scores = sorted(self.data,
                        key=lambda x: (self.get_match(x), self.get_overall(x)),
                        reverse=True)
        top = [[k, self.get_match(k), self.get_overall(k)]
               for k in (scores[: n] if len(scores) > n else scores)]
        return top
