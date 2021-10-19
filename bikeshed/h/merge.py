import itertools

from . import dom


def mergeTrees(tree1, tree2):
    """
    Attempts to merge two HTML trees
    of the same text content.

    Can fail, returning None.

    Does not merge the root of the two trees;
    instead it just returns an array of children,
    and you can decide where to put it.
    """

    for node in mergeStreams(
        digestTree(tree1),
        digestTree(tree2),
    ):
        print("*")
        if node["type"] == "end":
            print(f"</{node['item'].tag}>")
        elif node["type"] == "start":
            print(dom.serializeTag(node["item"]))
        else:
            print(node["item"])
    return []


def digestTree(root, nested=False):
    """
    Turns a tree into a stream of {text, element, end-of-element} items.
    The 'element' item is the element itself, empty, emitted at the start tag;
    when the end tag would appear, we just emit a generic eoe item.
    """

    length = textLength(root)
    children = dom.childNodes(root, clear=True)
    if nested:
        yield {
            "type": "start",
            "item": root,
            "length": length,
        }
    for node in children:
        if isinstance(node, str):
            yield {
                "type": "str",
                "item": node,
            }
        else:
            yield from digestTree(node, nested=True)
    if nested:
        yield {
            "type": "end",
            "item": root,
            "length": length,
        }


def textLength(el):
    length = 0
    for node in dom.childNodes(el):
        if isinstance(node, str):
            length += len(node)
        else:
            length += textLength(node)
    return length


def mergeStreams(s1, s2):
    """
    Merges two digested streams into a single one.
    Emits the same stream as digestTree(),
    except that it can throw if the trees turn out to be not mergable.
    """

    # "Pending" nodes that haven't been emitted yet, from each stream
    p1 = None
    p2 = None

    # Stack of open elements, to track that things merged validly.
    openStack = []

    def popStack(endNode):
        if openStack[-1]["item"] != endNode["item"]:
            raise ValueError("mergeStreams() can't merge these trees, due to overlapping elements.")
        openStack.pop()
        return True

    try:
        while True:
            # reload if possible
            if p1 is None:
                p1 = next(s1)
            if p2 is None:
                p2 = next(s2)

            # If either is an EOE, emit that
            # If one is element and one is text, emit the element
            # If both are text, emit the shortest common prefix
            # If both are elements, emit the one with the bigger length

            # Both EOE
            if p1["type"] == "end" and p2["type"] == "end":
                # The shorter would have its start emitted more recently.
                # If equal, p2 would have been emitted more recently,
                # because I bias toward emitting p1 start tags first when equal.
                if p1["length"] < p2["length"]:
                    popStack(p1)
                    yield p1
                    p1 = None
                elif p1["length"] > p2["length"]:
                    popStack(p2)
                    yield p2
                    p2 = None
                else:
                    popStack(p2)
                    yield p2
                    p2 = None

            # Either EOE
            if p1["type"] == "end":
                popStack(p1)
                yield p1
                p1 = None
                continue
            if p2["type"] == "end":
                popStack(p2)
                yield p2
                p2 = None
                continue

            # Both strings
            if p1["type"] == "str" and p2["type"] == "str":
                if len(p1["item"]) < len(p2["item"]):
                    yield p1
                    p2["item"] = p2["item"][len(p1) :]
                    p1 = None
                elif len(p1["item"]) > len(p2["item"]):
                    yield p2
                    p1["item"] = p1["item"][len(p2) :]
                    p2 = None
                else:
                    yield p1
                    p1 = None
                    p2 = None
                continue

            # Both elements
            if p1["type"] == "start" and p2["type"] == "start":
                if p1["length"] < p2["length"]:
                    yield p2
                    openStack.append(p2)
                    p2 = None
                elif p1["length"] > p2["length"]:
                    yield p1
                    openStack.append(p1)
                    p1 = None
                else:
                    # Equal length, bias toward emitting p1 on the outside
                    yield p1
                    openStack.append(p1)
                    p1 = None
                continue

            # One element, one text
            if p1["type"] == "start":
                yield p1
                openStack.append(p1)
                p1 = None
            else:
                yield p2
                openStack.append(p2)
                p2 = None
    except StopIteration:
        # Ran out of elements on at least one stream,
        # so just emit the remaining of the streams
        if p1 is not None:
            yield p1
        if p2 is not None:
            yield p2
        for node in itertools.chain(s1, s2):
            if isinstance(node, list):
                yield node[0]
            yield node
