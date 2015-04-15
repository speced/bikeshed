# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
# Display constants
VERTICAL_SEPARATION = 8
ARC_RADIUS = 10
DIAGRAM_CLASS = 'railroad-diagram'
TRANSLATE_HALF_PIXEL = True
INTERNAL_ALIGNMENT = 'center'
DEBUG = True

# Assume a monospace font with each char .5em wide, and the em is 16px
CHARACTER_ADVANCE = 8

def e(text):
    return str(text).replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;')

def determineGaps(outer, inner):
    diff = outer - inner
    if INTERNAL_ALIGNMENT == 'left':
        return 0, diff
    elif INTERNAL_ALIGNMENT == 'right':
        return diff, 0
    else:
        return diff/2, diff/2



class DiagramItem(object):
    def __init__(self, name, attrs=None, text=None):
        self.name = name
        self.attrs = attrs or {}
        self.children = [text] if text else []
        self.needsSpace = False
        self.raw = None
        self.yAdvance = 0

    def format(self, x, y, width):
        raise NotImplementedError  # Virtual

    def addTo(self, parent):
        parent.children.append(self)
        return self

    def writeSvg(self, write, raw=None):
        if raw is None and self.raw is not None:
            raw = self.raw
        write('<{0}'.format(self.name))
        for name, value in sorted(self.attrs.items()):
            write(' {0}="{1}"'.format(name, e(value)))
        write('>\n')
        for child in self.children:
            if isinstance(child, DiagramItem):
                child.writeSvg(write, raw)
            elif raw:
                write(child)
            else:
                write(e(child))
        write('</{0}>'.format(self.name))


class Path(DiagramItem):
    def __init__(self, x, y):
        DiagramItem.__init__(self, 'path', {'d': 'M%s %s' % (x, y)})

    def m(self, x, y):
        self.attrs['d'] += 'm{0} {1}'.format(x,y)
        return self

    def h(self, val):
        self.attrs['d'] += 'h{0}'.format(val)
        return self

    right = h

    def left(self, val):
        return self.h(-val)

    def v(self, val):
        self.attrs['d'] += 'v{0}'.format(val)
        return self

    down = v

    def up(self, val):
        return self.v(-val)

    def arc(self, sweep):
        x = ARC_RADIUS
        y = ARC_RADIUS
        if sweep[0] == 'e' or sweep[1] == 'w':
            x *= -1
        if sweep[0] == 's' or sweep[1] == 'n':
            y *= -1
        cw = 1 if sweep == 'ne' or sweep == 'es' or sweep == 'sw' or sweep == 'wn' else 0
        self.attrs['d'] += 'a{0} {0} 0 0 {1} {2} {3}'.format(ARC_RADIUS, cw, x, y)
        return self


    def format(self):
        self.attrs['d'] += 'h.5'
        return self


def wrapString(value):
    return value if isinstance(value, DiagramItem) else Terminal(value)


class Diagram(DiagramItem):
    def __init__(self, *items):
        DiagramItem.__init__(self, 'svg', {'class': DIAGRAM_CLASS})
        self.items = [Start()] + [wrapString(item) for item in items] + [End()]
        self.width = 1 + sum(item.width + (20 if item.needsSpace else 0)
                             for item in self.items)
        self.up = 0
        self.down = 0
        for item in self.items:
            self.up = max(self.up, item.up - self.yAdvance)
            self.down = max(self.down, item.down + self.yAdvance)
            self.yAdvance += item.yAdvance
        self.formatted = False

    def format(self, paddingTop=20, paddingRight=None, paddingBottom=None, paddingLeft=None):
        if paddingRight is None:
            paddingRight = paddingTop
        if paddingBottom is None:
            paddingBottom = paddingTop
        if paddingLeft is None:
            paddingLeft = paddingRight
        x = paddingLeft
        y = paddingTop + self.up
        g = DiagramItem('g')
        if TRANSLATE_HALF_PIXEL:
            g.attrs['transform'] = 'translate(.5 .5)'
        for item in self.items:
            if item.needsSpace:
                Path(x, y).h(10).addTo(g)
                x += 10
            item.format(x, y, item.width)
            x += item.width
            y += item.yAdvance
            if item.needsSpace:
                Path(x, y).h(10).addTo(g)
                x += 10
            item.addTo(g)
        self.attrs['width'] = self.width + paddingLeft + paddingRight
        self.attrs['height'] = self.up + self.down + paddingTop + paddingBottom
        self.attrs['viewBox'] = "0 0 {width} {height}".format(**self.attrs)
        g.addTo(self)
        self.formatted = True
        return self


    def writeSvg(self, write):
        if not self.formatted:
            self.format()
        return DiagramItem.writeSvg(self, write)


class Sequence(DiagramItem):
    def __init__(self, *items):
        DiagramItem.__init__(self, 'g')
        self.items = [wrapString(item) for item in items]
        self.width = sum(item.width + (20 if item.needsSpace else 0)
                         for item in self.items)
        self.up = 0
        self.down = 0
        for item in self.items:
            self.up = max(self.up, item.up - self.yAdvance)
            self.down = max(self.down, item.down + self.yAdvance)
            self.yAdvance += item.yAdvance
        if DEBUG:
            self.attrs['data-updown'] = "{0} {1}".format(self.up, self.down)
            self.attrs['data-type'] = "sequence"

    def format(self, x, y, width):
        leftGap, rightGap = determineGaps(width, self.width)
        Path(x, y).h(leftGap).addTo(self)
        Path(x+leftGap+self.width, y).h(rightGap).addTo(self)
        x += leftGap
        for item in self.items:
            if item.needsSpace:
                Path(x, y).h(10).addTo(self)
                x += 10
            item.format(x, y, item.width)
            x += item.width
            y += item.yAdvance
            if item.needsSpace:
                Path(x, y).h(10).addTo(self)
                x += 10
            item.addTo(self)
        return self


class Stack(DiagramItem):
    def __init__(self, *items):
        DiagramItem.__init__(self, 'g')
        self.items = [wrapString(item) for item in items]
        self.width = (ARC_RADIUS * 4) + max(item.width for item in self.items)
        item = self.items[0]
        self.up = item.up
        self.down = item.down
        prevItem = item
        for item in self.items[1:]:
            self.down += (ARC_RADIUS * 4) + item.up + item.down
            self.yAdvance += (ARC_RADIUS * 4) + prevItem.down + item.up
            prevItem = item
        self.yAdvance += prevItem.yAdvance

    def format(self, x, y, width):
        item = self.items[0]
        space = 0
        if (item.width < width):
            space = (width - item.width) / 2
            Path(x, y).h(space).addTo(self)
        item.format(x + space, y, item.width)
        item.addTo(self)
        prevItem = item
        for item in self.items[1:]:
            Path(x + space + prevItem.width, y + prevItem.yAdvance).arc('ne') \
                .v(prevItem.down - prevItem.yAdvance).arc('es') \
                .left((prevItem.width / 2) + (item.width / 2)).arc('nw').v(item.up).arc('ws').addTo(self)
            space = (width - item.width) / 2
            y += (ARC_RADIUS * 4) + prevItem.down + item.up
            item.format(x + space, y, item.width)
            item.addTo(self)
            prevItem = item
        if (0 < space):
            Path(x + prevItem.width + space, y + prevItem.yAdvance).h(space).addTo(self)


class Choice(DiagramItem):
    def __init__(self, default, *items):
        DiagramItem.__init__(self, 'g')
        assert default < len(items)
        self.default = default
        self.items = [wrapString(item) for item in items]
        self.width = ARC_RADIUS * 4 + max(item.width for item in self.items)
        self.up = 0
        self.down = 0
        self.yAdvance = self.items[self.default].yAdvance
        for i, item in enumerate(self.items):
            if i < default:
                self.up += max(ARC_RADIUS, item.up + item.down + VERTICAL_SEPARATION)
            elif i == default:
                self.up += max(ARC_RADIUS, item.up)
                self.down += max(ARC_RADIUS, item.down)
            else:
                assert i > default
                self.down += max(ARC_RADIUS, VERTICAL_SEPARATION + item.up + item.down)
        if DEBUG:
            self.attrs['data-updown'] = "{0} {1}".format(self.up, self.down)
            self.attrs['data-type'] = "choice"

    def format(self, x, y, width):
        leftGap, rightGap = determineGaps(width, self.width)

        # Hook up the two sides if self is narrower than its stated width.
        Path(x, y).h(leftGap).addTo(self)
        Path(x + leftGap + self.width, y).h(rightGap).addTo(self)
        x += leftGap

        last = len(self.items) - 1
        innerWidth = self.width - (ARC_RADIUS * 4)

        # Do the elements that curve above
        above = self.items[:self.default]
        if above:
            distanceFromY = max(
                ARC_RADIUS * 2,
                self.items[self.default].up
                    + VERTICAL_SEPARATION
                    + self.items[self.default - 1].down)
        for i, item in list(enumerate(above))[::-1]:
            Path(x, y).arc('se').up(distanceFromY - (ARC_RADIUS * 2)).arc('wn').addTo(self)
            item.format(x + (ARC_RADIUS * 2), y - distanceFromY, innerWidth)
            Path(x + (ARC_RADIUS * 2) + innerWidth, y + item.yAdvance - distanceFromY).arc('ne') \
                .down(distanceFromY + self.yAdvance - item.yAdvance - (ARC_RADIUS * 2)).arc('ws').addTo(self)
            item.addTo(self)
            distanceFromY += max(
                ARC_RADIUS,
                item.up
                    + VERTICAL_SEPARATION
                    + (self.items[i - 1].down if i > 0 else 0))

        # Do the straight-line path.
        Path(x, y).right(ARC_RADIUS * 2).addTo(self)
        self.items[self.default].format(x + (ARC_RADIUS * 2), y, innerWidth)
        Path(x + (ARC_RADIUS * 2) + innerWidth, y + self.yAdvance).right(ARC_RADIUS * 2).addTo(self)
        self.items[self.default].addTo(self)

        # Do the elements that curve below
        below = self.items[self.default + 1:]
        for i, item in enumerate(below):
            if i == 0:
                distanceFromY = max(
                    ARC_RADIUS * 2,
                    self.items[self.default].down
                        + VERTICAL_SEPARATION
                        + item.up)
            Path(x, y).arc('ne').down(distanceFromY - (ARC_RADIUS * 2)).arc('ws').addTo(self)
            item.format(x + (ARC_RADIUS * 2), y + distanceFromY, innerWidth)
            Path(x + (ARC_RADIUS * 2) + innerWidth, y + distanceFromY + item.yAdvance).arc('se') \
                .up((distanceFromY + item.yAdvance) - self.yAdvance - (ARC_RADIUS * 2)).arc('wn').addTo(self)
            item.addTo(self)
            distanceFromY += max(
                ARC_RADIUS,
                item.down
                    + VERTICAL_SEPARATION
                    + (below[i + 1].up if i+1 < len(below) else 0))
        return self


def Optional(item, skip=False):
    return Choice(0 if skip else 1, Skip(), item)


class OneOrMore(DiagramItem):
    def __init__(self, item, repeat = None):
        DiagramItem.__init__(self, 'g')
        repeat = repeat or Skip()
        self.item = wrapString(item)
        self.rep = wrapString(repeat)
        self.width = max(self.item.width, self.rep.width) + (ARC_RADIUS * 2)
        self.up = self.item.up
        self.down = max(
            ARC_RADIUS * 2,
            self.item.down + VERTICAL_SEPARATION + self.rep.up + self.rep.down)
        self.yAdvance = self.item.yAdvance
        self.needsSpace = True
        if DEBUG:
            self.attrs['data-updown'] = "{0} {1}".format(self.up, self.down)
            self.attrs['data-type'] = "oneormore"

    def format(self, x, y, width):
        leftGap, rightGap = determineGaps(width, self.width)

        # Hook up the two sides if self is narrower than its stated width.
        Path(x, y).h(leftGap).addTo(self)
        Path(x + leftGap + self.width, y).h(rightGap).addTo(self)
        x += leftGap

        # Draw item
        Path(x, y).right(ARC_RADIUS).addTo(self)
        self.item.format(x + ARC_RADIUS, y, self.width - (ARC_RADIUS * 2))
        Path(x + self.width - ARC_RADIUS, y + self.yAdvance).right(ARC_RADIUS).addTo(self)

        # Draw repeat arc
        distanceFromY = max(ARC_RADIUS * 2, self.item.down + VERTICAL_SEPARATION + self.rep.up)
        Path(x + ARC_RADIUS, y).arc('nw').down(distanceFromY - (ARC_RADIUS * 2)) \
            .arc('ws').addTo(self)
        self.rep.format(x + ARC_RADIUS, y + distanceFromY, self.width - (ARC_RADIUS * 2))
        Path(x + self.width - ARC_RADIUS, y + distanceFromY).arc('se') \
            .up(distanceFromY - self.yAdvance - (ARC_RADIUS * 2)).arc('en').addTo(self)
        self.item.addTo(self)
        self.rep.addTo(self)

        return self


def ZeroOrMore(item, repeat=None):
    result = Optional(OneOrMore(item, repeat))
    return result


class Start(DiagramItem):
    def __init__(self):
        DiagramItem.__init__(self, 'path')
        self.width = 20
        self.up = 10
        self.down = 10
        if DEBUG:
            self.attrs['data-updown'] = "{0} {1}".format(self.up, self.down)
            self.attrs['data-type'] = "start"

    def format(self, x, y, _width):
        self.attrs['d'] = 'M {0} {1} v 20 m 10 -20 v 20 m -10 -10 h 20.5'.format(x, y - 10)
        return self


class End(DiagramItem):
    def __init__(self):
        DiagramItem.__init__(self, 'path')
        self.width = 20
        self.up = 10
        self.down = 10
        if DEBUG:
            self.attrs['data-updown'] = "{0} {1}".format(self.up, self.down)
            self.attrs['data-type'] = "end"

    def format(self, x, y, _width):
        self.attrs['d'] = 'M {0} {1} h 20 m -10 -10 v 20 m 10 -20 v 20'.format(x, y)
        return self


class TextDiagramItem(DiagramItem):
    def __init__(self, prelude):
        DiagramItem.__init__(self, 'g')
        self.raw = "raw" in prelude.split()


class Terminal(TextDiagramItem):
    def __init__(self, text, prelude=""):
        TextDiagramItem.__init__(self, prelude)
        self.text = text
        self.prelude = prelude
        self.width = len(text) * CHARACTER_ADVANCE + 20
        self.up = 11
        self.down = 11
        self.needsSpace = True
        if DEBUG:
            self.attrs['data-updown'] = "{0} {1}".format(self.up, self.down)
            self.attrs['data-type'] = "terminal"

    def format(self, x, y, width):
        leftGap, rightGap = determineGaps(width, self.width)

        # Hook up the two sides if self is narrower than its stated width.
        Path(x, y).h(leftGap).addTo(self)
        Path(x + leftGap + self.width, y).h(rightGap).addTo(self)

        DiagramItem('rect', {'x': x + leftGap, 'y': y - 11, 'width': self.width,
                             'height': self.up + self.down, 'rx': 10, 'ry': 10}).addTo(self)
        DiagramItem('text', {'x': x + width / 2, 'y': y + 4}, self.text).addTo(self)
        return self


class NonTerminal(TextDiagramItem):
    def __init__(self, text, prelude=""):
        TextDiagramItem.__init__(self, prelude)
        self.text = text
        self.prelude = prelude
        self.width = len(text) * CHARACTER_ADVANCE + 20
        self.up = 11
        self.down = 11
        self.needsSpace = True
        if DEBUG:
            self.attrs['data-updown'] = "{0} {1}".format(self.up, self.down)
            self.attrs['data-type'] = "non-terminal"

    def format(self, x, y, width):
        leftGap, rightGap = determineGaps(width, self.width)

        # Hook up the two sides if self is narrower than its stated width.
        Path(x, y).h(leftGap).addTo(self)
        Path(x + leftGap + self.width, y).h(rightGap).addTo(self)

        DiagramItem('rect', {'x': x + leftGap, 'y': y - 11, 'width': self.width,
                             'height': self.up + self.down}).addTo(self)
        DiagramItem('text', {'x': x + width / 2, 'y': y + 4}, self.text).addTo(self)
        return self


class Comment(TextDiagramItem):
    def __init__(self, text, prelude=""):
        TextDiagramItem.__init__(self, prelude)
        self.text = text
        self.prelude = prelude
        self.width = len(text) * 7 + 10
        self.up = 11
        self.down = 11
        self.needsSpace = True
        if DEBUG:
            self.attrs['data-updown'] = "{0} {1}".format(self.up, self.down)
            self.attrs['data-type'] = "comment"

    def format(self, x, y, width):
        leftGap, rightGap = determineGaps(width, self.width)

        # Hook up the two sides if self is narrower than its stated width.
        Path(x, y).h(leftGap).addTo(self)
        Path(x + leftGap + self.width, y).h(rightGap).addTo(self)

        DiagramItem('text', {'x': x + width / 2, 'y': y + 5, 'class': 'comment'}, self.text).addTo(self)
        return self


class Skip(TextDiagramItem):
    def __init__(self, prelude=""):
        TextDiagramItem.__init__(self, prelude)
        self.prelude = prelude
        self.width = 0
        self.up = 0
        self.down = 0
        if DEBUG:
            self.attrs['data-updown'] = "{0} {1}".format(self.up, self.down)
            self.attrs['data-type'] = "skip"

    def format(self, x, y, width):
        Path(x, y).right(width).addTo(self)
        return self


if __name__ == '__main__':
    def add(name, diagram):
        sys.stdout.write('<h1>{0}</h1>\n'.format(e(name)))
        diagram.writeSvg(sys.stdout.write)
        sys.stdout.write('\n')

    import sys
    sys.stdout.write("<!doctype html><title>Test</title><style>svg.railroad-diagram{background-color:hsl(30,20%,95%);}svg.railroad-diagram path{stroke-width:3;stroke:black;fill:rgba(0,0,0,0);}svg.railroad-diagram text{font:bold 14px monospace;text-anchor:middle;}svg.railroad-diagram text.label{text-anchor:start;}svg.railroad-diagram text.comment{font:italic 12px monospace;}svg.railroad-diagram rect{stroke-width:3;stroke:black;fill:hsl(120,100%,90%);}</style>")
    exec(open('css-example.py-js').read())
