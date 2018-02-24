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


def find_path(board, start, end):
    grid = Grid(matrix=board)
    start_pt = grid.node(start.x, start.y)
    end_pt = grid.node(end.x, end.y)

    finder = AStarFinder()
    path, _ = finder.find_path(start_pt, end_pt, grid)
    return path


# TODO-TK: snake can crash into itself if it can't chase its tail and near by it
def get_cut_path(board, snake, food):
    board_f = deepcopy(board)
    for cut_len in range(1, board.width * 2):
        tail_pt = board_f.prune_agent_tail(cut_len)
        path_candidate  = find_path(board_f, snake.head, food)
        logger.debug('Cut path at length {}: {}'.format(cut_len, path_candidate))
        if path_candidate != []:
            logger.info('Using cut path to tail tip at length {}'.format(cut_len))
            path_candidate = find_path(board_f, snake.head, tail_pt)
            break  # use smallest cut possible
    return path_candidate


def find_disjoint_path(board, path_init, snake, food):
    path_return = find_path(board, food, snake.tip)
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
    return path


def get_move(board):
    snake = board.agent_snake
    food = board.food[0]  # TODO-TK: needs "closest food" functionality

    path_init = find_path(board, snake.head, food)
    logger.debug('Init path: {}'.format(path_init))

    # check if we can make a path assuming future snake length
    if path_init:
        # find path with exits in consideration
        path_final = find_disjoint_path(board, path_init, snake, food)
    else:
        tailchase_path = find_path(board, snake.head, snake.tip)
        logger.debug('Tail chase path: {}'.format(tailchase_path))
        if tailchase_path:
            logger.info('Using tail chase path')
            path_final = tailchase_path
        else:
            # TODO-TK: doesn't detour, problem for when we need to during cut paths
            path_final = get_cut_path(board, snake, food)

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
