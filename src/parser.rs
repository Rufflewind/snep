use std::{self, iter, io, mem};
use std::borrow::Borrow;
use std::cell::RefCell;
use std::collections::VecDeque;
use std::convert::TryFrom;
use std::io::Read;
use std::sync::Arc;
use regex::Regex;

pub mod delimiter {
    use std;
    use std::borrow::Borrow;
    use self::Direction::*;
    use self::Delim::*;

    #[derive(Clone, Copy, Debug, Eq, PartialEq)]
    pub enum Direction {
        Open,
        Close,
    }

    impl std::ops::Not for Direction {
        type Output = Self;
        fn not(self) -> Self::Output {
            match self {
                Direction::Open => Direction::Close,
                Direction::Close => Direction::Open,
            }
        }
    }

    #[derive(Clone, Copy, Debug, Eq, PartialEq)]
    pub enum Delim {
        Parenthesis,
        Bracket,
        Brace,
    }

    impl Delim {
        pub fn open(self) -> Delimiter {
            Delimiter(Open, self)
        }
        pub fn close(self) -> Delimiter {
            Delimiter(Close, self)
        }
    }

    #[derive(Clone, Copy, Debug, Eq, PartialEq)]
    pub struct Delimiter(pub Direction, pub Delim);

    impl Delimiter {
        pub fn as_char(self) -> char {
            self.as_str().chars().next().unwrap()
        }

        pub fn as_str(self) -> &'static str {
            match self {
                Delimiter(Open, Parenthesis) => "(",
                Delimiter(Close, Parenthesis) => ")",
                Delimiter(Open, Bracket) => "[",
                Delimiter(Close, Bracket) => "]",
                Delimiter(Open, Brace) => "{",
                Delimiter(Close, Brace) => "}",
            }
        }
    }

    impl std::convert::TryFrom<char> for Delimiter {
        type Err = ();
        fn try_from(d: char) -> Result<Self, Self::Err> {
            match d {
                '(' => Ok(Delimiter(Open, Parenthesis)),
                ')' => Ok(Delimiter(Close, Parenthesis)),
                '[' => Ok(Delimiter(Open, Bracket)),
                ']' => Ok(Delimiter(Close, Bracket)),
                '{' => Ok(Delimiter(Open, Brace)),
                '}' => Ok(Delimiter(Close, Brace)),
                _ => Err(()),
            }
        }
    }

    impl AsRef<str> for Delimiter {
        fn as_ref(&self) -> &str {
            self.borrow()
        }
    }

    impl Borrow<str> for Delimiter {
        fn borrow(&self) -> &str {
            self.as_str()
        }
    }

    impl std::ops::Deref for Delimiter {
        type Target = str;
        fn deref(&self) -> &Self::Target {
            &self.as_str()
        }
    }

    impl std::fmt::Display for Delimiter {
        fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
            f.write_str(self.as_str())
        }
    }
}

use self::delimiter::Direction::*;
use self::delimiter::{Delim, Delimiter};

const ESCAPER: char = '\\';
const DIVIDER: char = '|';

fn is_word_char(c: char) -> bool {
    !(Delimiter::try_from(c).is_ok() ||
      c.is_whitespace() ||
      c == ESCAPER ||
      c == DIVIDER)
}

/// If `name` is empty, then the location is considered unknown.
#[derive(Clone, Debug)]
pub struct Loc {
    /// Name of the file.
    pub name: Arc<String>,

    /// Zero-based line number.
    pub row: usize,

    /// Zero-based column number.
    pub col: usize,
}

impl Loc {
    pub fn update<I: IntoIterator<Item=char>>(&mut self, bytes: I) {
        for c in bytes {
            self.col += 1;
            if c == '\n' {
                self.col = 0;
                self.row += 1;
            }
        }
    }
}

impl<'a> From<&'a str> for Loc {
    fn from(name: &'a str) -> Self {
        Loc {
            name: Arc::new(String::from(name)),
            row: 0,
            col: 0,
        }
    }
}

impl Default for Loc {
    fn default() -> Self {
        Loc::from(<&str>::default())
    }
}

impl std::fmt::Display for Loc {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        if self.name.is_empty() {
            write!(f, "<unknown>")
        } else {
            write!(f, "{}:{}:{}", self.name, self.row + 1, self.col + 1)
        }
    }
}

#[derive(Clone, Copy, Debug)]
enum Token<'a> {
    Chunk(&'a str),
    Tag(&'a str, Delimiter),
}

#[derive(Clone, Debug)]
struct Lexer<'a> {
    input: &'a str,
    loc: Loc,
    queue: VecDeque<(Loc, Token<'a>)>,
}

impl<'a> Lexer<'a> {
    fn new(input: &'a str, loc: Loc) -> Self {
        Lexer {
            input: input,
            loc: loc,
            queue: VecDeque::new(),
        }
    }

    fn push(&mut self, token: Token<'a>) {
        self.queue.push_back((self.loc.clone(), token));
    }

    fn refill(&mut self) {
        use self::Token::*;

        // end of input
        if self.input.len() == 0 {
            return;
        }

        lazy_static! {
            static ref RE: Regex = Regex::new(concat!(
                r"(?s)",
                r"^(.*?)(",
                r"(:?\\[^\s\\|()\[\]{}]*)?[\])}]",
                r"|",
                r"[\\|]?[^\s\\|()\[\]{}]*[(\[{]",
                r")",
            )).unwrap();
        }
        match RE.captures(self.input) {
            None => {                   // last chunk
                self.push(Chunk(self.input));
                self.input = "";
            }
            Some(caps) => {
                self.input = self.input.split_at(caps.get(0).unwrap().end()).1;
                let chunk = caps.get(1).unwrap().as_str();
                let tag = caps.get(2).unwrap().as_str();

                let last_i = tag.char_indices().last().unwrap().0;
                let (word, delim) = tag.split_at(last_i);
                let delim = delim.chars().next().unwrap();
                let delim = Delimiter::try_from(delim).unwrap();
                let word = word.trim_left_matches('|');

                self.push(Chunk(chunk));
                self.loc.update(chunk.chars());
                self.push(Tag(word, delim));
                self.loc.update(tag.chars());
            }
        }
    }
}

impl<'a> Iterator for Lexer<'a> {
    type Item = (Loc, Token<'a>);

    fn next(&mut self) -> Option<Self::Item> {
        if self.queue.is_empty() {
            self.refill()
        }
        self.queue.pop_front()
    }
}

/// Stores binary data.
#[derive(Clone, Default, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Text(Arc<String>);

impl From<String> for Text {
    fn from(s: String) -> Self {
        Text(Arc::from(s))
    }
}

impl<'a> From<&'a str> for Text {
    fn from(s: &'a str) -> Self {
        Self::from(String::from(s))
    }
}

impl std::convert::AsRef<String> for Text {
    fn as_ref(&self) -> &String {
        self
    }
}

impl std::convert::AsRef<str> for Text {
    fn as_ref(&self) -> &str {
        self.borrow()
    }
}

impl Borrow<String> for Text {
    fn borrow(&self) -> &String {
        self
    }
}

impl Borrow<str> for Text {
    fn borrow(&self) -> &str {
        &self.0
    }
}

impl std::ops::Deref for Text {
    type Target = String;
    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl std::fmt::Debug for Text {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        f.debug_tuple("Text").field(self).finish()
    }
}

impl std::fmt::Display for Text {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        (self as &str).fmt(f)
    }
}

impl<'a, 'b> std::ops::Add<&'b Text> for &'a Text {
    type Output = Text;
    fn add(self, rhs: &'b Text) -> Self::Output {
        let s: &String = self.borrow();
        let mut s = s.clone();
        Text::from(s + (rhs as &str))
    }
}

#[derive(Clone, Debug)]
pub struct Elem {
    pub name: Text,
    pub delim: Delim,
    pub children: Vec<Node>,
    pub loc: Loc,
}

impl Elem {
    /// Melt the node into a mix of text nodes and child nodes.
    /// The closing delimiter is not included.
    fn into_text_nodes(self) -> impl Iterator<Item=Node> {
        let delim = self.delim.open();
        iter::once(Node::Text(self.name))
            .chain(iter::once(Node::escape_delim(delim)))
            .chain(self.children.into_iter())
    }
}

#[derive(Clone, Debug)]
pub enum Node {
    Text(Text),
    Elem(Elem),
}

impl<'a> From<&'a str> for Node {
    fn from(s: &'a str) -> Self {
        Node::Text(Text::from(s))
    }
}

pub fn is_literal(name: &str) -> bool {
    match name.chars().next() {
        Some(ESCAPER) => true,
        _ => false,
    }
}

impl Node {
    pub fn parse(s: &str, path: &str) ->(Vec<Self>, Vec<String>) {
        Node::parse_tokens(Lexer::new(&s, Loc::from(path)))
    }

    fn escape_delim<'a>(delim: Delimiter) -> Self {
        Node::Elem(Elem {
            name: Text::from(ESCAPER.to_string()),
            delim: Delim::Parenthesis,
            children: vec![Node::from(delim.borrow())],
            loc: Default::default(),
        })
    }

    fn parse_tokens<'a, I>(tokens: I) -> (Vec<Self>, Vec<String>)
        where I: Iterator<Item=(Loc, Token<'a>)>
    {
        let mut errs = Vec::new();
        let mut stack = Vec::new();
        let mut top = Elem {
            name: Text::default(),
            delim: Delim::Parenthesis,
            children: Vec::new(),
            loc: Default::default(),
        };
        for token in tokens {
            let esc = is_literal(&top.name);
            match token {
                (_, Token::Chunk(s)) => {
                    top.children.push(Node::from(s));
                }
                (loc, Token::Tag(word, delim)) => match delim {
                    _ if esc && (&top.name as &str) != word => {
                        top.children.push(Node::from(word));
                        top.children.push(Node::from(delim.borrow()));
                    }
                    Delimiter(Open, dtype) => {
                        stack.push(top);
                        top = Elem {
                            name: Text::from(word),
                            delim: dtype,
                            children: Vec::new(),
                            loc: loc,
                        };
                    }
                    Delimiter(Close, dtype) => {
                        if !esc {
                            top.children.push(Node::from(word));
                        }
                        if top.delim != dtype {
                            let d = Delimiter(Open, top.delim);
                            errs.push(format!(
                                "{}: ‘{}’ doesn’t close ‘{}{}’ at {}",
                                loc, delim, top.name, d, top.loc));
                            top.children.push(Self::escape_delim(d));
                        } else {
                            match stack.pop() {
                                None => {
                                    // we're at root level (which is never
                                    // an escaping context), so there's
                                    // nothing to close
                                    errs.push(format!(
                                        "{}: ‘{}’ doesn’t close anything",
                                        loc, delim));
                                    top.children.push(Node::from(
                                        delim.borrow()));
                                }
                                Some(mut new_top) => {
                                    new_top.children.push(Node::Elem(Elem {
                                        name: top.name,
                                        delim: top.delim,
                                        children: top.children,
                                        loc: top.loc,
                                    }));
                                    top = new_top;
                                }
                            }
                        }
                    }
                }
            }
        }
        let mut nodes = mem::replace(match stack.first_mut() {
            Some(root) => {
                errs.push(format!(
                    "{}: ‘{}{}’ was never closed",
                    top.loc, top.name, top.delim.open()));
                &mut root.children
            }
            None => &mut top.children,
        }, Vec::new());
        // flatten the unclosed elements into text
        for elem in stack.into_iter().chain(iter::once(top)).skip(1) {
            nodes.extend(elem.into_text_nodes());
        }
        (nodes, errs)
    }

    pub fn as_mid<'a>(&'a self, state: &'a mut NodeFmtState) -> MidNode<'a> {
        MidNode {
            state: RefCell::new(state),
            node: self,
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum NodeFmtState { Clean, Sticky }

impl Default for NodeFmtState {
    fn default() -> Self {
        NodeFmtState::Clean
    }
}

pub struct Nodes<I>(pub I);

impl<'a, I> std::fmt::Display for Nodes<I>
    where I: Clone + Iterator<Item=&'a Node>
{
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        let mut state = NodeFmtState::Clean;
        for node in self.0.clone() {
            node.as_mid(&mut state).fmt(f)?;
        }
        Ok(())
    }
}

pub struct MidNode<'a> {
    state: RefCell<&'a mut NodeFmtState>,
    node: &'a Node,
}

impl<'a> std::fmt::Display for MidNode<'a> {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        let mut state = self.state.borrow_mut();
        match self.node {
            &Node::Text(ref t) => {
                t.fmt(f)?;
                if is_word_char(t.chars().last().unwrap_or(' ')) {
                    **state = NodeFmtState::Sticky;
                } else {
                    **state = NodeFmtState::Clean;
                }
            }
            &Node::Elem(ref elem) => {
                if let NodeFmtState::Sticky = **state {
                    f.write_str(&DIVIDER.to_string())?;
                }
                elem.name.fmt(f)?;
                elem.delim.open().fmt(f)?;
                Nodes(elem.children.iter()).fmt(f)?;
                if is_literal(&elem.name) {
                    elem.name.fmt(f)?;
                }
                elem.delim.close().fmt(f)?;
                **state = NodeFmtState::Clean;
            },
        }
        Ok(())
    }
}

pub fn load_file(path: &str) -> String {
    let mut f = std::fs::File::open(path).unwrap();
    let mut s = Default::default();
    let _ = f.read_to_string(&mut s).unwrap();
    s
}
