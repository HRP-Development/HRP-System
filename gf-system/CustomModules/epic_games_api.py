from epicstore_api import EpicGamesStoreAPI

class Errors:
    class GameNotFound(Exception):
        def __init__(self, message="Game not found"):
            self.message = message
            super().__init__(message)
            
def GetFreeGames():
    api = EpicGamesStoreAPI()
    free_games = api.get_free_games()
    if 'data' in free_games and 'Catalog' in free_games['data'] and 'searchStore' in free_games['data']['Catalog']:
        elements = free_games['data']['Catalog']['searchStore']['elements']
        free_games_list = []
        for game in elements:
            price_info = game.get('price', {}).get('totalPrice', {})
            discount_price = price_info.get('discountPrice', -1)
            if discount_price == 0:
                game_id = game['id']
                title = game['title']
                description = game['description']
                picture = game['keyImages'][0]['url']
                link = game['productSlug']
                url_slug = game['productSlug']
                game_info = {
                    'id': game_id,
                    'title': title,
                    'description': description,
                    'picture': picture,
                    'link': f'https://www.epicgames.com/store/de/p/{url_slug}',
                }
                free_games_list.append(game_info)
                
        return free_games_list
    else:
        raise Errors.GameNotFound()

if __name__ == '__main__':
    GetFreeGames()