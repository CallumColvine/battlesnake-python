from collections import namedtuple


Point = namedtuple('Point', ['x', 'y'])


class Food(object):
    def __init__(self, point):
        self.point = point


class Snake(object):
    def __init__(self, body, length, health, snake_id):
        self.body = body
        self.length = length
        self.health = health
        self.id = snake_id

    @property
    def head(self):
        return self.body[0]

    @property
    def tail(self):
        return self.body[1:]


class Board(list):
    def __init__(self, agent_id, width, height, snakes, food):
        self.agent_id = agent_id
        self.width = width
        self.height = height
        self.snakes = snakes
        self.food = food
        self._grid = [[None for _ in range(height)] for _ in range(width)]

        self._populate_grid()

    @property
    def agent_snake(self):
        for snake in self.snakes:
            if snake.id == self.agent_id:
                return snake

    def _populate_grid(self):
        for snake in self.snakes:
            for point in snake.body:
                self._grid[point.y][point.x] = snake
        # TK: disabled for now while experimenting with pathfinding library
        #for f in self.food:
        #    self._grid[f.point.x][f.point.y] = f

    def __getitem__(self, arg):
        return self._grid[arg]

    def __len__(self):
        return len(self._grid)


def _parse_food(data):
    return [Food(Point(point['x'], point['y'])) for point in data['food']['data']]


def _parse_snakes(data):
    snakes = []
    for snake in data['snakes']['data']:
        body = [Point(point['x'], point['y']) for point in snake['body']['data']]
        snakes.append(Snake(body, snake['length'], snake['health'], snake['id']))

    return snakes


def get_board(data):
    snakes = _parse_snakes(data)
    food = _parse_food(data)
    return Board(data['you']['id'], data['width'], data['height'], snakes, food)
