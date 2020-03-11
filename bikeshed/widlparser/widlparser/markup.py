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
"""Process markup output."""

from typing import List, Optional, Tuple, Union, cast

from . import protocols


class MarkupGenerator(object):
    """MarkupGenerator controls the markup process for a construct."""

    construct: Optional[protocols.Construct]
    children: List[protocols.MarkupGenerator]

    def __init__(self, construct: protocols.Construct = None) -> None:
        self.construct = construct
        self.children = []

    def add_generator(self, generator: protocols.MarkupGenerator) -> None:
        """Add a generator for child constructs."""
        self.children.append(generator)

    def add_type(self, type: Optional[protocols.Production]) -> None:
        """Add a type."""
        if (type):
            self.add_text(type.leading_space)
            self.children.append(MarkupType(self.construct, type))
            self.add_text(type.semicolon)
            self.add_text(type.trailing_space)

    def add_primitive_type(self, type: Optional[protocols.Production]) -> None:
        """Add a primitive type."""
        if (type):
            self.children.append(MarkupPrimitiveType(self.construct, type))

    def add_string_type(self, type: Optional[protocols.Production]) -> None:
        """Add a string type."""
        if (type):
            self.children.append(MarkupStringType(self.construct, type))

    def add_buffer_type(self, type: Optional[protocols.Production]) -> None:
        """Add a buffer type."""
        if (type):
            self.children.append(MarkupBufferType(self.construct, type))

    def add_object_type(self, type: Optional[protocols.Production]) -> None:
        """Add an object type."""
        if (type):
            self.children.append(MarkupObjectType(self.construct, type))

    def add_type_name(self, type_name: Optional[Union[str, protocols.Production]]) -> None:
        """Add a type name."""
        if (type_name):
            self.children.append(MarkupTypeName(self.construct, str(type_name)))

    def add_name(self, name: Optional[Union[str, protocols.Production]]) -> None:
        """Add a name."""
        if (name):
            self.children.append(MarkupName(self.construct, str(name)))

    def add_keyword(self, keyword: Optional[Union[str, protocols.Production]]) -> None:
        """Add a keyword."""
        if (keyword):
            self.children.append(MarkupKeyword(self.construct, str(keyword)))

    def add_enum_value(self, enum_value: Optional[Union[str, protocols.Production]]) -> None:
        """Add an enum value."""
        if (enum_value):
            self.children.append(MarkupEnumValue(self.construct, str(enum_value)))

    def add_text(self, text: Optional[Union[str, protocols.Production]]) -> None:
        """Add plain text."""
        if (text):
            if ((0 < len(self.children)) and (type(self.children[-1]) is MarkupText)):
                cast(MarkupText, self.children[-1])._append_text(str(text))
            else:
                self.children.append(MarkupText(self.construct, str(text)))

    @property
    def text(self) -> str:
        """Get text of all children."""
        return ''.join([child.text for child in self.children])

    def _append_text(self, text: str) -> None:
        raise NotImplementedError

    def _markup(self, marker: protocols.Marker) -> Tuple[Optional[str], Optional[str]]:
        if (self.construct and hasattr(marker, 'markup_construct')):
            return marker.markup_construct(self.text, self.construct)
        return (None, None)

    def markup(self, marker: protocols.Marker, construct: protocols.Construct = None) -> str:
        """Generate markup, calling marker."""
        head, tail = self._markup(marker)
        output = str(head) if (head) else ''
        output += ''.join([child.markup(marker, self.construct) for child in self.children])
        return output + (str(tail) if (tail) else '')


class MarkupType(MarkupGenerator):
    """MarkupGenerator subclass to markup types."""

    def __init__(self, construct: Optional[protocols.Construct], type: protocols.Production) -> None:
        MarkupGenerator.__init__(self, construct)
        type._define_markup(self)

    def _markup(self, marker: protocols.Marker) -> Tuple[Optional[str], Optional[str]]:
        if (self.construct and hasattr(marker, 'markup_type')):
            return marker.markup_type(self.text, self.construct)
        return (None, None)


class MarkupPrimitiveType(MarkupGenerator):
    """MarkupGenerator subclass to markup primitive types."""

    def __init__(self, construct: Optional[protocols.Construct], type: protocols.Production) -> None:
        MarkupGenerator.__init__(self, construct)
        type._define_markup(self)

    def _markup(self, marker: protocols.Marker) -> Tuple[Optional[str], Optional[str]]:
        if (self.construct and hasattr(marker, 'markup_primitive_type')):
            return marker.markup_primitive_type(self.text, self.construct)
        return (None, None)


class MarkupBufferType(MarkupGenerator):
    """MarkupGenerator subclass to markup buffer types."""

    def __init__(self, construct: Optional[protocols.Construct], type: protocols.Production) -> None:
        MarkupGenerator.__init__(self, construct)
        type._define_markup(self)

    def _markup(self, marker: protocols.Marker) -> Tuple[Optional[str], Optional[str]]:
        if (self.construct and hasattr(marker, 'markup_buffer_type')):
            return marker.markup_buffer_type(self.text, self.construct)
        return (None, None)


class MarkupStringType(MarkupGenerator):
    """MarkupGenerator subclass to markup string types."""

    def __init__(self, construct: Optional[protocols.Construct], type: protocols.Production) -> None:
        MarkupGenerator.__init__(self, construct)
        type._define_markup(self)

    def _markup(self, marker: protocols.Marker) -> Tuple[Optional[str], Optional[str]]:
        if (self.construct and hasattr(marker, 'markup_string_type')):
            return marker.markup_string_type(self.text, self.construct)
        return (None, None)


class MarkupObjectType(MarkupGenerator):
    """MarkupGenerator subclass to markup object types."""

    def __init__(self, construct: Optional[protocols.Construct], type: protocols.Production) -> None:
        MarkupGenerator.__init__(self, construct)
        type._define_markup(self)

    def _markup(self, marker: protocols.Marker) -> Tuple[Optional[str], Optional[str]]:
        if (self.construct and hasattr(marker, 'markup_object_type')):
            return marker.markup_object_type(self.text, self.construct)
        return (None, None)


class MarkupText(MarkupGenerator):
    """MarkupGenerator subclass to markup text."""

    _text: str

    def __init__(self, construct: Optional[protocols.Construct], text: str) -> None:
        MarkupGenerator.__init__(self, construct)
        self._text = text

    @property
    def text(self) -> str:
        return self._text

    def _append_text(self, text: str) -> None:
        self._text += text

    def markup(self, marker: protocols.Marker, construct: protocols.Construct = None) -> str:
        """Use marker to encode text."""
        return str(marker.encode(self.text)) if (hasattr(marker, 'encode')) else self.text


class MarkupTypeName(MarkupText):
    """MarkupGenerator subclass to markup type names."""

    def __init__(self, construct: Optional[protocols.Construct], type: str) -> None:
        MarkupText.__init__(self, construct, type)

    def markup(self, marker: protocols.Marker, construct: protocols.Construct = None) -> str:
        """Generate marked up type name."""
        head, tail = marker.markup_type_name(self.text, cast(protocols.Construct, construct)) if (hasattr(marker, 'markup_type_name')) else (None, None)
        output = str(head) if (head) else ''
        output += MarkupText.markup(self, marker, construct)
        return output + (str(tail) if (tail) else '')


class MarkupName(MarkupText):
    """MarkupGenerator subclass to markup names."""

    def __init__(self, construct: Optional[protocols.Construct], name: str) -> None:
        MarkupText.__init__(self, construct, name)

    def markup(self, marker: protocols.Marker, construct: protocols.Construct = None) -> str:
        """Generate marked up name."""
        head, tail = marker.markup_name(self.text, cast(protocols.Construct, construct)) if (hasattr(marker, 'markup_name')) else (None, None)
        output = str(head) if (head) else ''
        output += MarkupText.markup(self, marker, construct)
        return output + (str(tail) if (tail) else '')


class MarkupKeyword(MarkupText):
    """MarkupGenerator subclass to markup keywords."""

    def __init__(self, construct: Optional[protocols.Construct], keyword: str) -> None:
        MarkupText.__init__(self, construct, keyword)

    def markup(self, marker: protocols.Marker, construct: protocols.Construct = None) -> str:
        """Generate marked up keyword."""
        head, tail = marker.markup_keyword(self.text, cast(protocols.Construct, construct)) if (hasattr(marker, 'markup_keyword')) else (None, None)
        output = str(head) if (head) else ''
        output += MarkupText.markup(self, marker, construct)
        return output + (str(tail) if (tail) else '')


class MarkupEnumValue(MarkupText):
    """MarkupGenerator subclass to markup enum values."""

    def __init__(self, construct: Optional[protocols.Construct], keyword: str) -> None:
        MarkupText.__init__(self, construct, str(keyword))

    def markup(self, marker: protocols.Marker, construct: protocols.Construct = None) -> str:
        """Generate marked up enum value."""
        head, tail = marker.markup_enum_value(self.text, cast(protocols.Construct, construct)) if (hasattr(marker, 'markup_enum_value')) else (None, None)
        output = str(head) if (head) else ''
        output += MarkupText.markup(self, marker, construct)
        return output + (str(tail) if (tail) else '')
