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
    tail_pt = None
    for cut_len in range(0, board.width * 2):
        tail_pt = board_f.prune_agent_tail(cut_len)
        path_candidate = find_path(board_f, start_pt, end_pt)
        logger.debug('Cut path at length {}: {}'.format(cut_len, path_candidate))
        if path_candidate != []:
            logger.info('Returning cut path to tail tip at length {}'.format(cut_len))
            path_candidate = find_path(board_f, start_pt, tail_pt)
            break
    return path_candidate, cut_len, tail_pt


def find_disjoint_path(board, path_init, snake, food):
    path_return = find_path(board, food, snake.tip)
    logger.debug('Return path: {}'.format(path_return))
    if path_return == []:
        path_return, _, _ = get_cut_path(board, food, snake.tip)
        logger.debug('Trying a cut return path: {}'.format(path_return))
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

# 1. Deep copy graph
# 2. For all non-Snake nodes, traverse until we get to the destination point
# 3. Mark yourself as a non-Snake node
# 4. Return your value + any value returned to you

def get_longest_path(board, head, cut_tail_pt):
    print board
    print "Cut tail pt is", cut_tail_pt
    path_board = deepcopy(board)
    max_path = []
    if cut_tail_pt:
        max_path = long_path_recurse(path_board, head, cut_tail_pt)
    print "Max path is ", max_path
    return max_path

def point_exists_not_visited(current_point, direction, board):
    if direction == 'left':
        if current_point.x - 1 >= 0 and board[current_point.x - 1][current_point.y] == 0:
            return Point(current_point.x - 1, current_point.y)
    elif direction == 'right':
        if current_point.x + 1 < len(board) and board[current_point.x + 1][current_point.y] == 0:
            return Point(current_point.x + 1, current_point.y)
    elif direction == 'up':
        if current_point.y - 1 >= 0 and board[current_point.x][current_point.y - 1] == 0:
            return Point(current_point.x, current_point.y - 1)
    elif direction == 'down':
        if current_point.y + 1 < len(board) and board[current_point.x][current_point.y + 1] == 0:
            return Point(current_point, current_point.y + 1)
    return None

def long_path_recurse(board, current_point, destination_point):
    if current_point == destination_point:
        return [current_point]

    path_left = []
    left_point = point_exists_not_visited(current_point, 'left', board)
    if left_point:
        board[current_point.x][current_point.y] = 1
        path_left.append(long_path_recurse(destination_point, current_point.left, board))
        board[current_point.x][current_point.y] = 0

    path_right = []
    right_point = point_exists_not_visited(current_point, 'right', board)
    if right_point:
        board[current_point.x][current_point.y] = 1
        path_right.append(long_path_recurse(destination_point, current_point.left, board))
        board[current_point.x][current_point.y] = 0

    path_up = []
    up_point = point_exists_not_visited(current_point, 'up', board)
    if up_point:
        board[current_point.x][current_point.y] = 1
        path_up.append(long_path_recurse(destination_point, current_point.left, board))
        board[current_point.x][current_point.y] = 0

    path_down = []
    down_point = point_exists_not_visited(current_point, 'down', board)
    if down_point:
        board[current_point.x][current_point.y] = 1
        path_down.append(long_path_recurse(destination_point, current_point.left, board))
        board[current_point.x][current_point.y] = 0

    max_list = path_left if len(path_left) > path_right else path_right
    max_list = path_right if len(path_right) > path_up else path_up
    max_list = path_up if len(path_up) > path_down else path_down
    return max_list

def get_move(board):
    snake = board.agent_snake
    food = board.food[0]  # TODO-TK: needs "closest food" functionality

    path_init = find_path(board, snake.head, food)
    logger.debug('Init path: {}'.format(path_init))

    # CC - Testing
    cut_food_path, cut_food_len, cut_tail_pt_food = get_cut_path(board, snake.head, food)
    cut_tip_path, cut_tip_len, cut_tail_pt_tip = get_cut_path(board, snake.head, snake.tip)
    cut_tail_pt = cut_tail_pt_food if cut_food_len <= cut_tip_len else cut_tail_pt_tip
    path_final = cut_food_path if cut_food_len <= cut_tip_len else cut_tip_path
    long_path = get_longest_path(board, snake.head, cut_tail_pt)

    # check if we can make a path assuming future snake length
    if path_init:
        # find path with exits in consideration
        path_final = find_disjoint_path(board, path_init, snake, food)
    else:
        tailchase_path = find_path(board, snake.head, snake.tip, trim_tip=True)
        logger.debug('Tail chase path: {}'.format(tailchase_path))
        if tailchase_path:
            logger.info('Using tail chase path')
            path_final = tailchase_path
        else:
            # TODO-TK: need to implement a reasonable longest path approximation
            cut_food_path, cut_food_len, _ = get_cut_path(board, snake.head, food)
            cut_tip_path, cut_tip_len, _ = get_cut_path(board, snake.head, snake.tip)
            path_final = cut_food_path if cut_food_len <= cut_tip_len else cut_tip_path


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
