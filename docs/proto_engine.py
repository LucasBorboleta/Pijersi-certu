#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""pijersi_rules.py implements the rules engine for the PIJERSI boardgame."""

__version__ = "1.1.0-rc3"

_COPYRIGHT_AND_LICENSE = """
PIJERSI-CERTU implements a GUI and a rules engine for the PIJERSI boardgame.

Copyright (C) 2019 Lucas Borboleta (lucas.borboleta@free.fr).

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses>.
"""

import array
import copy
import enum
from dataclasses import dataclass
#from collections import namedtuple
import math
import os
import random
import sys
import timeit
from typing import Callable
from typing import Iterable
from typing import NewType
from typing import Optional
from typing import Sequence
from typing import Tuple
from typing import TypeVar

import cProfile
from pstats import SortKey


_package_home = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "pijersi_certu")
sys.path.append(_package_home)
import pijersi_rules as rules


_do_debug = False

OMEGA = 1_000.
OMEGA_2 = OMEGA**2

HexIndex = NewType('HexIndex', int)
Sources = Iterable[HexIndex]
Path = Sequence[HexIndex]

CaptureCode = NewType('CaptureCode', int)
HexCode = NewType('HexCode', int)
MoveCode = NewType('MoveCode', int)
PathCode = NewType('PathCode', int)

BoardCodes = Sequence[HexCode]
PathCodes = Sequence[HexCode]


@enum.unique
class Reward(enum.IntEnum):
    WIN = 1
    DRAW = 0
    LOSS = -1

    assert LOSS < DRAW < WIN
    assert DRAW == 0
    assert LOSS + WIN == DRAW


@enum.unique
class Player(enum.IntEnum):
    WHITE = 0
    BLACK = 1
    assert WHITE < BLACK


def Player_name(player: Player) -> str:
    assert player in Player

    if player == Player.WHITE:
        return "white"

    elif player == Player.BLACK:
        return "black"


@enum.unique
class CubeSort(enum.IntEnum):
    ROCK = 0
    PAPER = 1
    SCISSORS = 2
    WISE = 3
    assert ROCK < PAPER < SCISSORS < WISE


def CubeSort_beats(src: CubeSort, dst: CubeSort) -> bool:
    assert src in CubeSort
    assert dst in CubeSort
    return (src, dst) in ((CubeSort.ROCK, CubeSort.SCISSORS),
                          (CubeSort.SCISSORS, CubeSort.PAPER),
                          (CubeSort.PAPER, CubeSort.ROCK))


CUBE_FROM_NAME = dict()
CUBE_FROM_NAME['R'] = (Player.WHITE, CubeSort.ROCK)
CUBE_FROM_NAME['P'] = (Player.WHITE, CubeSort.PAPER)
CUBE_FROM_NAME['S'] = (Player.WHITE, CubeSort.SCISSORS)
CUBE_FROM_NAME['W'] = (Player.WHITE, CubeSort.WISE)

CUBE_FROM_NAME['r'] = (Player.BLACK, CubeSort.ROCK)
CUBE_FROM_NAME['p'] = (Player.BLACK, CubeSort.PAPER)
CUBE_FROM_NAME['s'] = (Player.BLACK, CubeSort.SCISSORS)
CUBE_FROM_NAME['w'] = (Player.BLACK, CubeSort.WISE)

CUBE_TO_NAME = dict()
CUBE_TO_NAME[(Player.WHITE, CubeSort.ROCK)] = 'R'
CUBE_TO_NAME[(Player.WHITE, CubeSort.PAPER)] = 'P'
CUBE_TO_NAME[(Player.WHITE, CubeSort.SCISSORS)] = 'S'
CUBE_TO_NAME[(Player.WHITE, CubeSort.WISE)] = 'W'

CUBE_TO_NAME[(Player.BLACK, CubeSort.ROCK)] = 'r'
CUBE_TO_NAME[(Player.BLACK, CubeSort.PAPER)] = 'p'
CUBE_TO_NAME[(Player.BLACK, CubeSort.SCISSORS)] = 's'
CUBE_TO_NAME[(Player.BLACK, CubeSort.WISE)] = 'w'


@enum.unique
class HexagonDirection(enum.IntEnum):
    PHI_090 = 0
    PHI_150 = 1
    PHI_210 = 2
    PHI_270 = 3
    PHI_330 = 4
    PHI_030 = 5
    assert PHI_090 < PHI_150 < PHI_210 < PHI_270 < PHI_330 < PHI_030


def hex_distance(position_uv_1: Tuple[int, int], position_uv_2: Tuple[int, int]):
    """reference: https://www.redblobgames.com/grids/hexagons/#distances"""
    (u1, v1) = position_uv_1
    (u2, v2) = position_uv_2
    distance = (math.fabs(u1 - u2) + math.fabs(v1 - v2)+ math.fabs(u1 + v1 - u2 - v2))/2
    return distance


class Hexagon:

    Self = TypeVar("Self", bound="HexState")

    NULL = -102 # >> Should be negative and should be representable as a signed byte

    __slots__ = ('name', 'position_uv', 'index')

    __all_indices = []
    __all_sorted_hexagons = []
    __init_done = False
    __goal_indices = []
    __layout = []
    __name_to_hexagon = {}
    __next_fst_indices = []
    __next_snd_indices = []
    __position_uv_to_hexagon = {}
    __distance = {}
    __distance_to_goal = None


    all = None # shortcut to Hexagon.get_all()


    def __init__(self, name: str, position_uv= Tuple[int, int]):

        assert name not in Hexagon.__name_to_hexagon
        assert len(position_uv) == 2
        assert position_uv not in Hexagon.__position_uv_to_hexagon
        assert len(name) == 2

        self.name = name
        self.position_uv = position_uv
        self.index = None

        Hexagon.__name_to_hexagon[self.name] = self
        Hexagon.__position_uv_to_hexagon[position_uv] = self


    def __str__(self):
        return f"Hexagon({self.name}, {self.position_uv}, {self.index}"


    @staticmethod
    def get(name: str) ->Self:
        return Hexagon.__name_to_hexagon[name]


    @staticmethod
    def get_all() -> Sequence[Self]:
        return Hexagon.__all_sorted_hexagons


    @staticmethod
    def get_all_indices() -> Sequence[HexIndex]:
        return Hexagon.__all_indices


    @staticmethod
    def get_goal_indices(player: Player) -> Sequence[HexIndex]:
        return Hexagon.__goal_indices[player]


    @staticmethod
    def get_layout() -> Sequence[Sequence[str]]:
        return Hexagon.__layout


    @staticmethod
    def get_next_fst_index(hexagon_index: HexIndex, hexagon_dir: HexagonDirection) -> HexIndex:
        return Hexagon.__next_fst_indices[hexagon_index][hexagon_dir]


    @staticmethod
    def get_next_snd_index(hexagon_index: HexIndex, hexagon_dir: HexagonDirection) -> HexIndex:
        return Hexagon.__next_snd_indices[hexagon_index][hexagon_dir]


    @staticmethod
    def get_distance(hexagon_1_index: HexIndex, hexagon_2_index: HexIndex) -> float:
        return Hexagon.__distance[(hexagon_1_index, hexagon_2_index)]


    @staticmethod
    def get_distance_to_goal(hexagon_index: HexIndex, player: Player) -> float:
        return Hexagon.__distance_to_goal[player][hexagon_index]


    @staticmethod
    def init():
        if not  Hexagon.__init_done:
            Hexagon.__create_hexagons()
            Hexagon.__create_all_sorted_hexagons()
            Hexagon.__create_layout()
            Hexagon.__create_goal_hexagons()
            Hexagon.__create_delta_u_and_v()
            Hexagon.__create_next_hexagons()
            Hexagon.__create_distance()
            Hexagon.__create_distance_to_goal()
            Hexagon.__init_done = True


    @staticmethod
    def print_hexagons():
        for hexagon in Hexagon.__all_sorted_hexagons:
            print(hexagon)


    @staticmethod
    def __create_all_sorted_hexagons():
        for name in sorted(Hexagon.__name_to_hexagon.keys()):
            Hexagon.__all_sorted_hexagons.append(Hexagon.__name_to_hexagon[name])

        for (index, hexagon) in enumerate(Hexagon.__all_sorted_hexagons):
            hexagon.index = index

        for hexagon in Hexagon.__all_sorted_hexagons:
            Hexagon.__all_indices.append(hexagon.index)

        Hexagon.all = Hexagon.__all_sorted_hexagons


    @staticmethod
    def __create_delta_u_and_v():
        Hexagon.__delta_u = array.array('b', [+1, +1, +0, -1, -1, +0])
        Hexagon.__delta_v = array.array('b', [+0, -1, -1, +0, +1, +1])


    @staticmethod
    def __create_goal_hexagons():

        white_goal_hexagons = ["g1", "g2", "g3", "g4", "g5", "g6"]
        black_goal_hexagons = ["a1", "a2", "a3", "a4", "a5", "a6"]

        white_goal_indices = array.array('b', map(lambda x: Hexagon.get(x).index, white_goal_hexagons))
        black_goal_indices = array.array('b', map(lambda x: Hexagon.get(x).index, black_goal_hexagons))

        Hexagon.__goal_indices = [None for _ in Player]

        Hexagon.__goal_indices[Player.WHITE] = white_goal_indices
        Hexagon.__goal_indices[Player.BLACK] = black_goal_indices


    @staticmethod
    def __create_layout():

        Hexagon.__layout = []

        Hexagon.__layout.append( (1, ["g1", "g2", "g3", "g4", "g5", "g6"]))
        Hexagon.__layout.append( (0, ["f1", "f2", "f3", "f4", "f5", "f6", "f7"]))
        Hexagon.__layout.append( (1, ["e1", "e2", "e3", "e4", "e5", "e6"]))
        Hexagon.__layout.append( (0, ["d1", "d2", "d3", "d4", "d5", "d6", "d7"]))
        Hexagon.__layout.append( (1, ["c1", "c2", "c3", "c4", "c5", "c6"]))
        Hexagon.__layout.append( (0, ["b1", "b2", "b3", "b4", "b5", "b6", "b7"]))
        Hexagon.__layout.append( (1, ["a1", "a2", "a3", "a4", "a5", "a6"]))


    @staticmethod
    def __create_next_hexagons():

        Hexagon.__next_fst_indices = [None for _ in Hexagon.__all_sorted_hexagons]
        Hexagon.__next_snd_indices = [None for _ in Hexagon.__all_sorted_hexagons]

        for (hexagon_index, hexagon) in enumerate(Hexagon.__all_sorted_hexagons):
            (hexagon_u, hexagon_v) = hexagon.position_uv

            Hexagon.__next_fst_indices[hexagon_index] = array.array('b', [Hexagon.NULL for _ in HexagonDirection])
            Hexagon.__next_snd_indices[hexagon_index] = array.array('b', [Hexagon.NULL for _ in HexagonDirection])

            for hexagon_dir in HexagonDirection:
                hexagon_delta_u = Hexagon.__delta_u[hexagon_dir]
                hexagon_delta_v = Hexagon.__delta_v[hexagon_dir]

                hexagon_fst_u = hexagon_u + 1*hexagon_delta_u
                hexagon_fst_v = hexagon_v + 1*hexagon_delta_v

                hexagon_snd_u = hexagon_u + 2*hexagon_delta_u
                hexagon_snd_v = hexagon_v + 2*hexagon_delta_v

                if (hexagon_fst_u, hexagon_fst_v) in Hexagon.__position_uv_to_hexagon:
                    hexagon_fst = Hexagon.__position_uv_to_hexagon[(hexagon_fst_u, hexagon_fst_v)]
                    Hexagon.__next_fst_indices[hexagon_index][hexagon_dir] = hexagon_fst.index

                    if (hexagon_snd_u, hexagon_snd_v) in Hexagon.__position_uv_to_hexagon:
                        hexagon_snd = Hexagon.__position_uv_to_hexagon[(hexagon_snd_u, hexagon_snd_v)]
                        Hexagon.__next_snd_indices[hexagon_index][hexagon_dir] = hexagon_snd.index


    @staticmethod
    def __create_distance():
        for hexagon_1 in Hexagon.get_all():
            for hexagon_2 in Hexagon.get_all():
                distance = hex_distance(hexagon_1.position_uv, hexagon_2.position_uv)
                Hexagon.__distance[(hexagon_1.index, hexagon_2.index)] = distance


    @staticmethod
    def __create_distance_to_goal():

        Hexagon.__distance_to_goal = [ array.array('b',[ 0 for _ in Hexagon.get_all() ]) for _ in Player ]

        for player in Player:
            for hexagon_cube in Hexagon.get_all():
                for hexagon_goal_index in Hexagon.get_goal_indices(player):
                    distance = Hexagon.get_distance(hexagon_cube.index, hexagon_goal_index)
                    Hexagon.__distance_to_goal[player][hexagon_cube.index] = int(distance)


    @staticmethod
    def __create_hexagons():

        # Row "a"
        Hexagon('a1', (-1, -3))
        Hexagon('a2', (-0, -3))
        Hexagon('a3', (1, -3))
        Hexagon('a4', (2, -3))
        Hexagon('a5', (3, -3))
        Hexagon('a6', (4, -3))

        # Row "b"
        Hexagon('b1', (-2, -2))
        Hexagon('b2', (-1, -2))
        Hexagon('b3', (0, -2))
        Hexagon('b4', (1, -2))
        Hexagon('b5', (2, -2))
        Hexagon('b6', (3, -2))
        Hexagon('b7', (4, -2))

        # Row "c"
        Hexagon('c1', (-2, -1))
        Hexagon('c2', (-1, -1))
        Hexagon('c3', (0, -1))
        Hexagon('c4', (1, -1))
        Hexagon('c5', (2, -1))
        Hexagon('c6', (3, -1))

        # Row "d"
        Hexagon('d1', (-3, 0))
        Hexagon('d2', (-2, 0))
        Hexagon('d3', (-1, 0))
        Hexagon('d4', (0, 0))
        Hexagon('d5', (1, 0))
        Hexagon('d6', (2, 0))
        Hexagon('d7', (3, 0))

        # Row "e"
        Hexagon('e1', (-3, 1))
        Hexagon('e2', (-2, 1))
        Hexagon('e3', (-1, 1))
        Hexagon('e4', (0, 1))
        Hexagon('e5', (1, 1))
        Hexagon('e6', (2, 1))

        # Row "f"
        Hexagon('f1', (-4, 2))
        Hexagon('f2', (-3, 2))
        Hexagon('f3', (-2, 2))
        Hexagon('f4', (-1, 2))
        Hexagon('f5', (0, 2))
        Hexagon('f6', (1, 2))
        Hexagon('f7', (2, 2))

        # Row "g"
        Hexagon('g1', (-4, 3))
        Hexagon('g2', (-3, 3))
        Hexagon('g3', (-2, 3))
        Hexagon('g4', (-1, 3))
        Hexagon('g5', (0, 3))
        Hexagon('g6', (1, 3))


class HexState:

    Self = TypeVar("Self", bound="HexState")

    CODE_BASE = HexCode((2*2*2)*(2*2*2)*2)
    CODE_BASE_2 = CODE_BASE*CODE_BASE
    CODE_BASE_3 = CODE_BASE_2*CODE_BASE

    __slots__ = ('is_empty', 'has_stack', 'player', 'bottom', 'top', '__code')

    def __init__(self,
                 is_empty: bool=True,
                 has_stack: bool=False,
                 player: Optional[Player]=None,
                 bottom: Optional[CubeSort]=None,
                 top: Optional[CubeSort]=None):

        if is_empty:
            assert not has_stack
            assert player is None
            assert bottom is None
            assert top is None
        else:
            assert player is not None

            if has_stack:
                assert bottom is not None and top is not None
                if top == CubeSort.WISE:
                    assert bottom == CubeSort.WISE
            else:
                assert bottom is not None and top is None

        self.is_empty = is_empty
        self.has_stack = has_stack
        self.player = player
        self.bottom = bottom
        self.top = top
        self.__code = None


    @staticmethod
    def make_empty() -> Self:
        return HexState()


    @staticmethod
    def make_single(player: Player, cube: CubeSort) -> Self:
        return HexState(player=player, bottom=cube, is_empty=False)


    @staticmethod
    def make_stack(player: Player, bottom: CubeSort, top: CubeSort) -> Self:
        return HexState(player=player, bottom=bottom, top=top, is_empty=False, has_stack=True)


    def __str__(self):
        return ( f"HexState(is_empty={self.is_empty}" +
                 f", has_stack={self.has_stack}" +
                 f", player={self.player.name if self.player is not None else None}" +
                 f", bottom={self.bottom.name if self.bottom is not None else None}" +
                 f", top={self.top.name if self.top is not None else None})" )


    def __repr__(self):
        return str(self)


    def __eq__(self, other):
        return (self.is_empty == other.is_empty and
                self.has_stack == other.has_stack and
                self.player == other.player and
                self.bottom == other.bottom and
                self.top == other.top)


    def encode(self) -> HexCode:
        if self.__code is None:
            code = 0
            code +=   (0 if self.is_empty else 1)
            code += 2*(1 if self.has_stack else 0)
            code += 4*(self.player.value if self.player is not None else 0)
            code += 8*(self.bottom.value if self.bottom is not None else 0)
            code += 32*(self.top.value if self.top is not None else 0)

            assert 0 <= code < HexState.CODE_BASE

            if self.is_empty:
                assert code == 0

            self.__code = code

        return self.__code


    @staticmethod
    def decode(code: HexCode) -> Self:

        assert 0 <= code < HexState.CODE_BASE

        is_empty = True
        has_stack = False
        player = None
        bottom = None
        top = None

        rest = code

        bit_empty = rest % 2
        rest = rest // 2
        is_empty = bit_empty == 0

        if not is_empty:
            bit_stack = rest % 2
            rest = rest // 2
            has_stack = bit_stack != 0

            bit_player = rest % 2
            rest = rest // 2
            player = tuple(Player)[bit_player]

            bits_bottom = rest % 4
            rest = rest // 4
            bottom = tuple(CubeSort)[bits_bottom]

            if has_stack:
                bits_top = rest % 4
                rest = rest // 4
                top = tuple(CubeSort)[bits_top]

        assert rest == 0

        return HexState(is_empty=is_empty, has_stack=has_stack, player=player, bottom=bottom, top=top)


    @staticmethod
    def iterate_hex_states() -> Iterable[Self]:

        for is_empty in (True, False):

            if is_empty:
                has_stack = False
                player = None
                bottom = None
                top = None
                yield HexState(is_empty=is_empty,
                               has_stack=has_stack,
                               player=player,
                               bottom=bottom,
                               top=top)

            else:
                for player in Player:
                    for bottom in CubeSort:
                        for has_stack in (True, False):
                            if has_stack:
                                if bottom == CubeSort.WISE:
                                    for top in CubeSort:
                                        yield HexState(is_empty=is_empty,
                                                       has_stack=has_stack,
                                                       player=player,
                                                       bottom=bottom,
                                                       top=top)
                                else:
                                    for top in (CubeSort.ROCK, CubeSort.PAPER, CubeSort.SCISSORS):
                                        yield HexState(is_empty=is_empty,
                                                       has_stack=has_stack,
                                                       player=player,
                                                       bottom=bottom,
                                                       top=top)
                            else:
                                top = None
                                yield HexState(is_empty=is_empty,
                                               has_stack=has_stack,
                                               player=player,
                                               bottom=bottom,
                                               top=top)


PathStates = Sequence[HexState]
BoardStates = Sequence[HexState]


@dataclass
class Action:
    next_board_codes: Optional[(BoardCodes)] = None
    path_vertices: Optional[Path] = None
    capture_code: Optional[CaptureCode] = None
    move_code: Optional[MoveCode] = None
# Action = namedtuple('Action', field_names=['next_board_codes', 'path_vertices', 'capture_code', 'move_code'])

Actions = Sequence[Action]


class GameState:

    Self = TypeVar("Self", bound="HexState")

    __init_done = False
    __MAX_CREDIT = 20
    __slots__ = ('board_codes', 'is_terminal', 'credit', 'turn', 'current_player')


    TABLE_GOAL_INDICES = None
    TABLE_GOAL_DISTANCES = None

    TABLE_HAS_CUBE = None
    TABLE_HAS_STACK = None

    TABLE_CUBE_COUNT = None

    TABLE_HAS_FIGHTER = None
    TABLE_FIGHTER_COUNT = None

    TABLE_TRY_CUBE_PATH1_NEXT_CODE = None
    TABLE_TRY_CUBE_PATH1_CAPTURE_CODE = None

    TABLE_TRY_STACK_PATH1_NEXT_CODE = None
    TABLE_TRY_STACK_PATH1_CAPTURE_CODE = None

    TABLE_TRY_STACK_PATH2_NEXT_CODE = None
    TABLE_TRY_STACK_PATH2_CAPTURE_CODE = None

    MOVE_CODE_TO_NAMES = None
    CAPTURE_CODE_TO_NAMES = None


    def __init__(self,
                 board_codes: BoardCodes=None,
                 is_terminal: bool=False,
                 credit: int=__MAX_CREDIT,
                 turn: int=1,
                 current_player: Player=Player.WHITE):


        self.board_codes = board_codes if board_codes is not None else GameState.__make_default_board_codes()
        self.is_terminal = is_terminal
        self.credit = credit
        self.turn = turn
        self.current_player = current_player


    def is_terminated(self) -> bool:
        return (self.player_is_arrived(Player.WHITE) or
                self.player_is_arrived(Player.BLACK) or
                self.credit == 0 or
                not self.has_action())


    def has_action(self) -> bool:

        if not self.is_terminal:
            board_codes = self.board_codes
            current_player = self.current_player

            for cube_source in GameState.__find_cube_sources(board_codes, current_player):
                for cube_direction in HexagonDirection:
                    action1 = GameState.__try_cube_path1_action(board_codes, cube_source, cube_direction)
                    if action1 is not None:
                        return True
        return False


    def player_is_arrived(self, player: Player) -> bool:

        goal_indices = GameState.TABLE_GOAL_INDICES[player]
        has_fighter = GameState.TABLE_HAS_FIGHTER[player]

        goal_score = sum([has_fighter[self.board_codes[hex_index]] for hex_index in goal_indices])
        is_arrived = (goal_score != 0)

        return is_arrived


    def get_rewards(self) -> Optional[Tuple[Reward, Reward]]:

        rewards = [None for player in Player]

        if self.player_is_arrived(Player.WHITE):
            rewards[Player.WHITE] = Reward.WIN
            rewards[Player.BLACK] = Reward.LOSS

        elif self.player_is_arrived(Player.BLACK):
            rewards[Player.BLACK] = Reward.WIN
            rewards[Player.WHITE] = Reward.LOSS

        elif self.credit == 0:
            rewards[Player.WHITE] = Reward.DRAW
            rewards[Player.BLACK] = Reward.DRAW

        elif self.has_action():

            if self.current_player == Player.WHITE:
                rewards[Player.BLACK] = Reward.WIN
                rewards[Player.WHITE] = Reward.LOSS

            elif self.current_player == Player.BLACK:
                rewards[Player.WHITE] = Reward.WIN
                rewards[Player.BLACK] = Reward.LOSS

        else:
            rewards = None

        return rewards


    def get_actions(self) -> Actions:
        return self.__find_actions()


    def get_action_names(self) -> Actions:
        return [GameState.__make_action_name(action) for action in self.get_actions()]


    def get_fighter_counts(self)-> Sequence[int]:
        counts = [sum([GameState.TABLE_FIGHTER_COUNT[player][hex_code] for hex_code in self.board_codes ]) for player in Player]
        return counts


    def get_cube_counts(self)-> Sequence[int]:
        counts = [sum([GameState.TABLE_CUBE_COUNT[player][hex_code] for hex_code in self.board_codes ]) for player in Player]
        return counts


    def get_distances_to_goal(self) -> Sequence[Sequence[int]]:
        """White and black distances to goal"""

        distances_to_goal = list()

        for player in Player:
            has_fighter = GameState.TABLE_HAS_FIGHTER[player]
            goal_distances = GameState.TABLE_GOAL_DISTANCES[player]

            distances_to_goal.append([goal_distances[hex_index]
                                         for (hex_index, hex_code) in enumerate(self.board_codes)
                                         if has_fighter[hex_code] != 0])
        return distances_to_goal


    @staticmethod
    def encode_path_codes(path_codes: PathCodes) -> PathCode:

        path_length = len(path_codes)
        
        if path_length == 2:
            code = path_codes[0] + path_codes[1]*HexState.CODE_BASE

        elif path_length == 3:
            code = path_codes[0] + path_codes[1]*HexState.CODE_BASE + path_codes[2]*HexState.CODE_BASE_2

        else:
            code = 0
            shift = 1
            code_base = HexState.CODE_BASE
            for hex_code in path_codes:
                code += shift*hex_code
                shift *= code_base

        return code


    @staticmethod
    def decode_path_code(code: PathCode, path_length: int) -> PathCodes:

        assert code >= 0

        if path_length == 2:
            path_codes = (code % HexState.CODE_BASE,
                          (code // HexState.CODE_BASE) % HexState.CODE_BASE)

        elif path_length == 3:
            path_codes = (code % HexState.CODE_BASE,
                          (code // HexState.CODE_BASE) % HexState.CODE_BASE,
                          (code // HexState.CODE_BASE_2) % HexState.CODE_BASE)

        else:
            path_codes = list()

            rest = code
            for _ in range(path_length):
                hex_code = rest % HexState.CODE_BASE
                rest = rest // HexState.CODE_BASE
                path_codes.append(hex_code)

            assert rest == 0

        return path_codes


    @staticmethod
    def encode_path_states(path_states: PathStates) -> PathCode:
        return GameState.encode_path_codes([hex_state.encode() for hex_state in path_states])


    @staticmethod
    def decode_path_codes(path_codes: PathCodes) -> PathStates:
        return [HexState.decode(code) for code in path_codes]


    def show(self):

        shift = " " * len("a1KR")

        print()

        for (row_shift_count, row_hexagon_names) in Hexagon.get_layout():

            row_text = shift*row_shift_count

            for hexagon_name in row_hexagon_names:

                row_text += hexagon_name
                hexagon = Hexagon.get(hexagon_name)
                hexagon_index = hexagon.index

                hex_state = HexState.decode(self.board_codes[hexagon_index])

                if hex_state.is_empty:
                    row_text += ".."

                elif not hex_state.has_stack:
                    bottom_label = CUBE_TO_NAME[(hex_state.player, hex_state.bottom)]
                    row_text += "." + bottom_label

                elif hex_state.has_stack:
                    bottom_label = CUBE_TO_NAME[(hex_state.player, hex_state.bottom)]
                    top_label = CUBE_TO_NAME[(hex_state.player, hex_state.top)]
                    row_text += top_label + bottom_label

                row_text += shift
            print(row_text)


    @staticmethod
    def __make_action_name(action: Action) -> str:

        hexagons = Hexagon.get_all()

        hex_names = [hexagons[hex_index].name for hex_index in action.path_vertices]
        move_names = GameState.MOVE_CODE_TO_NAMES[action.move_code]
        capture_names = GameState.CAPTURE_CODE_TO_NAMES[action.capture_code]

        action_name = hex_names[0]
        for (move_name, hex_name, capture_name) in zip(move_names, hex_names[1:], capture_names):
            action_name += move_name + hex_name + capture_name

        return action_name


    @staticmethod
    def __make_empty_board_codes() -> BoardCodes :
        board_codes = array.array('B', [0 for _ in Hexagon.get_all()])
        return board_codes


    @staticmethod
    def __make_default_board_codes() -> BoardCodes :
        board_codes = GameState.__make_empty_board_codes()

        #-- Whites

        GameState.__set_stack_from_names(board_codes, 'b4', bottom_name='W', top_name='W')

        GameState.__set_cube_from_names(board_codes, 'a1', 'R')
        GameState.__set_cube_from_names(board_codes, 'a2', 'P')
        GameState.__set_cube_from_names(board_codes, 'a3', 'S')
        GameState.__set_cube_from_names(board_codes, 'a4', 'R')
        GameState.__set_cube_from_names(board_codes, 'a5', 'P')
        GameState.__set_cube_from_names(board_codes, 'a6', 'S')

        GameState.__set_cube_from_names(board_codes, 'b1', 'P')
        GameState.__set_cube_from_names(board_codes, 'b2', 'S')
        GameState.__set_cube_from_names(board_codes, 'b3', 'R')

        GameState.__set_cube_from_names(board_codes, 'b5', 'S')
        GameState.__set_cube_from_names(board_codes, 'b6', 'R')
        GameState.__set_cube_from_names(board_codes, 'b7', 'P')

        #-- Blacks

        GameState.__set_stack_from_names(board_codes, 'f4', bottom_name='w', top_name='w')

        GameState.__set_cube_from_names(board_codes, 'g6', 'r')
        GameState.__set_cube_from_names(board_codes, 'g5', 'p')
        GameState.__set_cube_from_names(board_codes, 'g4', 's')
        GameState.__set_cube_from_names(board_codes, 'g3', 'r')
        GameState.__set_cube_from_names(board_codes, 'g2', 'p')
        GameState.__set_cube_from_names(board_codes, 'g1', 's')

        GameState.__set_cube_from_names(board_codes, 'f7', 'p')
        GameState.__set_cube_from_names(board_codes, 'f6', 's')
        GameState.__set_cube_from_names(board_codes, 'f5', 'r')

        GameState.__set_cube_from_names(board_codes, 'f3', 's')
        GameState.__set_cube_from_names(board_codes, 'f2', 'r')
        GameState.__set_cube_from_names(board_codes, 'f1', 'p')

        return board_codes


    @staticmethod
    def __set_cube_from_names(board_codes: BoardCodes, hex_name: str, cube_name: str):
        hex_index = Hexagon.get(hex_name).index
        (player, cube) = CUBE_FROM_NAME[cube_name]
        GameState.__set_cube(board_codes, hex_index, player, cube)


    @staticmethod
    def __set_stack_from_names(board_codes: BoardCodes, hex_name: str, bottom_name: CubeSort, top_name: CubeSort):
        hex_index = Hexagon.get(hex_name).index
        (player, bottom) = CUBE_FROM_NAME[bottom_name]
        (top_player, top) = CUBE_FROM_NAME[top_name]
        assert top_player == player
        GameState.__set_stack(board_codes, hex_index, player, bottom, top)


    @staticmethod
    def __set_cube(board_codes: BoardCodes, hex_index: HexIndex, player: Player, cube: CubeSort):
        hex_state = HexState.decode(board_codes[hex_index])

        assert hex_state.is_empty

        hex_state.is_empty = False
        hex_state.player = player
        hex_state.bottom = cube
        board_codes[hex_index] = hex_state.encode()


    @staticmethod
    def __set_stack(board_codes: BoardCodes, hex_index: HexIndex, player: Player, bottom: CubeSort, top: CubeSort):
        hex_state = HexState.decode(board_codes[hex_index])

        assert hex_state.is_empty

        hex_state.is_empty = False
        hex_state.has_stack = True
        hex_state.player = player
        hex_state.bottom = bottom
        hex_state.top = top
        board_codes[hex_index] = hex_state.encode()


    def __find_actions(self) -> Actions:
        return self.__find_cube_first_actions() + self.__find_stack_first_actions()


    @staticmethod
    def __find_cube_sources(board_codes: BoardCodes, current_player: Player) -> Sources:
        table_code = GameState.TABLE_HAS_CUBE[current_player]
        return [hex_index for (hex_index, hex_code) in enumerate(board_codes) if table_code[hex_code] != 0]


    @staticmethod
    def __find_stack_sources(board_codes: BoardCodes, current_player: Player) -> Sources:
        table_code = GameState.TABLE_HAS_STACK[current_player]
        return [hex_index for (hex_index, hex_code) in enumerate(board_codes) if table_code[hex_code] != 0]


    @staticmethod
    def __make_path1(source: HexIndex, direction: HexagonDirection) -> Optional[Path]:

        next_fst_hex = Hexagon.get_next_fst_index(source, direction)

        if next_fst_hex != Hexagon.NULL:
            path = (source, next_fst_hex)

        else:
            path= None

        return path


    @staticmethod
    def __make_path2(source: HexIndex, direction: HexagonDirection) -> Optional[Path]:
        path = None

        next_fst_hex = Hexagon.get_next_fst_index(source, direction)

        if next_fst_hex != Hexagon.NULL:
            next_snd_hex = Hexagon.get_next_snd_index(source, direction)

            if next_snd_hex != Hexagon.NULL:
                path = (source, next_fst_hex, next_snd_hex)

        return path


    @staticmethod
    def __make_path_codes(board_codes: BoardCodes, path: Path) -> PathCodes:
        path_length = len(path)
        
        if path_length == 2:
            return [board_codes[path[0]],  board_codes[path[1]]]

        elif path_length == 3:
            return [board_codes[path[0]],  board_codes[path[1]], board_codes[path[2]]]

        else:
            return [board_codes[hex_index] for hex_index in path]


    @staticmethod
    def __try_path1(path_codes: PathCodes,
                  table_next_code: Sequence[HexCode],
                  table_has_capture: Sequence[bool]) -> Tuple[Optional[PathCodes], bool]:

        path_length = len(path_codes)
        assert path_length == 2

        code = GameState.encode_path_codes(path_codes)
        next_code = table_next_code[code]

        if next_code != 0:
            next_path_codes = GameState.decode_path_code(next_code, path_length)
            capture_code = table_has_capture[code]

        else:
            next_path_codes = None
            capture_code = False

        return (next_path_codes, capture_code)


    @staticmethod
    def __try_path2(path_codes: PathCodes,
                  table_next_code: Sequence[HexCode],
                  table_has_capture: Sequence[bool]) -> Tuple[Optional[PathCodes], bool]:

        path_length = len(path_codes)
        assert path_length == 3

        next_path_codes = None
        capture_code = False

        # >> Optimization: if the intermediate hexagon is not empty then the stack cannot cross it
        # >> Such optimization is reducing the size of the index domain of table_next_code and table_has_capture
        if path_codes[1] == 0:
            compressed_path_codes = [path_codes[0], path_codes[2]]
            code = GameState.encode_path_codes(compressed_path_codes)
            next_code = table_next_code[code]

            if next_code != 0:
                # >> next_code is encoding a three hexagons path state
                next_path_codes = GameState.decode_path_code(next_code, path_length)
                capture_code = table_has_capture[code]

        return (next_path_codes, capture_code)


    @staticmethod
    def __try_cube_path1(path_codes: PathCodes) -> Tuple[Optional[PathCodes], bool]:
        return GameState.__try_path1(path_codes, GameState.TABLE_TRY_CUBE_PATH1_NEXT_CODE, GameState.TABLE_TRY_CUBE_PATH1_CAPTURE_CODE)


    @staticmethod
    def __try_stack_path1(path_codes: PathCodes) -> Tuple[Optional[PathCodes], bool]:
        return GameState.__try_path1(path_codes, GameState.TABLE_TRY_STACK_PATH1_NEXT_CODE, GameState.TABLE_TRY_STACK_PATH1_CAPTURE_CODE)


    @staticmethod
    def __try_stack_path2(path_codes: PathCodes) -> Tuple[PathCodes, bool]:
        return GameState.__try_path2(path_codes, GameState.TABLE_TRY_STACK_PATH2_NEXT_CODE, GameState.TABLE_TRY_STACK_PATH2_CAPTURE_CODE)


    @staticmethod
    def __apply_path_codes(board_codes: BoardCodes, path: Path, path_codes: PathCodes) -> BoardCodes:
        next_board_codes = copy.copy(board_codes)
        
        path_length = len(path)

        if path_length == 2:
            next_board_codes[path[0]] = path_codes[0]
            next_board_codes[path[1]] = path_codes[1]

        elif path_length == 3:
            next_board_codes[path[0]] = path_codes[0]
            next_board_codes[path[1]] = path_codes[1]
            next_board_codes[path[2]] = path_codes[2]

        else:
            for (hex_index, hex_code) in zip(path, path_codes):
                next_board_codes[hex_index] = hex_code

        return next_board_codes


    @staticmethod
    def __try_cube_path1_action(board_codes: BoardCodes, source: HexIndex, direction: HexagonDirection) -> Optional[Action]:
        return GameState.__try_path_action(board_codes, source, direction,
                                           GameState.__make_path1, GameState.__try_cube_path1, move_code=0)


    @staticmethod
    def __try_stack_path1_action(board_codes: BoardCodes, source: HexIndex, direction: HexagonDirection) -> Optional[Action]:
        return GameState.__try_path_action(board_codes, source, direction,
                                           GameState.__make_path1, GameState.__try_stack_path1, move_code=1)


    @staticmethod
    def __try_stack_path2_action(board_codes: BoardCodes, source: HexIndex, direction: HexagonDirection) -> Optional[Action]:
        return GameState.__try_path_action(board_codes, source, direction,
                                           GameState.__make_path2, GameState.__try_stack_path2, move_code=1)


    @staticmethod
    def __try_path_action(board_codes: BoardCodes, source: HexIndex, direction: HexagonDirection,
                        make_path: Callable[ [HexIndex, HexagonDirection], Optional[Path] ],
                        try_path: Callable[ [PathCodes], Tuple[Optional[PathCodes], bool] ],
                        move_code: MoveCode) -> Optional[Action]:
        action = None
        path = make_path(source, direction)
        if path is not None:
            path_codes = GameState.__make_path_codes(board_codes, path)
            (next_path_codes, capture_code) = try_path(path_codes)
            if next_path_codes is not None:
                action = Action(next_board_codes=GameState.__apply_path_codes(board_codes, path, next_path_codes),
                                path_vertices=[source, path[-1]],
                                capture_code=capture_code,
                                move_code=move_code)

        return action


    def __find_cube_first_actions(self) -> Actions:
        actions = list()

        if not self.is_terminal:
            board_codes = self.board_codes
            current_player = self.current_player

            for cube_source in GameState.__find_cube_sources(board_codes, current_player):

                for cube_direction in HexagonDirection:
                    action1 = GameState.__try_cube_path1_action(board_codes, cube_source, cube_direction)
                    if action1 is not None:
                        actions.append(action1)

                        board_codes_1 = action1.next_board_codes
                        stack_source = action1.path_vertices[-1]
                        if GameState.TABLE_HAS_STACK[current_player][board_codes_1[stack_source]] != 0:
                            for stack_direction in HexagonDirection:
                                action21 = GameState.__try_stack_path1_action(board_codes_1, stack_source, stack_direction)
                                if action21 is not None:
                                    action21 = Action(next_board_codes=action21.next_board_codes,
                                                      path_vertices=action1.path_vertices + [action21.path_vertices[-1]],
                                                      capture_code=action1.capture_code + 2*action21.capture_code,
                                                      move_code=action1.move_code + 2*action21.move_code)
                                    actions.append(action21)

                                    action22 = GameState.__try_stack_path2_action(board_codes_1, stack_source, stack_direction)
                                    if action22 is not None:
                                        action22 = Action(next_board_codes=action22.next_board_codes,
                                                          path_vertices=action1.path_vertices + [action22.path_vertices[-1]],
                                                          capture_code=action1.capture_code + 2*action22.capture_code,
                                                          move_code=action1.move_code + 2*action22.move_code)
                                        actions.append(action22)

        return actions


    def __find_stack_first_actions(self) -> Actions:
        actions = list()
        if not self.is_terminal:
            board_codes = self.board_codes
            current_player = self.current_player

            for stack_source in GameState.__find_stack_sources(board_codes, current_player):
                for stack_direction in HexagonDirection:

                    action11 = GameState.__try_stack_path1_action(board_codes, stack_source, stack_direction)
                    if action11 is not None:
                        actions.append(action11)

                        board_codes_11 = action11.next_board_codes
                        cube_source = action11.path_vertices[-1]
                        for cube_direction in HexagonDirection:
                            action12 = GameState.__try_cube_path1_action(board_codes_11, cube_source, cube_direction)
                            if action12 is not None:
                               action12 = Action(next_board_codes=action12.next_board_codes,
                                                 path_vertices=action11.path_vertices + [action12.path_vertices[-1]],
                                                 capture_code=action11.capture_code + 2*action12.capture_code,
                                                 move_code=action11.move_code + 2*action12.move_code)
                               actions.append(action12)

                        action21 = GameState.__try_stack_path2_action(board_codes, stack_source, stack_direction)
                        if action21 is not None:
                            actions.append(action21)

                            board_codes_21 = action21.next_board_codes
                            cube_source = action21.path_vertices[-1]
                            for cube_direction in HexagonDirection:
                                action22 = GameState.__try_cube_path1_action(board_codes_21, cube_source, cube_direction)
                                if action22 is not None:
                                   action22 = Action(next_board_codes=action22.next_board_codes,
                                                     path_vertices=action21.path_vertices + [action22.path_vertices[-1]],
                                                     capture_code=action21.capture_code + 2*action22.capture_code,
                                                     move_code=action21.move_code + 2*action22.move_code )
                                   actions.append(action22)

        return actions


    @staticmethod
    def init():


        def create_tables_try_cube_path1() -> Tuple[Sequence[PathCode], Sequence[CaptureCode]]:
            table_next_code = array.array('H', [0 for _ in range(HexState.CODE_BASE_2)])
            table_has_capture = array.array('B', [0 for _ in range(HexState.CODE_BASE_2)])

            for src_state in HexState.iterate_hex_states():
                for dst_state in HexState.iterate_hex_states():
                    code = GameState.encode_path_states([src_state, dst_state])

                    next_code = 0
                    capture_code = 0

                    next_src_state = None
                    next_dst_state = None

                    if not src_state.is_empty:

                        if dst_state.is_empty:
                            #-- Just moves without stacking rules involved
                            if src_state.has_stack:
                                next_src_state = HexState.make_single(player=src_state.player, cube=src_state.bottom)
                                next_dst_state = HexState.make_single(player=src_state.player, cube=src_state.top)

                            else:
                                next_src_state = HexState.make_empty()
                                next_dst_state = HexState.make_single(player=src_state.player, cube=src_state.bottom)

                        elif dst_state.player == src_state.player:
                            # >> Stacking rules must be considered
                            if not dst_state.has_stack:
                                # == Destination has a single cube owned by the active player
                                if src_state.has_stack:
                                    if src_state.top != CubeSort.WISE or (src_state.top == CubeSort.WISE and dst_state.bottom == CubeSort.WISE):
                                        next_src_state = HexState.make_single(player=src_state.player, cube=src_state.bottom)
                                        next_dst_state = HexState.make_stack(player=src_state.player, bottom=dst_state.bottom, top=src_state.top)

                                else:
                                    if src_state.bottom != CubeSort.WISE or (src_state.bottom == CubeSort.WISE and dst_state.bottom == CubeSort.WISE):
                                        next_src_state = HexState.make_empty()
                                        next_dst_state = HexState.make_stack(player=src_state.player, bottom=dst_state.bottom, top=src_state.bottom)

                        else:
                            # >> Capturing rules must be considered
                            if dst_state.has_stack:
                                # == Destination has a stack owned by the non-active player

                                if src_state.has_stack:
                                    if CubeSort_beats(src_state.top, dst_state.top):
                                        capture_code = 1
                                        next_src_state = HexState.make_single(player=src_state.player, cube=src_state.bottom)
                                        next_dst_state = HexState.make_single(player=src_state.player, cube=src_state.top)

                                else:
                                    if CubeSort_beats(src_state.bottom, dst_state.top):
                                        capture_code = 1
                                        next_src_state = HexState.make_empty()
                                        next_dst_state = HexState.make_single(player=src_state.player, cube=src_state.bottom)

                            else:
                                # == Destination has a single cube owned by the non-active player

                                if src_state.has_stack:
                                    if CubeSort_beats(src_state.top, dst_state.bottom):
                                        capture_code = 1
                                        next_src_state = HexState.make_single(player=src_state.player, cube=src_state.bottom)
                                        next_dst_state = HexState.make_single(player=src_state.player, cube=src_state.top)
                                else:
                                    if CubeSort_beats(src_state.bottom, dst_state.bottom):
                                        capture_code = 1
                                        next_src_state = HexState.make_empty()
                                        next_dst_state = HexState.make_single(player=src_state.player, cube=src_state.bottom)

                        if next_src_state is not None and next_dst_state is not None:
                            next_code = GameState.encode_path_states([next_src_state, next_dst_state])

                    table_next_code[code] = next_code
                    table_has_capture[code] = capture_code

            return (table_next_code, table_has_capture)


        def create_tables_try_stack_path(table_next_code: Sequence[PathCode] ,
                                       table_has_capture: Sequence[CaptureCode],
                                       next_mid_state=Optional[HexState]) -> None:

            for src_state in HexState.iterate_hex_states():
                for dst_state in HexState.iterate_hex_states():
                    code = GameState.encode_path_states([src_state, dst_state])

                    next_code = 0
                    capture_code = 0

                    next_src_state = None
                    next_dst_state = None

                    if not src_state.is_empty and src_state.has_stack:

                        if dst_state.is_empty:
                            #-- Just moves without stacking rules involved
                            next_src_state = HexState.make_empty()
                            next_dst_state = HexState.make_stack(player=src_state.player, bottom=src_state.bottom, top=src_state.top)

                        elif dst_state.player != src_state.player:
                            # >> Capturing rules must be considered

                            if dst_state.has_stack:
                                # == Destination has a stack owned by the non-active player
                                if CubeSort_beats(src_state.top, dst_state.top):
                                    capture_code = 1
                                    next_src_state = HexState.make_empty()
                                    next_dst_state = HexState.make_stack(player=src_state.player, bottom=src_state.bottom, top=src_state.top)

                            else:
                                # == Destination has a single cube owned by the non-active player
                                if CubeSort_beats(src_state.top, dst_state.bottom):
                                    capture_code = 1
                                    next_src_state = HexState.make_empty()
                                    next_dst_state = HexState.make_stack(player=src_state.player, bottom=src_state.bottom, top=src_state.top)

                        if next_src_state is not None and next_dst_state is not None:

                            if next_mid_state is None:
                                next_code = GameState.encode_path_states([next_src_state, next_dst_state])

                            else:
                                next_code = GameState.encode_path_states([next_src_state, next_mid_state, next_dst_state])

                    table_next_code[code] = next_code
                    table_has_capture[code] = capture_code

            return (table_next_code, table_has_capture )


        def create_tables_try_stack_path1() -> Tuple[Sequence[PathCode], Sequence[CaptureCode]]:
            table_next_code = array.array('H', [0 for _ in range(HexState.CODE_BASE_2)])
            table_has_capture = array.array('B', [0 for _ in range(HexState.CODE_BASE_2)])

            create_tables_try_stack_path(table_next_code, table_has_capture, next_mid_state=None)

            return (table_next_code, table_has_capture)


        def create_tables_try_stack_path2() -> Tuple[Sequence[PathCode], Sequence[CaptureCode]]:
            table_next_code = array.array('L', [0 for _ in range(HexState.CODE_BASE_2)])
            table_has_capture = array.array('B', [0 for _ in range(HexState.CODE_BASE_2)])

            create_tables_try_stack_path(table_next_code, table_has_capture, next_mid_state=HexState.make_empty())

            return (table_next_code, table_has_capture)


        def create_table_has_cube() -> Sequence[Sequence[int]]:
            table = [ array.array('B', [0 for _ in range(HexState.CODE_BASE)]) for _ in Player]

            for hex_state in HexState.iterate_hex_states():

                if not hex_state.is_empty:
                    count = 1
                    hex_code = hex_state.encode()
                    table[hex_state.player][hex_code] = count

            return table


        def create_table_has_stack() -> Sequence[Sequence[int]]:
            table = [ array.array('B', [0 for _ in range(HexState.CODE_BASE)]) for _ in Player]

            for hex_state in HexState.iterate_hex_states():

                if not hex_state.is_empty and hex_state.has_stack:
                    count = 1
                    hex_code = hex_state.encode()
                    table[hex_state.player][hex_code] = count

            return table


        def create_table_cube_count() -> Sequence[Sequence[int]]:
            table = [ array.array('B', [0 for _ in range(HexState.CODE_BASE)]) for _ in Player]

            for hex_state in HexState.iterate_hex_states():

                if not hex_state.is_empty:

                    if hex_state.has_stack:
                        count = 2
                    else:
                        count = 1

                    hex_code = hex_state.encode()
                    table[hex_state.player][hex_code] = count

            return table


        def create_table_has_fighter() -> Sequence[Sequence[int]]:
            table = [ array.array('B', [0 for _ in range(HexState.CODE_BASE)]) for _ in Player]

            for hex_state in HexState.iterate_hex_states():

                if not hex_state.is_empty:

                    if hex_state.has_stack:
                        count = 0
                        count = max(count, 1 if hex_state.bottom != CubeSort.WISE else 0)
                        count = max(count, 1 if hex_state.top != CubeSort.WISE else 0)
                    else:
                        count = 1 if hex_state.bottom != CubeSort.WISE else 0

                    hex_code = hex_state.encode()
                    table[hex_state.player][hex_code] = count

            return table


        def create_table_fighter_count() -> Sequence[Sequence[int]]:
            table = [ array.array('B', [0 for _ in range(HexState.CODE_BASE)]) for _ in Player]

            for hex_state in HexState.iterate_hex_states():

                if not hex_state.is_empty:

                    if hex_state.has_stack:
                        count = 0
                        count += 1 if hex_state.bottom != CubeSort.WISE else 0
                        count += 1 if hex_state.top != CubeSort.WISE else 0
                    else:
                        count = 1 if hex_state.bottom != CubeSort.WISE else 0

                    hex_code = hex_state.encode()
                    table[hex_state.player][hex_code] = count

            return table


        def make_goal_scores() -> Sequence[Sequence[int]]:
            table = [array.array('B', [0 for _ in range(HexState.CODE_BASE)]) for _ in Player]

            for hex_state in HexState.iterate_hex_states():

                if hex_state.is_empty:
                    count = 0

                else:

                    if hex_state.has_stack:
                        count = 0
                        count += 1 if hex_state.bottom != CubeSort.WISE else 0
                        count += 1 if hex_state.top != CubeSort.WISE else 0

                    else:
                        count = 1 if hex_state.bottom != CubeSort.WISE else 0

                    hex_code = hex_state.encode()
                    table[hex_code][hex_state.player] = count
            return table


        if not GameState.__init_done:

            GameState.TABLE_GOAL_INDICES = [Hexagon.get_goal_indices(player) for player in Player]

            GameState.TABLE_GOAL_DISTANCES = [ [Hexagon.get_distance_to_goal(hex_index, player)
                                      for hex_index in Hexagon.get_all_indices() ]
                                    for player in Player]

            GameState.TABLE_HAS_CUBE = create_table_has_cube()
            GameState.TABLE_HAS_STACK = create_table_has_stack()

            GameState.TABLE_CUBE_COUNT = create_table_cube_count()

            GameState.TABLE_HAS_FIGHTER = create_table_has_fighter()

            GameState.TABLE_FIGHTER_COUNT= create_table_fighter_count()

            ( GameState.TABLE_TRY_CUBE_PATH1_NEXT_CODE,
              GameState.TABLE_TRY_CUBE_PATH1_CAPTURE_CODE ) =  create_tables_try_cube_path1()

            ( GameState.TABLE_TRY_STACK_PATH1_NEXT_CODE,
              GameState.TABLE_TRY_STACK_PATH1_CAPTURE_CODE ) = create_tables_try_stack_path1()

            ( GameState.TABLE_TRY_STACK_PATH2_NEXT_CODE,
              GameState.TABLE_TRY_STACK_PATH2_CAPTURE_CODE ) = create_tables_try_stack_path2()

            GameState.MOVE_CODE_TO_NAMES = [None for _ in range(4)]
            GameState.MOVE_CODE_TO_NAMES[0] = ['-', '']
            GameState.MOVE_CODE_TO_NAMES[1] = ['=', '-']
            GameState.MOVE_CODE_TO_NAMES[2] = ['-', '=']
            GameState.MOVE_CODE_TO_NAMES[3] = ['=', '-']

            GameState.CAPTURE_CODE_TO_NAMES = [None for _ in range(4)]
            GameState.CAPTURE_CODE_TO_NAMES[0] = ['', '']
            GameState.CAPTURE_CODE_TO_NAMES[1] = ['!', '']
            GameState.CAPTURE_CODE_TO_NAMES[2] = ['', '!']
            GameState.CAPTURE_CODE_TO_NAMES[3] = ['!', '!']

            GameState.__init_done = True

    @staticmethod
    def print_tables():


        def print_tables_try_cube_path1():
            print()
            print("-- print_tables_try_cube_path1 --")
            print(GameState.TABLE_TRY_CUBE_PATH1_NEXT_CODE)
            print(GameState.TABLE_TRY_CUBE_PATH1_CAPTURE_CODE)


        def print_tables_try_stack_path1():
            print()
            print("-- print_tables_try_stack_path1 --")
            print(GameState.TABLE_TRY_STACK_PATH1_NEXT_CODE)
            print(GameState.TABLE_TRY_STACK_PATH1_CAPTURE_CODE)


        def print_tables_try_stack_path2():
            print()
            print("-- print_tables_try_stack_path2 --")
            print(GameState.TABLE_TRY_STACK_PATH2_NEXT_CODE)
            print(GameState.TABLE_TRY_STACK_PATH2_CAPTURE_CODE)


        def print_table_has_cube():
            print()
            print("-- print_table_has_cube --")
            print(GameState.TABLE_HAS_CUBE)


        def print_table_has_stack():
            print()
            print("-- print_table_has_stack --")
            print(GameState.TABLE_HAS_STACK)


        def print_table_cube_count():
            print()
            print("-- print_table_cube_count --")
            print(GameState.TABLE_CUBE_COUNT)


        def print_table_has_fighter():
            print()
            print("-- print_table_has_fighter --")
            print(GameState.TABLE_HAS_FIGHTER)


        def print_table_fighter_count():
            print()
            print("-- print_table_fighter_count --")
            print(GameState.TABLE_FIGHTER_COUNT)


        print_table_cube_count()
        print_table_has_cube()

        print_table_fighter_count()
        print_table_has_fighter()

        print_tables_try_cube_path1()
        print_tables_try_stack_path1()
        print_tables_try_stack_path2()

def test():


    def generate_random_hex_state(is_empty: Optional[bool]=None,
                                  has_stack: Optional[bool]=None,
                                  player: Optional[Player]=None,
                                  bottom: Optional[CubeSort]=None,
                                  top: Optional[CubeSort]=None) -> HexState:

        is_empty = random.choice((True, False)) if is_empty is None else is_empty
        if not is_empty:
            player = random.choice(tuple(Player)) if player is None else player
            bottom = random.choice(tuple(CubeSort)) if bottom is None else bottom
            has_stack = random.choice((True, False)) if has_stack is None else has_stack
            if has_stack:
                if bottom == CubeSort.WISE:
                    top = random.choice(tuple(CubeSort)) if top is None else top
                else:
                    top = random.choice((CubeSort.ROCK, CubeSort.PAPER, CubeSort.SCISSORS)) if top is None else top

        else:
            has_stack = False
            player = None
            bottom = None
            top = None

        return HexState(is_empty=is_empty, has_stack=has_stack, player=player, bottom=bottom, top=top)


    def generate_random_path_state(path_length: int) -> PathStates:
        assert path_length >= 0
        path_state = [generate_random_hex_state() for _ in range(path_length)]
        return path_state


    def test_iterate_hex_states() -> None:

        print()
        print("-- test_iterate_hex_states --")

        hex_codes = set()

        for hex_state in HexState.iterate_hex_states():
            hex_code = hex_state.encode()
            print(f"hex_state = {hex_state} ; hex_code={hex_code}")
            assert hex_code not in hex_codes
            hex_codes.add(hex_code)

        print(f"len(hex_codes) = {len(hex_codes)} ; min(hex_codes) = {min(hex_codes)} ; max(hex_codes) = {max(hex_codes)}")
        assert len(hex_codes) <= HexState.CODE_BASE
        assert min(hex_codes) == 0
        assert max(hex_codes) <= HexState.CODE_BASE


    def test_encode_and_decode_hex_state():

        print()
        print("-- test_encode_and_decode_hex_state --")

        hex_state_count = 100

        for _ in range(hex_state_count):

            hex_state = generate_random_hex_state()
            print()
            print(f"hex_state = {hex_state}")

            hex_state_code = hex_state.encode()
            print(f"hex_state_code = {hex_state_code}")

            hex_decoded_state = HexState.decode(hex_state_code)
            print(f"hex_decoded_state = {hex_decoded_state}")
            assert hex_decoded_state == hex_state

        hex_state_count = 100

        for _ in range(hex_state_count):

            hex_state = generate_random_hex_state(is_empty=False, has_stack=True, bottom=CubeSort.WISE)
            print()
            print(f"hex_state = {hex_state}")

            hex_state_code = hex_state.encode()
            print(f"hex_state_code = {hex_state_code}")

            hex_decoded_state = HexState.decode(hex_state_code)
            print(f"hex_decoded_state = {hex_decoded_state}")
            assert hex_decoded_state == hex_state


    def test_encode_and_decode_path_states() -> None:

        print()
        print("-- test_encode_and_decode_path_states --")

        path_state_count = 100
        path_length = 3

        for _ in range(path_state_count):
            path_state = generate_random_path_state(path_length)
            print()
            print(f"path_state = {path_state}")

            path_code = GameState.encode_path_states(path_state)
            print(f"path_code = {path_code}")

            path_codes = GameState.decode_path_code(path_code, path_length)
            print(f"path_codes = {path_codes}")

            path_decoded_state = GameState.decode_path_codes(path_codes)
            print(f"path_decoded_state = {path_decoded_state}")
            assert path_decoded_state == path_state


    def test_iteration_technics():

        print()
        print("-- test_iteration_technics --")

        board_state = [generate_random_hex_state() for _ in range(45)]

        def do_list():
            distances_to_goal = list()

            for player in Player:
                has_fighter = GameState.TABLE_HAS_FIGHTER[player]
                goal_distances = GameState.TABLE_GOAL_DISTANCES[player]

                distances = list()
                for (hex_index, hex_state) in enumerate(board_state):
                    if has_fighter[hex_state.encode()] != 0:
                        distances.append(goal_distances[hex_index])

                distances_to_goal.append(distances)
            return distances_to_goal


        def do_for():
            distances_to_goal = list()

            for player in Player:
                has_fighter = GameState.TABLE_HAS_FIGHTER[player]
                goal_distances = GameState.TABLE_GOAL_DISTANCES[player]

                distances_to_goal.append([goal_distances[hex_index]
                                              for (hex_index, hex_state) in enumerate(board_state)
                                              if has_fighter[hex_state.encode()] != 0])
            return distances_to_goal

        distances_to_goal = do_list()
        print("(len(distances_to_goal[0], len(distances_to_goal[1]) = ", (len(distances_to_goal[0]), len(distances_to_goal[1])))
        distances_to_goal = do_for()
        print("(len(distances_to_goal[0], len(distances_to_goal[1]) = ", (len(distances_to_goal[0]), len(distances_to_goal[1])))

        do_for_time = timeit.timeit(do_for, number=1_000)
        do_list_time = timeit.timeit(do_list, number=1_000)
        print("do_list() => ", do_list_time)
        print("do_for() => ", do_for_time, ', (do_for_time/do_list_time - 1)*100 =', (do_for_time/do_list_time -1)*100)


    def test_encode_technics():

        print()
        print("-- test_encode_technics --")

        path_codes = [random.randint(0, HexState.CODE_BASE - 1) for _ in range(3)]

        def do_tech1():
            code = 0
            shift = 1
            for hex_code in path_codes:
                code += shift*hex_code
                shift *= HexState.CODE_BASE
            return code


        def do_tech2():
            return sum(hex_code*pow(HexState.CODE_BASE, hex_index) for (hex_index, hex_code) in enumerate(path_codes))


        print(f"path_codes = {path_codes}")
        print(f"do_tech1() = {do_tech1()} ")
        print(f"do_tech2() = {do_tech2()} ")

        time1 = timeit.timeit(do_tech1, number=1_000)
        time2 = timeit.timeit(do_tech2, number=1_000)
        print("do_tech1() => ", time1)
        print("do_tech2() => ", time2, ', (time1/time2 - 1)*100 =', (time1/time2 -1)*100)


    def test_game_state():

        print()
        print("-- test_game_state --")

        game_state = GameState()
        print("game_state =>")
        game_state.show()

        print()
        print(f"game_state.is_terminated() = {game_state.is_terminated()}")
        print(f"game_state.has_action() = {game_state.has_action()}")

        action_names = game_state.get_action_names()
        action_name_set = set(action_names)

        pijersi_state = rules.PijersiState()
        pijersi_action_names = pijersi_state.get_action_names()
        pijersi_action_name_set = set(pijersi_action_names)

        assert len(action_name_set) == len(pijersi_action_name_set)
        assert action_name_set == pijersi_action_name_set


        def do_new():
            tmp_actions = game_state.get_actions()
            assert len(tmp_actions) == len(pijersi_action_name_set)


        def do_old():
            tmp_actions = pijersi_state.get_actions()
            assert len(tmp_actions) == len(pijersi_action_name_set)


        time_new = timeit.timeit(do_new, number=100)
        time_old = timeit.timeit(do_old, number=100)
        print("do_new() => ", time_new)
        print("do_old() => ", time_old,
              ', (time_new/time_old - 1)*100 =', (time_new/time_old -1)*100,
              ', time_old/time_new = ', time_old/time_new)


    test_encode_and_decode_hex_state()
    test_encode_and_decode_path_states()
    test_iterate_hex_states()

    GameState.print_tables()

    test_iteration_technics()
    test_encode_technics()

    test_game_state()


def do_profile():
    for _ in range(1_000):
        tmp_actions = do_profile_game_state.get_actions()
        assert len(tmp_actions) == 186


def main():
    Hexagon.init()
    GameState.init()
    test()


if __name__ == "__main__":
    print()
    print("Hello")
    print(f"sys.version = {sys.version}")

    main()

    if True:
        do_profile_game_state = GameState()
        cProfile.run('do_profile()', sort=SortKey.CUMULATIVE)

    print()
    print("Bye")

    if True:
        print()
        _ = input("main: done ; press enter to terminate")
