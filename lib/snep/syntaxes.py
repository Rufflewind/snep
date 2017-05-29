import re

syntaxes = {
  "c": [("/\*@", "\*/\s*\n")],
  "c++": [("//@", "\n")],
  "hs": [("--\s@", "\n"), ("{-@", "-}")],
  "sh": [("#@", "\n")],
}

def guess_syntax(extension, shebang):

    if extension in ["c", "cc", "cpp", "cxx", "c++", "C",
                     "h", "hh", "hpp", "hxx", "h++", "H"]:
        return ["c", "c++"]

    if extension in ["hs", "hsc"]:
        return ["hs"]

    if re.search(r"^(py|\w*sh)$", extension):
        return ["sh"]

    if (re.search(r"[/ ]\w*sh\s", shebang) or
        re.search(r"[/ ]i?python[.\d]*\s", shebang)):
        return ["sh"]
