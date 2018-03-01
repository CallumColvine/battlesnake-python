import os
import logging
import sys

from copy import deepcopy

from pathfinding.core.grid import Grid
from pathfinding.finder.a_star import AStarFinder

import bottle

from board import get_board, Point


def _get_logger():
    DEFAULT_FORMAT = '%(asctime)s [%(levelname)s]: %(message)s (%(filename)s:%(lineno)d)'
    logger = logging.getLogger('battlesnake')
    ch = logging.StreamHandler(stream=sys.stderr)
    ch.setFormatter(logging.Formatter(DEFAULT_FORMAT))
    logger.addHandler(ch)
    logger.setLevel(os.getenv('BATTLESNAKE_LOG_LEVEL', logging.INFO))
    return logger


logger = _get_logger()


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


# trim_tip necessary due to data anomaly we're getting from the server
# unable to fully remove because many nodes are in same position, can collide if too close (hence > 1 condition)
def find_path(board, start, end, trim_tip=False):
    if trim_tip and board.pt_distance(start, end) > 1:
        board_c = deepcopy(board)
        board_c[end.y][end.x] = None
        grid = Grid(matrix=board_c)
    else:
        grid = Grid(matrix=board)

    start_pt = grid.node(start.x, start.y)
    end_pt = grid.node(end.x, end.y)

    finder = AStarFinder()
    path, _ = finder.find_path(start_pt, end_pt, grid)
    return path


def get_cut_path(board, start_pt, end_pt):
    board_f = deepcopy(board)
    cut_len = 0
    for cut_len in range(1, board.width * 2):
        tail_pt = board_f.prune_agent_tail(cut_len)
        path_candidate  = find_path(board_f, start_pt, end_pt)
        logger.debug('Cut path at length {}: {}'.format(cut_len, path_candidate))
        if path_candidate != []:
            logger.info('Returning cut path to tail tip at length {}'.format(cut_len))
            path_candidate = find_path(board_f, start_pt, tail_pt)
            break
    return path_candidate, cut_len, tail_pt


def find_disjoint_path(board, snake, food):
    path_init = find_path(board, snake.head, food)
    logger.debug('Init path: {}'.format(path_init))

    path_return = find_path(board, food, snake.tip)
    logger.debug('Return path: {}'.format(path_return))

    intersects = set(path_init).intersection(set(path_return))
    logger.debug('Removing intersections: {}'.format(intersects))
    if intersects:
        if food in intersects:
            intersects.remove(food)
        for x, y in intersects:
            board[y][x] = snake

    disjoint_path = find_path(board, snake.head, food)
    logger.debug('Disjoint path: {}'.format(disjoint_path))
    if disjoint_path:
        path = disjoint_path
    else:
        path = path_init

    return_exists = True if path_return else False
    return path, return_exists

def get_least_short_path(board, snake, cut_tail_pt, path_final):
    paths = []
    board[snake.head.y][snake.head.x] = 1
    print('!! Getting longest path space fill')
    # Check if it's within the bounds of the board and it's NOT occupied
    if snake.head.y - 1 >= 0 and board[snake.head.y - 1][snake.head.x] != 1:
        paths.append(find_path(
            board, Point(snake.head.y - 1, snake.head.x), cut_tail_pt))
    if snake.head.y + 1 < board.width and board[snake.head.y + 1][snake.head.x] != 1:
        paths.append(find_path(
            board, Point(snake.head.y + 1, snake.head.x), cut_tail_pt))
    if snake.head.x - 1 >= 0 and board[snake.head.y][snake.head.x - 1] != 1:
        paths.append(find_path(
            board, Point(snake.head.y, snake.head.x - 1), cut_tail_pt))
    if snake.head.x + 1 < board.height and board[snake.head.y][snake.head.x + 1] != 1:
        paths.append(find_path(
            board, Point(snake.head.y, snake.head.x + 1), cut_tail_pt))
    logger.info('Space filling paths are: {}'.format(paths))
    for path in paths:
        logger.debug('Considering space fill path: {}'.format(path))
        if path and len(path) > len(path_final):
            path_final = path
    return path_final

def get_move(board):
    snake = board.agent_snake
    food = board.food[0]  # TODO-TK: needs "closest food" functionality

    # find path with exits in consideration
    path_init, return_exists = find_disjoint_path(board, snake, food)

    if path_init and return_exists:
        path_final = path_init
    else:
        tailchase_path = find_path(board, snake.head, snake.tip, trim_tip=True)
        logger.debug('Tail chase path: {}'.format(tailchase_path))
        if len(tailchase_path) > 1:
            logger.info('Using tail chase path')
            path_final = tailchase_path
        else:
            if path_init:
                logger.info('Reverting to init path.')
                path_final = path_init
            else:
                # TODO-TK: need to implement a reasonable longest path approximation
                cut_food_path, cut_food_len, food_tail_pt = get_cut_path(board, snake.head, food)
                cut_tip_path, cut_tip_len, cut_tail_pt = get_cut_path(board, snake.head, snake.tip)
                path_final = cut_food_path if cut_food_len <= cut_tip_len and cut_food_path else cut_tip_path
                target_point = food_tail_pt if cut_food_len <= cut_tip_len and cut_food_path else cut_tail_pt
                # goal_point = Point(path_final[-1][0], path_final[-1][1])
                path_shorter = get_least_short_path(board, snake, target_point, path_final)
                if path_shorter:
                    path_final = path_shorter



    logger.info("Using path: {}".format(path_final))
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
