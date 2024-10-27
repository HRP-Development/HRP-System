# Badwordlist v1
from functools import lru_cache
from difflib import SequenceMatcher


class BadWords:
    def __init__(self):
        self.badwordlist = {
        "hurensohn", "fotze", "bastard", "opfer", "spast", "wichser", "arschloch", "ficker",
        "schlampe", "hure", "mongo", "missgeburt", "verpiss", "idiot", "trottel",
        "drecksau", "penner", "schwachkopf", "arschficker", "pimmel", "scheißdreck", "verfickt",
        "dummkopf", "scheißhaufen", "wichse", "kotzbrocken", "schwuchtel", "kanacke", "asozialer",
        "dreckspatz", "miststück", "volldepp", "affenarsch", "arschkriecher", "pissnelke", 
        "hinterlader", "drecksack", "arroganzbolzen", "rotze", "dreckslappen",
        "schwachmat", "gehirnamputiert", "verkrüppelt", "vollidiot", "hackfresse",
        "nigger"
        }
        self.words_to_check = {word.lower() for word in self.badwordlist}


    @lru_cache(maxsize=50)
    def isBad(self, message: str) -> bool:
        cleaned_message = ''.join(char.lower() if char.isalnum() or char.isspace() else ' ' for char in message)
        message_words = set(cleaned_message.split())
        
        if self.words_to_check.intersection(message_words):
            return True
        
        for message_word in message_words:
            for word in self.words_to_check:
                similarity = SequenceMatcher(None, word, message_word).ratio()
                if similarity >= 0.81:
                    print(f"{message_word}:{word} -> {similarity}")
                    return True
        
        return False
               



if __name__ == "__main__":
    bad = BadWords()
    test = "Du bist ein Huren sohn."
    print(bad.isBad(test))