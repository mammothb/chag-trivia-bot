import logging
import re
import socket
import time

LOG = logging.getLogger("Chat")

class Chat:
    # RATE = 20 / 30  # message rate limit
    RATE = 120  # message rate limit
    CHAT_MSG = re.compile(r"^:\w+!\w+@\w+\.tmi\.twitch\.tv PRIVMSG #\w+ :")

    def __init__(self, bot):
        self.bot = bot
        self.socket = socket.socket()
        self.HOST = None
        self.PORT = None
        self.NICK = None
        self.PASS = None
        self.CHAN = None
        self.is_loaded = False

    def is_bot(self, username):
        return username.lower() == self.NICK.lower()

    def is_ready(self):
        return self.is_loaded

    def set_config(self, config):
        try:
            self.HOST = config["host"]
            self.PORT = int(config["port"])
            self.NICK = config["nick"]
            self.PASS = config["pass"]
            self.CHAN = config["chan"]
            self.is_loaded = True
        except (KeyError, ValueError):
            LOG.error("Config not loaded! Check config file and reboot bot.")
            self.is_loaded = False

    def connect(self):
        self.socket.connect((self.HOST, self.PORT))
        self.socket.send(f"PASS {self.PASS}\r\n".encode("utf-8"))
        self.socket.send(f"NICK {self.NICK}\r\n".encode("utf-8"))
        self.socket.send(f"JOIN {self.CHAN}\r\n".encode("utf-8"))
        time.sleep(1)
        self.socket.setblocking(0)

    # Chat message sender func
    def send_msg(self, msg):
        self.socket.send(
            ":{0}!{0}@{0}.tmi.twitch.tv PRIVMSG {1} : {2}\r\n".format(
                self.NICK, self.CHAN, msg).encode("utf-8"))

    def scanloop(self):
        try:
            response = self.socket.recv(1024).decode("utf-8")
            if response == "PING :tmi.twitch.tv\r\n":
                self.socket.send("PONG :tmi.twitch.tv\r\n".encode("utf-8"))
                LOG.info("Pong sent")
                return
            username = re.search(r"\w+", response).group(0)
            if self.is_bot(username):
                return
            message = self.CHAT_MSG.sub("", response)
            LOG.info("USER RESPONSE: %s : %s", username, message)
            self.bot.process_message(username, message)
        except (BlockingIOError, AttributeError):
            pass
        finally:
            time.sleep(1 / self.RATE)
