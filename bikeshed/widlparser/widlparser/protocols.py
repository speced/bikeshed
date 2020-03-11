# coding=utf-8
#
#  Copyright © 2013 Hewlett-Packard Development Company, L.P.
#
#  This work is distributed under the W3C® Software License [1]
#  in the hope that it will be useful, but WITHOUT ANY
#  WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
#  [1] http://www.w3.org/Consortium/Legal/2002/copyright-software-20021231
#
"""Protocol definitions."""

from typing import Iterator, List, Optional, Sequence, Tuple, Union

from typing_extensions import Protocol


class SymbolTable(Protocol):
    """Protocol for symbol capture and lookup."""

    def add_type(self, type: 'Construct') -> None:
        ...

    def get_type(self, name: str) -> Optional['Construct']:
        ...


class Production(Protocol):
    """Protocol for all productions."""

    leading_space: str
    semicolon: Union[str, 'Production']
    trailing_space: str

    @property
    def tail(self) -> str:
        ...

    def __str__(self) -> str:
        ...

    def _define_markup(self, generator: 'MarkupGenerator') -> 'Production':
        ...

    def define_markup(self, generator: 'MarkupGenerator') -> None:
        ...


class ChildProduction(Protocol):
    """Protocol for productions that have parents."""

    @property
    def idl_type(self) -> str:
        ...

    @property
    def name(self) -> Optional[str]:
        ...

    @property
    def normal_name(self) -> Optional[str]:
        ...

    @property
    def full_name(self) -> Optional[str]:
        ...

    def _define_markup(self, generator: 'MarkupGenerator') -> 'Production':
        ...

    def define_markup(self, generator: 'MarkupGenerator') -> None:
        ...

    @property
    def method_name(self) -> Optional[str]:
        ...

    @property
    def method_names(self) -> List[str]:
        ...

    @property
    def arguments(self) -> Optional['ArgumentList']:
        ...

    @property
    def symbol_table(self) -> Optional[SymbolTable]:
        ...

    def __str__(self) -> str:
        ...


class ConstructMap(Protocol):
    """Mapping of name to Construct."""

    def __len__(self) -> int:
        ...

    def __getitem__(self, key: Union[str, int]) -> 'Construct':
        ...

    def __contains__(self, key: Union[str, int]) -> bool:
        ...

    def __iter__(self) -> Iterator['Construct']:
        ...

    def keys(self) -> Sequence[str]:
        ...

    def values(self) -> Sequence['Construct']:
        ...

    def items(self) -> Sequence[Tuple[str, 'Construct']]:
        ...

    def get(self, key: Union[str, int]) -> Optional['Construct']:
        ...


class ArgumentList(Protocol):
    """List of arguments."""

    def __len__(self) -> int:
        ...

    def __getitem__(self, key: Union[str, int]) -> 'Construct':
        ...

    def __contains__(self, key: Union[str, int]) -> bool:
        ...

    def __iter__(self) -> Iterator['Construct']:
        ...

    def keys(self) -> Sequence[str]:
        ...

    def values(self) -> Sequence['Construct']:
        ...

    def items(self) -> Sequence[Tuple[str, 'Construct']]:
        ...

    def get(self, key: Union[str, int]) -> Optional['Construct']:
        ...

    @property
    def argument_names(self) -> Sequence[str]:
        ...

    def matches_names(self, argument_names: Sequence[str]) -> bool:
        ...


class Construct(Protocol):
    """Base class for high-level language constructs."""

    @property
    def idl_type(self) -> str:
        ...

    @property
    def name(self) -> Optional[str]:
        ...

    @property
    def normal_name(self) -> Optional[str]:
        ...

    @property
    def full_name(self) -> Optional[str]:
        ...

    @property
    def constructors(self) -> List['Construct']:
        ...

    @property
    def method_name(self) -> Optional[str]:
        ...

    @property
    def method_names(self) -> List[str]:
        ...

    @property
    def arguments(self) -> Optional[ArgumentList]:
        ...

    @property
    def symbol_table(self) -> Optional[SymbolTable]:
        ...

    @property
    def extended_attributes(self) -> Optional[ConstructMap]:
        ...

    def __bool__(self) -> bool:
        ...

    def __len__(self) -> int:
        ...

    def __getitem__(self, key: Union[str, int]) -> 'Construct':
        ...

    def __contains__(self, key: Union[str, int]) -> bool:
        ...

    def __iter__(self) -> Iterator['Construct']:
        ...

    def __reversed__(self) -> Iterator['Construct']:
        ...

    def keys(self) -> Sequence[str]:
        ...

    def values(self) -> Sequence['Construct']:
        ...

    def items(self) -> Sequence[Tuple[str, 'Construct']]:
        ...

    def get(self, key: Union[str, int]) -> Optional['Construct']:
        ...

    def find_member(self, name: str) -> Optional['Construct']:
        ...

    def find_members(self, name: str) -> List['Construct']:
        ...

    def find_method(self, name: str, argument_names: Sequence[str] = None) -> Optional['Construct']:
        ...

    def find_methods(self, name: str, argument_names: Sequence[str] = None) -> List['Construct']:
        ...

    def find_argument(self, name: str, search_members: bool = True) -> Optional['Construct']:
        ...

    def find_arguments(self, name: str, search_members: bool = True) -> List['Construct']:
        ...

    def matches_argument_names(self, argument_names: Sequence[str]) -> bool:
        ...

    @property
    def complexity_factor(self) -> int:
        ...

    def __repr__(self) -> str:
        ...

    def _define_markup(self, generator: 'MarkupGenerator') -> 'Production':
        ...

    def define_markup(self, generator: 'MarkupGenerator') -> None:
        ...

    def markup(self, marker: 'Marker') -> str:
        ...


class Marker(Protocol):
    """Protocol to provide markup."""

    def markup_construct(self, text: str, construct: Construct) -> Tuple[Optional[str], Optional[str]]:
        ...

    def markup_type(self, text: str, construct: Construct) -> Tuple[Optional[str], Optional[str]]:
        ...

    def markup_primitive_type(self, text: str, construct: Construct) -> Tuple[Optional[str], Optional[str]]:
        ...

    def markup_buffer_type(self, text: str, construct: Construct) -> Tuple[Optional[str], Optional[str]]:
        ...

    def markup_string_type(self, text: str, construct: Construct) -> Tuple[Optional[str], Optional[str]]:
        ...

    def markup_object_type(self, text: str, construct: Construct) -> Tuple[Optional[str], Optional[str]]:
        ...

    def markup_type_name(self, text: str, construct: Construct) -> Tuple[Optional[str], Optional[str]]:
        ...

    def markup_name(self, text: str, construct: Construct) -> Tuple[Optional[str], Optional[str]]:
        ...

    def markup_keyword(self, text: str, construct: Construct) -> Tuple[Optional[str], Optional[str]]:
        ...

    def markup_enum_value(self, text: str, construct: Construct) -> Tuple[Optional[str], Optional[str]]:
        ...

    def encode(self, text: str) -> str:
        ...


class MarkupGenerator(Protocol):
    """MarkupGenerator controls the markup process for a construct."""

    def __init__(self, construct: Construct) -> None:
        ...

    def add_generator(self, generator: 'MarkupGenerator') -> None:
        ...

    def add_type(self, type: Optional[Production]) -> None:
        ...

    def add_primitive_type(self, type: Optional[Production]) -> None:
        ...

    def add_string_type(self, type: Optional[Production]) -> None:
        ...

    def add_buffer_type(self, type: Optional[Production]) -> None:
        ...

    def add_object_type(self, type: Optional[Production]) -> None:
        ...

    def add_type_name(self, type_name: Optional[Union[str, Production]]) -> None:
        ...

    def add_name(self, name: Optional[Union[str, Production]]) -> None:
        ...

    def add_keyword(self, keyword: Optional[Union[str, Production]]) -> None:
        ...

    def add_enum_value(self, enum_value: Optional[Union[str, Production]]) -> None:
        ...

    def add_text(self, text: Optional[Union[str, Production]]) -> None:
        ...

    @property
    def text(self) -> str:
        ...

    def markup(self, marker: Marker, construct: Construct = None) -> str:
        ...
