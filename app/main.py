import os
import logging
import sys

from copy import deepcopy

from pathfinding.core.grid import Grid
from pathfinding.core.heuristic import manhatten
from pathfinding.finder.a_star import AStarFinder

import bottle

from board import get_board, Point, Snake, Food


def _get_logger():
    DEFAULT_FORMAT = '%(asctime)s [%(levelname)s]: %(message)s (%(filename)s:%(lineno)d)'
    logger = logging.getLogger('battlesnake')
    ch = logging.StreamHandler(stream=sys.stderr)
    ch.setFormatter(logging.Formatter(DEFAULT_FORMAT))
    logger.addHandler(ch)
    logger.setLevel(os.getenv('BATTLESNAKE_LOG_LEVEL', logging.INFO))
    return logger


logger = _get_logger()


def fibrange(board):
    # yield 0 and start series from 1/2 to skip returning 1 twice
    yield 0
    a, b = 1, 2
    while a < len(board.agent_snake.tail):
        yield a
        a, b = b, a + b


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


class HeuristicFinder(AStarFinder):
    def __init__(self, board, *args, **kwargs):
        super(HeuristicFinder, self).__init__(*args, **kwargs)
        self.board = board

    def _empty_cell_opponent_risk(self, node):
        if self.board[node.y][node.x] is None:
            return self.board.is_opponent_head(node.x - 1, node.y)\
                or self.board.is_opponent_head(node.x + 1, node.y)\
                or self.board.is_opponent_head(node.x, node.y - 1)\
                or self.board.is_opponent_head(node.x, node.y + 1)

        return False

    def _perimeter_snake_heads(self, node):
        coords = [(node.x - 1, node.y), (node.x + 1, node.y), (node.x, node.y - 1), (node.x, node.y + 1)]
        coord_cells = [(coord, self.board.get_cell(*coord)) for coord in coords]
        return [cell for coord, cell in coord_cells if isinstance(cell, Snake) and cell.is_head(coord[0], coord[1])]

    def _food_in_perimeter(self, node):
        coords = [(node.x - 1, node.y), (node.x + 1, node.y), (node.x, node.y - 1), (node.x, node.y + 1)]
        return sum((isinstance(self.board.get_cell(*coord), Food) for coord in coords))

    def _is_frame_cell(self, node):
        return node.x > self.board.width / 4 or node.x == 0 or node.y > self.board.height / 4 or node.y == 0

    def compute_edge_score(self, node_a, node_b):
        food_in_perimeter = self._food_in_perimeter(node_a)
        manhat = manhatten(abs(node_a.x - node_b.x), abs(node_a.y - node_b.y))
        init_score = 0
        if self._empty_cell_opponent_risk(node_a):
            perimeter_snake_heads = self._perimeter_snake_heads(node_a)
            if self.board.agent_id in (snake.id for snake in perimeter_snake_heads):
                if all([len(self.board.agent_snake) > len(perimeter_snake)
                        for perimeter_snake in perimeter_snake_heads
                        if perimeter_snake.id != self.board.agent_id]):
                    init_score = - manhat

        if self._is_frame_cell(node_a):
            init_score += manhat

        return food_in_perimeter + init_score + manhatten(abs(self.board.width / 2 - node_a.x), abs(self.board.height / 2 - node_b.y)) * 10

    def apply_heuristic(self, node_a, node_b, _=None):
        return self.compute_edge_score(node_a, node_b) + manhatten(abs(node_a.x - node_b.x), abs(node_a.y - node_b.y))


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

    finder = HeuristicFinder(board)
    path, _ = finder.find_path(start_pt, end_pt, grid)
    return path


def get_cut_path(board, start_pt, end_pt):
    board_f = deepcopy(board)
    cut_len = 0
    for cut_len in fibrange(board):
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
            path_final = [snake.head] + path  # TODO-TK: filler, need next move to not be based on [1]th entry
    return path_final


def closest_food(board, start_pt):
    dests = {board.pt_distance(start_pt, f):f for f in board.food}
    return dests[min(dests.keys())]


def closest_to_center_food(board):
    return closest_food(board, Point(board.width / 2, board.height / 2))


def is_shouldering_opponent(board):
    snake = board.agent_snake
    return board.is_opponent_head(snake.head.x - 1, snake.head.y)\
        or board.is_opponent_head(snake.head.x + 1, snake.head.y)\
        or board.is_opponent_head(snake.head.x, snake.head.y - 1)\
        or board.is_opponent_head(snake.head.x, snake.head.y + 1)


def get_destination(board):
    snake = board.agent_snake
    if snake.health < 75 or len(snake) < 20:
        if snake.health > 30:
            return closest_to_center_food(board)
        return closest_food(board, snake.head)
        logger.debug('Choosing closest food as destination')
    if len(board.snakes) == 2 and snake.health > 90:
        for snake_id in board.snakes.keys():
            if snake_id != board.agent_id:
                opp_snake = board.snakes[snake_id]
                opp_head = opp_snake.body[0]
                opp_neck = opp_snake.body[1]
                x = (opp_head.x - opp_neck.x) * 2
                y = (opp_head.y - opp_neck.y) * 2
                point = Point(opp_head.x + x, opp_head.x + y)
                if board[point]:
                    logger.debug('Choosing front of 1v1 opponent as destination')
                    return point
    if snake.health > 50:
        logger.debug('Choosing closest to center destination')
    return snake.tip


def get_move(board):
    snake = board.agent_snake
    food = get_destination(board)

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
                    logger.debug('Using last resort path')
                    path_final = path_food_longer if cut_food_len < cut_tip_len else path_tip_longer

    next_move = map_move(snake, Point(*path_final[1]))
    logger.info("Making next move {} with path: {}".format(next_move, path_final))
    return next_move


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
