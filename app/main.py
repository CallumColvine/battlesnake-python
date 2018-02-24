import os

from pathfinding.core.grid import Grid
from pathfinding.finder.a_star import AStarFinder

import bottle

from board import get_board, Point



@bottle.route('/static/<path:path>')
def static(path):
    return bottle.static_file(path, root='static/')


@bottle.post('/start')
def start():
    data = bottle.request.json
    game_id = data['game_id']
    board_width = data['width']
    board_height = data['height']

    head_url = '%s://%s/static/head.png' % (
        bottle.request.urlparts.scheme,
        bottle.request.urlparts.netloc
    )

    # TODO: Do things with data

    return {
        'color': '#1A0F05',
        'taunt': '{} ({}x{})'.format(game_id, board_width, board_height),
        'head_url': head_url,
        'name': 'battlesnake-python'
    }


def map_move(snake, point):
    x = snake.head.x - point.x
    y = snake.head.y - point.y
    if x != 0:
        if x < 0:
            return 'right'
        return 'left'
    else:
        if y < 0:
            return 'down'
        return 'up'


def find_path(board, start, end):
    grid = Grid(matrix=board)
    start_pt = grid.node(start.x, start.y)
    end_pt = grid.node(end.x, end.y)

    finder = AStarFinder()
    path, _ = finder.find_path(start_pt, end_pt, grid)
    return path


def get_move(board):
    snake = board.agent_snake
    food = board.food[0]

    # find path with exits in consideration
    path_init  = find_path(board, snake.head, food)

    path_return  = find_path(board, food, snake.tip)
    intersects = set(path_init).intersection(set(path_return))
    if intersects:
        if food in intersects:
            intersects.remove(food)
        for x, y in intersects:
            board[y][x] = snake

    path_final = find_path(board, snake.head, food)
    return map_move(snake, Point(*path_final[1]))


@bottle.post('/move')
def move():
    data = bottle.request.json

    board = get_board(data)
    return {
        'move': get_move(board),
        'taunt': 'battlesnake-python!'
    }


# Expose WSGI app (so gunicorn can find it)
application = bottle.default_app()

if __name__ == '__main__':
    bottle.run(
        application,
        host=os.getenv('IP', '0.0.0.0'),
        port=os.getenv('PORT', '8080'),
        debug = True)
