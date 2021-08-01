import collections
import warnings
import re


class WikitextError(ValueError):
    pass


class WikitextWarning(Warning):
    pass


def _re_escape(x):
    return (
        re.escape(x)
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _safefind(haystack, needle, start = 0, end = False):
    f = haystack.find(needle, start)
    return len(haystack) if f < 0 else f + len(needle) if end else f


# a function that returns the first match of any needle in a haystack
def _minfind(haystack, needles, index=0):
    t = "|".join(_re_escape(n) for n in needles)
    match = re.compile(t).search(haystack, index)
    if match is None:
        return None
    return (match.start(), match.group(0))


MAXIMUM_HEADING_LEVEL = 6
_DumpPage = collections.namedtuple("DumpPage", ["title", "text"])
_Heading = collections.namedtuple("Heading", ["level", "text"])
_Section = collections.namedtuple("Section", ["heading", "text"])
_InternalLink = collections.namedtuple("InternalLink", ["target", "text"])
_Template = collections.namedtuple("Template", ["src", "name", "args"])


class DumpPage(_DumpPage):
    """
    A page that has been obtained from a MediaWiki XML dump.

    Attributes
    ----------
    title : str
        The page title. Includes the namespace with a separating colon (:).
    text : str
        The page text, in raw wikitext format.
    """

    pass


class Heading(_Heading):
    """
    A wikitext heading.

    Attributes
    ----------
    level : int
        The level of the heading, at least 1 and at most 6. The higher the
        level, the "inner" the heading is; that is, a level 3 heading is a
        subheading for a level 2 heading.

    text : str or None
        The text in the heading, or None if no text.
    """

    pass


class Section(_Section):
    """
    A wikitext section, consisting of a heading and the text under it.

    Attributes
    ----------
    heading : Heading
        The heading of the section. May have text = None.

    text : str
        The text in the section.
    """

    pass


class InternalLink(_InternalLink):
    """
    A wikitext internal link.

    Attributes
    ----------
    target : str
        The target of the link. Not parsed in any way, and thus may include
        references to other namespaces or interwiki links. Note that this may
        even include images or other media.

    text : str
        The text or markup that defines the appearance of this link.
    """

    pass


class Template(_Template):
    """
    A wikitext template invocation.

    Attributes
    ----------
    src : str
        The original wikitext of the template invocation.

    name : str
        The name of the template being invoked.

    args : OrderedDict
        The arguments the template is being invoked with.
    """

    pass


def _remove_extra(text):
    result = ""
    lookstart = 0
    lentext = len(text)
    while lookstart < lentext:
        fd = _minfind(text, ("<!--", "<nowiki>"), lookstart)
        if fd:
            result += text[lookstart : fd[0]]
            lookstart = fd[0] + len(fd[1])
            if fd[1] == "<!--":
                lookstart = _safefind(text, "-->", lookstart, True)
            elif fd[1] == "<nowiki>":
                lookstart = _safefind(text, "</nowiki>", lookstart, True)
        else:
            break
    result += text[lookstart :]
    return result


def iterate_pages_in_xml(xml):
    """
    Parses a MediaWiki XML dump and gives out all of the pages that can be
    found. The dump should be "Articles, templates, media/file descriptions,
    and primary meta-pages", which has a file name of the format
    "SITE-YYYYMMDD-pages-articles.xml".

    Parameters
    ----------
    xml : str
        The file name or complete path to the XML dump.

    Yields
    ------
    DumpPage
        The generated items are tuples of the type DumpPage with the page
        title and text.

    """
    import xml.etree.ElementTree as etree

    group_nesting = 0
    last_title = ""
    in_page = False

    def strip_ns(tag):
        if "{" and "}" in tag:
            return tag[tag.find("}") + 1 :]
        return tag

    for event, elem in etree.iterparse(xml, events=("start", "end")):
        if event == "start":
            if strip_ns(elem.tag) == "page":
                in_page = True
        elif event == "end":
            if in_page:
                if strip_ns(elem.tag) == "title":
                    last_title = elem.text
                if strip_ns(elem.tag) == "text":
                    yield DumpPage(last_title, elem.text or "")
            if strip_ns(elem.tag) == "page":
                in_page = False
            elem.clear()


def parse_heading(text):
    """
    Parses a heading from a single line of wikitext. Headings start and
    end with one or more equals signs (=).

    Parameters
    ----------
    text : str
        The text to parse the heading from. Must be a single line, as headings
        cannot span multiple lines.

    Returns
    -------
    Heading or None
        A parsed heading, or None if one cannot be found or parsed from a text.
    """
    if "\n" in text:
        return None
    eq = 0
    while (
        eq < min(MAXIMUM_HEADING_LEVEL + 1, len(text) // 2)
        and text[eq] == "="
        and text[-eq - 1] == "="
    ):
        eq += 1
    if eq > 0:
        eq = min(eq, 6)
        return Heading(eq, text[eq:-eq].strip())
    return None


def contains_heading(text, level, heading):
    """Checks whether the given wikitext contains a heading of the given level.

    Parameters
    ----------
    text : str
        The text to find the heading from.
    level : int
        The level of the heading to look for.
    heading : str
        The text of the heading to look for.

    Returns
    -------
    bool
        Whether the given wikitext contains the specified heading.
    """
    if level < 1 or level > MAXIMUM_HEADING_LEVEL:
        raise ValueError("invalid value for heading level")
    text = _remove_extra(text)
    matching = "=" * level
    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith(matching) and line.endswith(matching):
            line = line[level:-level].strip()
            if line == heading:
                return True
    return False


def contains_l2(text, l2):
    """Checks whether the given wikitext contains a specific level 2 heading.

    Parameters
    ----------
    text : str
        The text to find the heading from.
    l2 : str
        The text of the level 2 heading to look for.

    Returns
    -------
    bool
        Whether the given wikitext contains the specified level 2 heading.
    """
    return contains_heading(text, 2, l2)


def contains_l3(text, l3):
    """Checks whether the given wikitext contains a specific level 3 heading.

    Parameters
    ----------
    text : str
        The text to find the heading from.
    l3 : str
        The text of the level 3 heading to look for.

    Returns
    -------
    bool
        Whether the given wikitext contains the specified level 3 heading.
    """
    return contains_heading(text, 3, l3)


def contains_l4(text, l4):
    """Checks whether the given wikitext contains a specific level 4 heading.

    Parameters
    ----------
    text : str
        The text to find the heading from.
    l4 : str
        The text of the level 4 heading to look for.

    Returns
    -------
    bool
        Whether the given wikitext contains the specified level 4 heading.
    """
    return contains_heading(text, 4, l4)


def contains_l5(text, l5):
    """Checks whether the given wikitext contains a specific level 5 heading.

    Parameters
    ----------
    text : str
        The text to find the heading from.
    l5 : str
        The text of the level 5 heading to look for.

    Returns
    -------
    bool
        Whether the given wikitext contains the specified level 5 heading.
    """
    return contains_heading(text, 5, l5)


def contains_l3_in_l2(text, l3, l2):
    """
    Checks whether the given wikitext contains a specific level 3 heading
    under a specific level 2 heading.

    Parameters
    ----------
    text : str
        The text to find the heading from.
    l3 : str
        The text of the level 3 heading to look for.
    l2 : str
        The text of the level 2 heading to look for.

    Returns
    -------
    bool
        Whether the wikitext contains the specified level 3 heading under
        the specified level 2 heading.
    """
    matching2 = "=" * 2
    matching3 = "=" * 3
    text = _remove_extra(text)
    in_l2 = False
    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith(matching3) and line.endswith(matching3):
            line = line[3:-3].strip()
            if in_l2 and line == l3:
                return True
        elif line.startswith(matching2) and line.endswith(matching2):
            line = line[2:-2].strip()
            if line == l2:
                in_l2 = True
            elif in_l2:
                break
    return False


def get_section_text(text, level, heading, top=False):
    """Gets the text under the specified heading (first heading that matches
    the given level and heading).

    Parameters
    ----------
    text : str
        The text to find the heading from.
    level : int
        The level of the heading to look for.
    heading : str
        The text of the heading to look for.
    top : bool, default: False
        Whether to only return the text directly under the heading and
        not include any of the subheadings.

    Returns
    -------
    str
        The text under the given heading.

    Raises
    ------
    WikitextError
        If the specified heading is not present in the given wikitext.
    """
    if level < 1 or level > MAXIMUM_HEADING_LEVEL:
        raise ValueError("invalid value for heading level")
    text = _remove_extra(text)
    lines = text.splitlines()
    start_line, end_line = None, None
    for i, line in enumerate(lines):
        line = line.rstrip()
        h = parse_heading(line)
        if h is not None:
            if h.level == level and h.text == heading:
                start_line = i + 1
            elif start_line is not None and top or h.level <= level:
                end_line = i
    if end_line is None:
        end_line = len(lines)
    if start_line is not None:
        return "\n".join(lines[start_line:end_line])
    raise WikitextError(f"heading ({level}, {repr(heading)}) was not found")


def get_namespace(title):
    """Parses a Wiktionary page title and extracts the namespace from it.

    Parameters
    ----------
    title : str
        The page title to parse.

    Returns
    -------
    str or None
        The namespace, in text, of the given title, or None for the
        main namespace.
    """
    if ":" in title:
        return title.split(":", 2)[0]
    else:
        return None


def iterate_headings(text, level):
    """
    Parses wikitext and iterates over all sections of headings of
    a given level.

    Parameters
    ----------
    text : str
        The wikitext to iterate over.
    level : int
        The level of the headings to iterate over.

    Yields
    ------
    Section
        Page sections under headings of the specified level.
    """
    lastindex = -1
    lasttitle = None
    index = -1
    text = _remove_extra(text)
    lines = text.splitlines()
    l2 = "=" * level
    l3 = l2 + "="
    for line in lines:
        index += 1
        if (
            line.startswith(l2)
            and not line.startswith(l3)
            and line.endswith(l2)
            and not line.endswith(l3)
        ):
            yield Section(
                Heading(level, lasttitle),
                "\n".join(lines[lastindex + 1 : index]),
            )
            lastindex = index
            lasttitle = line[level:-level].strip()
    yield Section(
        Heading(level, lasttitle),
        "\n".join(lines[lastindex + 1 :]),
    )


def iterate_l2s(text):
    """
    Parses wikitext and iterates over all sections of level 2 headings.

    Parameters
    ----------
    text : str
        The wikitext to iterate over.

    Yields
    ------
    Section
        Page sections under level 2 headings.
    """
    yield from iterate_headings(text, 2)


def iterate_l3s(text):
    """
    Parses wikitext and iterates over all sections of level 3 headings.

    Parameters
    ----------
    text : str
        The wikitext to iterate over.

    Yields
    ------
    Section
        Page sections under level 3 headings.
    """
    yield from iterate_headings(text, 3)


def iterate_l4s(text):
    """
    Parses wikitext and iterates over all sections of level 4 headings.

    Parameters
    ----------
    text : str
        The wikitext to iterate over.

    Yields
    ------
    Section
        Page sections under level 4 headings.
    """
    yield from iterate_headings(text, 4)


def iterate_l5s(text):
    """
    Parses wikitext and iterates over all sections of level 5 headings.

    Parameters
    ----------
    text : str
        The wikitext to iterate over.

    Yields
    ------
    Section
        Page sections under level 5 headings.
    """
    yield from iterate_headings(text, 5)


def iterate_sections(text):
    """
    Parses wikitext and iterates over all sections.

    Parameters
    ----------
    text : str
        The wikitext to iterate over.

    Yields
    ------
    Section
        Page sections under headings of all levels. Note that the text
        contents for sections may include subsections.
        The expected current structure is
            ((2, "Heading"), "Text 1\n===Subheading===\nText 2")
            ((3, None), "Text 1")
            ((3, "Subheading"), "Text 2")
    """
    for h1 in iterate_headings(text, 1):
        yield h1
        for h2 in iterate_headings(h1.text, 2):
            yield h2
            for h3 in iterate_headings(h2.text, 3):
                yield h3
                for h4 in iterate_headings(h3.text, 4):
                    yield h4
                    for h5 in iterate_headings(h4.text, 5):
                        yield h5
                        for h6 in iterate_headings(h5.text, 6):
                            yield h6


def parse_internal_link(link):
    """
    Parses an internal link from wikitext (of the format [[target]] or
    [[target|text]]).

    Parameters
    ----------
    text : str
        The text to parse the internal link from. Should not contain any
        other text than the link itself.

    Returns
    -------
    InternalLink or None
        A parsed internal link, or None if one cannot be parsed from the text.
    """
    if link.startswith("[[") or link.endswith("]]"):
        linki = link[2:-2]
        if "|" in link:
            return InternalLink(*linki.split("|", 1))
        else:
            return InternalLink(linki, linki)
    else:
        return None


def _find_internal_links_raw(text):
    start = 0
    while True:
        linkstart = text.find("[[", start)
        if linkstart < 0:
            break
        depth = 1
        lookstart = linkstart + 2
        while depth > 0:
            fd = _minfind(text, ("[[", "]]"), lookstart)
            if fd:
                if fd[1] == "[[":
                    depth += 1
                elif fd[1] == "]]":
                    depth = 0
                lookstart = fd[0] + len(fd[1])
            else:
                break
        linkend = lookstart
        start = linkend
        if linkend > linkstart:
            yield linkstart, linkend


# links: {"target", "alt"}


def find_internal_links(text):
    """Parses wikitext and iterates over all internal links.

    Parameters
    ----------
    text : str
        The wikitext to iterate over.

    Yields
    ------
    InternalLink
        All internal links. This includes media embeds and everything else
        that uses the [[...]] syntax.
    """
    text = _remove_extra(text)
    for linkstart, linkend in _find_internal_links_raw(text + " "):
        if linkend > linkstart:
            yield parse_internal_link(text[linkstart:linkend])


iterate_internal_links = find_internal_links


def remove_links(text):
    """
    Removes all (internal) links from the given wikitext. Internal links
    will be replaced by the link text. Note that media embeds do not get any
    special treatment and thus you may get "thumb"s all over the place.

    Parameters
    ----------
    text : str
        The wikitext to remove internal links from.

    Returns
    -------
    str
        The new wikitext with all internal links removed.
    """
    res = ""
    lastptr = 0
    text = _remove_extra(text)
    for linkstart, linkend in _find_internal_links_raw(text + " "):
        res += text[lastptr:linkstart]
        if linkend > linkstart:
            parsed = parse_internal_link(text[linkstart:linkend])
            res += parsed.text
        lastptr = linkend
    res += text[lastptr:]
    return res


def extract_headings_(text):
    lines = text.split('\n')
    leftover = []
    for line_ in lines:
        if line_ and line_[-1] == "\r":
            line = line_[:-1]
        else:
            line = line_
        heading = None
        if line.startswith("=") and line.endswith("="):
            heading = parse_heading(line)
        if heading is None:
            leftover.append(line)
        else:
            if leftover:
                yield "\n".join(leftover)
            leftover = []
            yield heading
    if leftover:
        yield "\n".join(leftover)


def parse_wikitext(text):
    """Parses wikitext and yields sections.

    Parameters
    ----------
    text : str
        The wikitext to iterate over.

    Yields
    -------
    str, Heading, InternalLink, Template
        Either a text section, heading, internal link or template invocation.
    """
    start = 0
    textstart = 0
    text = _remove_extra(text)
    while True:
        specialstart = _minfind(text, ["[[", "{{"], start)
        if specialstart is None:
            break
        if specialstart[1] == "[[":
            if specialstart[0] > textstart:
                yield from extract_headings_(text[textstart : specialstart[0]])
            depth = 1
            lookstart = specialstart[0] + len(specialstart[1])
            linkstart = specialstart[0]
            while depth > 0:
                fd = _minfind(text, ("[[", "]]"), lookstart)
                if fd:
                    if fd[1] == "[[":
                        depth += 1
                    elif fd[1] == "]]":
                        depth = 0
                    lookstart = fd[0] + len(fd[1])
                else:
                    break
            linkend = lookstart
            start = linkend
            textstart = start
            if linkend > linkstart:
                yield parse_internal_link(text[linkstart:linkend])
        elif specialstart[1] == "{{":
            if specialstart[0] > textstart:
                yield from extract_headings_(text[textstart : specialstart[0]])
            depth = 1
            lookstart = specialstart[0] + len(specialstart[1])
            tempstart = specialstart[0]
            while depth > 0:
                fd = _minfind(text, ("{{", "}}"), lookstart)
                if fd:
                    if fd[1] == "{{":
                        depth += 1
                    elif fd[1] == "}}":
                        depth -= 1
                    lookstart = fd[0] + len(fd[1])
                else:
                    break
            tempend = lookstart
            start = tempend
            textstart = start
            if tempend > tempstart:
                yield parse_template_(text[tempstart:tempend])
    if textstart < len(text):
        yield from extract_headings_(text[textstart:])


def _find_templates_raw(text):
    start = 0
    while True:
        tempstart = text.find("{{", start)
        if tempstart < 0:
            break
        depth = 1
        lookstart = tempstart + 2
        while depth > 0:
            fd = _minfind(text, ("{{", "}}"), lookstart)
            if fd:
                if fd[1] == "{{":
                    depth += 1
                elif fd[1] == "}}":
                    depth -= 1
                lookstart = fd[0] + len(fd[1])
            else:
                break
        tempend = lookstart
        start = tempend
        if tempend > tempstart:
            yield tempstart, tempend


def _extract_positional_args(args):
    res, ctr = [], 1
    while ctr in args:
        res.append(args[ctr])
        ctr += 1
    return res


def extract_positional_args(args):
    """Extracts the positional arguments from template invocation arguments.
    ..note:: Deprecated
        Use `get_positional_args` instead.

    Parameters
    ----------
    args : OrderedDict
        The arguments of a template invocation.

    Returns
    -------
    list
        The numbered parameters as a list.
    """
    return _extract_positional_args(args)


def get_positional_args(template):
    """Extracts the positional arguments from a template invocation.

    Parameters
    ----------
    args : Template
        The template invocation to get arguments from.

    Returns
    -------
    list
        The numbered parameters as a list. Note that the list is 1-based -
        there will be a dummy None element as the first (zeroth) element.
    """
    return [None] + _extract_positional_args(template.args)


def _shift_args(args, n):
    if n < 0:
        raise ValueError("cannot shift by a negative amount")
    if n == 0:
        return args
    result = args.copy()
    ctr = n + 1
    for i in range(1, ctr):
        if i in result:
            del result[i]
    while ctr in result:
        result[ctr - n] = result[ctr]
        del result[ctr]
        ctr += 1
    return result


def shift_args(args, n):
    """
    Shifts positional arguments of a template invocation; that is,
    moves positional arguments back by a given number.
    ..note:: Deprecated
        Use `get_positional_args` and slice instead.

    Parameters
    ----------
    args : OrderedDict
        The arguments of a template invocation.
    n : int
        The number to shift by. 1 means "shift all numbered parameters
        back by one".

    Returns
    -------
    OrderedDict
        An OrderedDict where the numbered parameters have been shifted
        but all other parameters left where they are.
    """
    return _shift_args(args)


def find_templates(text):
    """Parses wikitext and iterates over all template invocations.

    Parameters
    ----------
    text : str
        The wikitext to iterate over.

    Yields
    -------
    Template
        All template invocations in the specified wikitext.
    """
    text = _remove_extra(text)
    for tempstart, tempend in _find_templates_raw(text + " "):
        if tempend > tempstart + 2:
            yield parse_template_(text[tempstart:tempend])


iterate_templates = find_templates


def find_templates_by_name(text, name):
    """
    Parses wikitext and iterates over all template invocations for templates
    of a given name.

    Parameters
    ----------
    text : str
        The wikitext to iterate over.
    name : str
        The template name. Only invocations of a given template are yielded.

    Yields
    -------
    Template
        All template invocations for the template of the given name in
        the specified wikitext.
    """
    text = _remove_extra(text)
    for tempstart, tempend in _find_templates_raw(text + " "):
        if tempend > tempstart + 2:
            template = parse_template_(text[tempstart:tempend])
            if template.name == name:
                yield template


iterate_templates_by_name = find_templates_by_name


def replace_templates(text, replace_function):
    """
    Parses wikitext and replaces all template invocations with the results
    given by a function.

    Parameters
    ----------
    text : str
        The wikitext to iterate over.
    replace_function : function(Template)
        The function that will be called with every template invocation
        found in the wikitext. It should return the text that the template
        invocation should be replaced by.
        If the function returns None, the template invocation is removed.
        If the function returns ..., the invocation is not replaced.

    Returns
    -------
    str
        The wikitext with all template invocations replaced.
    """
    text = _remove_extra(text)
    result, i = "", 0
    for tempstart, tempend in _find_templates_raw(text + " "):
        if tempend > tempstart + 2:
            result += text[i:tempstart]
            template = parse_template_(text[tempstart:tempend])
            value = replace_function(template)
            if value is ...:
                value = template.src
            elif value is None:
                value = ""
            result += value
            i = tempend
    result += text[i:]
    return result


def replace_templates_if(text, filter_function, replace_function):
    """
    Parses wikitext and replaces all template invocations with the results
    given by a function if a filter function decides so.

    Parameters
    ----------
    text : str
        The wikitext to iterate over.
    filter_function : function(Template) -> bool
        The function that will be called with every template invocation
        found in the wikitext. It should return either True or False
        to signify whether the invocation should be replaced.
    replace_function : function(Template) -> str
        The function that will be called with every template invocation
        found in the wikitext that the filter returns True for. It should
        return the text that the template invocation should be replaced by.
        If the function returns None, the template invocation is removed.
        If the function returns ..., the invocation is not replaced.

    Returns
    -------
    str
        The wikitext with the appropriate template invocations replaced.
    """
    return replace_templates(
        text,
        lambda template: replace_function(template)
        if filter_function(template)
        else ...,
    )


def parse_template(text):
    """
    Parses an template invocation from wikitext (such as
    {{template|arg1|key=value}}).

    Parameters
    ----------
    text : str
        The text to parse the template invocation from. Should not contain any
        other text than the link itself.

    Returns
    -------
    Template or None
        A parsed template invocation, or None if one cannot be parsed
        from the text.
    """
    rtext = text
    if not (text.startswith("{{") and text.endswith("}}")):
        return None
    text = text[2:-2]
    depth = 0
    linkdepth = 0
    lastpar = 0
    findind = 0
    hadeq = 0
    pars = []
    thiskey = None
    findind = lastpar
    while True:
        match = _minfind(
            text,
            ["{{", "}}", "[[", "]]"]
            + (["|"] if depth == linkdepth == 0 else [])
            + (["="] if depth == linkdepth == hadeq == 0 and pars else []),
            findind,
        )
        if not match:
            break
        findind = match[0] + len(match[1])
        if match[1] == "{{":
            depth += 1
        elif match[1] == "}}":
            depth -= 1
        if match[1] == "[[":
            linkdepth += 1
        elif match[1] == "]]":
            linkdepth -= 1
        elif match[1] == "|":
            pars.append((thiskey, text[lastpar : match[0]]))
            thiskey = None
            lastpar = match[0] + len(match[1])
            hadeq = 0
        elif match[1] == "=":
            thiskey = text[lastpar : match[0]]
            lastpar = match[0] + len(match[1])
            hadeq = 1
    pars.append((thiskey, text[lastpar:]))
    parsed = collections.OrderedDict()
    parind = 0
    for k, v in pars[1:]:
        if k is not None:
            k = k.strip()
            v = v.strip()
            if k in parsed.keys():
                warnings.warn(
                    f"duplicate parameter {k}: {v} to replace"
                    + f" existing {k}={parsed[k]}",
                    WikitextWarning,
                )
            parsed[k] = v
        else:
            parind += 1
            parsed[parind] = v
    return Template(rtext, pars[0][1].strip(), parsed)


def parse_template_(text):
    template = parse_template(text)
    if template is None:
        raise ValueError("internal error; cannot get template from <"
            + text + ">")
    return template


def make_template(name, args, num_first=False):
    """Creates the wikitext for a template invocation.

    Parameters
    ----------
    name : str
        The name of the template to be invoked.
    args : OrderedDict, dict, list
        The arguments for the invocation. The keys for numbered parameters
        should be integers, not strings, while all other keys should be strings.
        If a dict, the order is not well-defined.
        If a list, every element should be a 2-tuple (key, value).
    num_first : bool, default: False
        Whether numbered parameters are first regardless of their order
        in args.

    Returns
    -------
    str
        The wikitext that invokes the template.
    """

    if isinstance(args, dict):
        args = list(args.items())

    if num_first:
        numargs = [
            v for k, v in sorted(args, key=lambda t: t[0]) if type(k) == int
        ]
        posargs, nonposargs = ["|" + x for x in numargs], []
        for key, value in args:
            if type(key) == str:
                nonposargs += "|" + key + "=" + str(value)
            elif type(key) == int:
                pass
            else:
                raise TypeError(f"invalid key type {type(key)}")
        return "{{" + name + "".join(posargs) + "".join(nonposargs) + "}}"
    else:
        argstr, argindx = "", 0
        pathological = False
        while True:
            for key, value in args:
                if type(key) == str:
                    argstr += "|" + key + "=" + str(value)
                elif type(key) == int:
                    if key > argindx:
                        argindx = key
                        argstr += "|" + str(value)
                    elif key < argindx:
                        pathological = True
                        argsorig = args
                        argsresolve = dict(args)
                        args = []
                        skip = 1
                        for key, value in argsorig:
                            if type(key) == str:
                                args.append((key, value))
                            elif type(key) == int:
                                if key <= skip:
                                    continue
                                for j in range(skip, key):
                                    args.append((j, argsresolve.get(j, "")))
                                args.append((key, value))
                                skip = key
                        break
            if pathological:
                pathological = False
                argstr = ""
                argindx = 0
                continue
            break
        return "{{" + name + argstr + "}}"


def remake_template(template):
    """Creates the wikitext for a template invocation from an existing template.

    Parameters
    ----------
    template : Template
        The template invocation.

    Returns
    -------
    str
        The wikitext that invokes the template.
    """

    return make_template(template.name, template.args, False)


# deprecated aliases
iterate_heading = iterate_headings
iterate_l2 = iterate_l2s
iterate_l3 = iterate_l3s
iterate_l4 = iterate_l4s
iterate_l5 = iterate_l5s
iterate_heading_rec = iterate_sections
stringify_template = lambda t, num_first=True: make_template(*t, num_first)
find_templates_src = find_templates
find_templates_src_by_name = find_templates_by_name
replace_templates_src = replace_templates
replace_templates_if_src = replace_templates_if
parse_xml = iterate_pages_in_xml
