from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class TestSuite:
    description: str
    spec: str
    status: str
    title: str
    url: str
    vshortname: str


# {
#    "description": "Nightly build of the Compositing and Blending 1 CR Test Suite.",
#    "spec": "compositing-1",
#    "status": "dev",
#    "title": "Compositing and Blending Level 1 CR Test Suite",
#    "url": "http://test.csswg.org/suites/compositing-1_dev/nightly-unstable/",
#    "vshortname": "compositing-1_dev"
# }
