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
def find_path(board, start, end, trim_tip=False, prune_tip=False):
    tip_stack = board.agent_snake.tip_stack()
    head_distance = board.pt_distance(start, end)
    if prune_tip or trim_tip and head_distance > tip_stack:
        logger.debug('Trimming tip of snake with {} tips stacked and {} away.'.format(tip_stack, head_distance))
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
    for cut_len in range(0, min(len(board.agent_snake.tail), board.width * 2)):
        tail_pt = board_f.prune_agent_tail(cut_len)
        path_candidate = find_path(board_f, start_pt, end_pt)
        logger.debug('Cut path at length {}: {}'.format(cut_len, path_candidate))
        if tail_pt and len(path_candidate) > 1:
            logger.debug('Returning cut path to end point {} at length {}'.format(end_pt,cut_len))
            path_candidate = find_path(board_f, start_pt, tail_pt)
            break
    return path_candidate, cut_len, tail_pt


def find_disjoint_path(board, snake, food):
    path_init = find_path(board, snake.head, food)
    logger.debug('Init path: {}'.format(path_init))

    path_return = find_path(board, food, snake.tip, trim_tip=True)
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


def get_longer_path(board, snake, cut_tail_pt, path_final, prune_tip=False):
    paths = []
    # Check if it's within the bounds of the board and it's NOT occupied
    if snake.head.y - 1 >= 0 and board[snake.head.y - 1][snake.head.x] is None:
        paths.append(find_path(board, Point(snake.head.x, snake.head.y - 1), cut_tail_pt, prune_tip=prune_tip))

    if snake.head.y + 1 < board.height and board[snake.head.y + 1][snake.head.x] is None:
        paths.append(find_path(board, Point(snake.head.x, snake.head.y + 1), cut_tail_pt, prune_tip=prune_tip))

    if snake.head.x - 1 >= 0 and board[snake.head.y][snake.head.x - 1] is None:
        paths.append(find_path(board, Point(snake.head.x - 1, snake.head.y), cut_tail_pt, prune_tip=prune_tip))

    if snake.head.x + 1 < board.width and board[snake.head.y][snake.head.x + 1] is None:
        paths.append(find_path(board, Point(snake.head.x + 1, snake.head.y), cut_tail_pt, prune_tip=prune_tip))

    logger.debug('Space filling paths are: {}'.format(paths))
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
        logger.info('Using optimal path')
        path_final = path_init
    else:
        logger.debug('Not using optimal path')
        cut_food_path, cut_food_len, food_pt = get_cut_path(board, snake.head, food)

        if cut_food_len < len(cut_food_path):
            logger.info('Using cut food path')
            path_final = cut_food_path
        else:
            logger.debug('Not using cut food path')
            path_food_longer = get_longer_path(board, snake, food_pt, cut_food_path)
            if cut_food_len < len(path_food_longer):
                path_final = path_food_longer
                logger.info('Using longer cut food path')
            else:
                logger.debug('Not using longer cut food path')
                cut_tip_path, cut_tip_len, cut_tip_pt = get_cut_path(board, snake.head, snake.tip)
                path_tip_longer = get_longer_path(board, snake, cut_tip_pt, cut_tip_path, prune_tip=True)
                if cut_tip_len < len(path_tip_longer):
                    logger.info('Using longer cut tip path')
                    path_final = path_tip_longer
                else:
                    logger.debug('Using init path')
                    path_final = path_init

    logger.info("Path: {}".format(path_final))
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
