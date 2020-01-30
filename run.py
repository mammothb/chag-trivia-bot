import logging

from chagtriviabot.bot import ChagTriviaBot

FORMAT = '%(asctime)-15s %(levelname)7s %(name)7s: %(message)s'
logging.basicConfig(format=FORMAT, level=logging.INFO)

BOT = ChagTriviaBot()
BOT.prepare()
BOT.run()
