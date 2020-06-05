# -*- coding: utf-8 -*-

# Full name of variouss groups
# Accessible throught the [LONGGROUP] macro.
shortToLongGroup = {
    "csswg": "CSS Working Group",
    "svgwg": "SVG Working Group",
    "psig": "Patent and Standards Interest Group"
}

# Where email announcements about publications from this group should be sent
# An array of one or more value is expected.
# All of them will be used (coma separated) in the "To" field via the [GROUPLISTS] macro
# and the first one will also be used for the "Reply To" field via the [GROUPREPLYTO] macro.
groupAnnounceLists = {
    "csswg": ["www-style@w3.org", "public-review-announce@w3.org"],
    "svgwg": ["www-svg@w3.org", "public-review-announce@w3.org"],
    "psig": ["member-psig@w3.org", "w3c-ac-forum@w3.org"]
}

# URL to the Group's mailing list archive, if any.
# Accessible via the [GROUPMLARCHIVE] macro.
groupMLArchive = {
    "csswg": "http://lists.w3.org/Archives/Public/www-style/",
    "svgwg": "http://lists.w3.org/Archives/Public/www-svg/",
    "psig": "https://lists.w3.org/Archives/Member/member-psig/"
}
