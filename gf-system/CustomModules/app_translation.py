import discord
from typing import Optional


class Translator(discord.app_commands.Translator):
    def __init__(self):
        self.translations = {
            discord.Locale.german: {
                "Test, if the bot is responding.": "Teste, ob der Bot antwortet.",
                "Get information about the bot.": "Erhalte Informationen über den Bot.",
                "change_nickname": "nickname_ändern",
                "Setup the bot.": "Richte den Bot ein.",
                "clear": "löschen",
                "Clears the chat.": "Löscht den Chat.",
                "Amount of messages to delete.": "Anzahl der zu löschenden Nachrichten.",
                "lock": "sperren",
                "Locks the chat.": "Sperrt den Chat.",
                "unlock": "entsperren",
                "Unlocks the chat.": "Entsperrt den Chat.",
                "Kicks a user.": "Kickt einen Benutzer.",
                "ban": "sperren",
                "Bans a user.": "Sperrt einen Benutzer.",
                "send_verification": "verifizierung_senden",
                "Sends the Verfication Embed.": "Sendet das Verifizierungs-Embed.",
                },
            discord.Locale.japanese: {
                "ping": "ピング",
                "Test, if the bot is responding.": "ボットが応答しているかテストします。",
                "botinfo": "ボット情報",
                "Get information about the bot.": "ボットに関する情報を取得します。",
                "change_nickname": "ニックネームを変更する",
                "Setup the bot.": "ボットをセットアップします。",
                "clear": "クリア",
                "Clears the chat.": "チャットをクリアします。",
                "Amount of messages to delete.": "削除するメッセージの数。",
                "lock": "ロック",
                "Locks the chat.": "チャットをロックします。",
                "unlock": "アンロック",
                "Unlocks the chat.": "チャットをアンロックします。",
                "kick": "キック",
                "Kicks a user.": "ユーザーをキックします。",
                "ban": "禁止",
                "Bans a user.": "ユーザーを禁止します。",
                }
        }

    async def load(self):
        print("App Translator initialized.")

    async def translate(self,
                        string: discord.app_commands.locale_str,
                        locale: discord.Locale,
                        context: discord.app_commands.TranslationContext) -> Optional[str]:
        """
        `locale_str` is the string that is requesting to be translated
        `locale` is the target language to translate to
        `context` is the origin of this string, eg TranslationContext.command_name, etc
        This function must return a string (that's been translated), or `None` to signal no available translation available, and will default to the original.
        """
        string = string.message
        return self.translations.get(locale, {}).get(string, string)