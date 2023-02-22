from __future__ import annotations

from . import h, t

trackingVectorId = "b732b3fe"  # hashlib.md5("tracking-vector").hexdigest()[0:8], to minimize chance of collision


def addTrackingVector(doc: t.SpecT) -> None:
    if doc.md.trackingVectorClass is None:
        return

    els = h.findAll("[tracking-vector]", doc)

    if len(els) == 0:
        return

    if doc.md.trackingVectorImage is None:
        # Generate an SVG and <use> it in all the individual spots
        h.appendChild(
            doc.body,
            h.E.svg(
                {"viewBox": "0 0 46 64", "style": "display:none"},
                h.E.defs(
                    {},
                    h.E.path(
                        {
                            "id": trackingVectorId,
                            "stroke": "black",
                            "stroke-linecap": "round",
                            "stroke-linejoin": "round",
                            "stroke-dasharray": "3,2,35,2,20,2",
                            "fill": "none",
                            "d": "M2 23Q17 -16 40 12M1 35Q17 -20 43 20M2 40Q18 -19 44 25M3 43Q19 -16 45 29M5 46Q20 -12 45 32M5 49Q11 40 15 27T27 16T45 37M5 49Q15 38 19 25T34 27T44 41M6 52Q17 40 21 28T32 29T43 44M6 52Q21 42 23 31T30 32T42 47M7 54Q23 47 24 36T28 34T41 50M8 56Q26 50 26 35Q28 48 40 53M10 58Q24 54 27 45Q30 52 38 55M27 50Q28 53 36 57M25 52Q28 56 31 57M22 55L26 57M10 58L37 57M13 60L32 60M16 62L28 63",  # pylint: disable=line-too-long
                        }
                    ),
                ),
            ),
        )

    for el in els:
        h.prependChild(el, " ")  # The space is to separate from the following text.
        h.prependChild(
            el,
            h.E.a(
                {
                    "class": doc.md.trackingVectorClass,
                    "href": "https://infra.spec.whatwg.org/#tracking-vector",
                },
                trackingVectorImage(
                    doc.md.trackingVectorImage,
                    doc.md.trackingVectorImageWidth,
                    doc.md.trackingVectorImageHeight,
                    doc.md.trackingVectorAltText,
                    doc.md.trackingVectorTitle,
                ),
            ),
        )
        h.removeAttr(el, "tracking-vector")


def trackingVectorImage(
    imageURL: str | None, imageWidth: str, imageHeight: str, altText: str, title: str
) -> t.ElementT:
    if imageURL is None:
        return h.E.svg(
            {"width": "46", "height": "64", "role": "img", "aria-label": altText},
            h.E.title({}, title),
            h.E.use({"href": "#" + trackingVectorId}),
        )
    return h.E.img(
        {
            "title": title,
            "alt": altText,
            "src": imageURL,
            "width": imageWidth,
            "height": imageHeight,
        }
    )
